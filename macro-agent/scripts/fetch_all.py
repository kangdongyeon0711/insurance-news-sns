"""전체 수집 + data/latest_snapshot.json 생성.

사용:
  python scripts/fetch_all.py              # ECOS·FRED·EIA·DART 수집 후 스냅샷 생성
  python scripts/fetch_all.py --no-fetch   # 이미 있는 data/series/*.csv로 스냅샷만 재생성
  python scripts/fetch_all.py --print      # 주요 값 출력

수집 실패/키 누락이어도 스냅샷은 기존 CSV로 생성하고 warnings에 기록한다.
수기 입력값(data/manual/*.yaml — 예: ECOS 홈페이지에서 직접 확인한 값)은 API 값과 합친다. 같은 날짜는 API 우선,
괴리 0.5% 초과 시 경고. 스냅샷 항목의 source_type(api|manual)·value_flag(API|수기)로 구분한다.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from common import (CONFIG_DIR, SERIES_DIR, SNAPSHOT_PATH, get_logger, load_yaml, read_series_csv, save_json,
                    stale_threshold_days, today, write_series_csv)

log = get_logger("fetch_all")
KEY_SERIES = ["krw_usd", "ktb_10y", "kr_aa_spread", "ust_10y", "us_ig_oas", "brent", "kr_base_rate"]


def _value_at_or_before(s: pd.Series, d: pd.Timestamp) -> float | None:
    sub = s[s.index <= d]
    return None if sub.empty else float(sub.iloc[-1])


def _chg(s: pd.Series, last_date: pd.Timestamp, last: float, offset: pd.DateOffset, chg_type: str) -> float | None:
    prev = _value_at_or_before(s, last_date - offset)
    if prev is None:
        return None
    if chg_type == "pct":
        return None if prev == 0 else round((last / prev - 1) * 100, 2)
    return round((last - prev) * 100, 1)  # %p → bp


def series_stats(s: pd.Series, meta: dict, ref: date) -> dict:
    s = s.dropna().sort_index()
    last_date, last = s.index[-1], float(s.iloc[-1])
    chg_type = meta.get("chg_type", "diff")
    cycle = meta.get("cycle", "D")
    s5 = s[s.index >= last_date - pd.DateOffset(years=5)]
    age = (pd.Timestamp(ref) - last_date).days
    return {
        "series_id": meta["series_id"],
        "name": meta["name"],
        "topic_id": meta.get("topic_id"),
        "source": meta.get("source", "derived"),
        "unit": meta.get("unit", "%p"),
        "chg_unit": "%" if chg_type == "pct" else "bp",
        "last_value": round(last, 4),
        "as_of": last_date.strftime("%Y-%m-%d"),
        "chg_1w": _chg(s, last_date, last, pd.DateOffset(weeks=1), chg_type),
        "chg_1m": _chg(s, last_date, last, pd.DateOffset(months=1), chg_type),
        "chg_3m": _chg(s, last_date, last, pd.DateOffset(months=3), chg_type),
        "chg_1y": _chg(s, last_date, last, pd.DateOffset(years=1), chg_type),
        "pct_rank_5y": round(float((s5 <= last).mean()), 3) if len(s5) > 1 else None,
        "age_days": age,
        "stale": age > stale_threshold_days(cycle),
        "verified": meta.get("verified", False),
    }


def load_manual(manual_dir: Path, warnings: list[str] | None = None) -> dict[str, dict]:
    """data/manual/*.yaml의 수기 입력값 → {series_id: {"points": pd.Series, "meta": {...}, "info": {...}}}.

    같은 series_id·같은 날짜가 여러 파일에 있으면 priority가 높은 파일(동률이면 나중 파일) 값을 쓰고,
    값이 0.5% 넘게 다르면 경고한다.
    """
    out: dict[str, dict] = {}
    warnings = warnings if warnings is not None else []
    docs = [(f, load_yaml(f) or {}) for f in (sorted(manual_dir.glob("*.yaml")) if manual_dir.exists() else [])]
    docs.sort(key=lambda x: x[1].get("priority", 0))   # 안정 정렬: 낮은 priority 먼저 → 높은 것이 덮어씀
    for f, doc in docs:
        for pt in doc.get("points", []):
            sid = pt["series_id"]
            e = out.setdefault(sid, {"rows": {}, "meta": {}, "info": {}})
            d = pd.Timestamp(str(pt["as_of"]))
            v = float(pt["value"])
            if d in e["rows"] and e["rows"][d] and abs(v / e["rows"][d] - 1) > 0.005:
                warnings.append(f"{sid}: {d.date()} 수기 파일 간 값 불일치 {e['rows'][d]} → {v} ({f.name} 채택)")
            e["rows"][d] = v
            e["meta"].update(pt.get("meta") or {})
            e["info"][d.strftime("%Y-%m-%d")] = {"file": str(f.relative_to(manual_dir.parent.parent)),
                                                 "source": doc.get("source"), "period_label": pt.get("period_label"),
                                                 "note": pt.get("note")}
    for e in out.values():
        e["points"] = pd.Series(e.pop("rows")).sort_index()
    return out


def merge_series(api: pd.Series | None, manual: dict | None, sid: str, warnings: list[str]) -> tuple[pd.Series | None, str]:
    """API 값 우선으로 수기 값을 합친다. 반환: (합친 시계열, 마지막 값의 출처 'api'|'manual')."""
    if manual is None:
        return api, "api"
    m = manual["points"]
    if api is None:
        return m, "manual"
    both = api.index.intersection(m.index)
    for d0 in both:
        a, b = float(api[d0]), float(m[d0])
        if a and abs(b / a - 1) > 0.005:
            warnings.append(f"{sid}: {d0.date()} 수기 {b} vs API {a} 괴리 {abs(b / a - 1) * 100:.2f}% — 확인 필요")
    merged = api.combine_first(m).sort_index()
    return merged, ("api" if merged.index[-1] in api.index else "manual")


def build_derived(defs: list[dict], data: dict[str, pd.Series], series_dir: Path) -> list[dict]:
    """파생 스프레드 계산 → series_dir/{id}.csv 저장 + data에 추가. 계산된 정의 목록 반환."""
    built = []
    for d in defs:
        a, b = data.get(d["a"]), data.get(d["b"])
        if a is None or b is None:
            log.warning("파생 %s 계산 불가: %s 또는 %s 없음", d["series_id"], d["a"], d["b"])
            continue
        if d.get("ffill"):  # 정책금리처럼 주기가 다른 계단형 시계열
            idx = a.index.union(b.index)
            a, b = a.reindex(idx).ffill(), b.reindex(idx).ffill()
        df = pd.concat([a.rename("a"), b.rename("b")], axis=1, join="inner").dropna()
        if df.empty:
            continue
        diff = (df["a"] - df["b"]).round(4)
        write_series_csv(d["series_id"], [(i.strftime("%Y-%m-%d"), v) for i, v in diff.items()], series_dir)
        data[d["series_id"]] = diff
        built.append(d)
    return built


def build_snapshot(series_dir: Path = SERIES_DIR, ref: date | None = None, fetch_status: dict | None = None,
                   manual_dir: Path | None = None) -> dict:
    ref = ref or today()
    manual_dir = manual_dir or (series_dir.parent / "manual")
    cfg = load_yaml(CONFIG_DIR / "series.yaml")
    warnings: list[str] = []
    out: dict[str, dict] = {}
    by_id: dict[str, dict] = {}
    data: dict[str, pd.Series] = {}
    src_type: dict[str, str] = {}
    manual = load_manual(manual_dir, warnings)
    metas = list(cfg["series"])
    known = {m["series_id"] for m in metas}
    for sid, e in manual.items():
        if sid not in known:
            metas.append({"series_id": sid, "source": "manual", "verified": None, "name": sid, "unit": "",
                          "cycle": "D", "chg_type": "pct", "topic_id": None, **e["meta"]})
    for meta in metas:
        sid = meta["series_id"]
        api = read_series_csv(sid, series_dir) if meta.get("source") != "manual" else None
        s, st = merge_series(api, manual.get(sid), sid, warnings)
        if s is None:
            warnings.append(f"{sid}({meta['name']}): 데이터 없음 — 미확인")
            continue
        by_id[sid], data[sid], src_type[sid] = meta, s, st
        out[sid] = series_stats(s, meta, ref)
        out[sid]["source_type"] = st
        out[sid]["value_flag"] = "API" if st == "api" else "수기"
        if st == "manual":
            out[sid]["manual"] = manual[sid]["info"][out[sid]["as_of"]]
    for d in build_derived(cfg.get("derived", []), data, series_dir):
        s = data[d["series_id"]]
        comps = [by_id.get(d["a"], {}), by_id.get(d["b"], {})]
        st = "manual" if "manual" in (src_type.get(d["a"]), src_type.get(d["b"])) else "api"
        meta = {**d, "source": "derived", "unit": "%p", "chg_type": "diff",
                "cycle": "M" if any(c.get("cycle") == "M" for c in comps) else "D",
                "verified": all(c.get("verified", False) for c in comps)}
        out[d["series_id"]] = {**series_stats(s, meta, ref), "last_value_bp": round(float(s.iloc[-1]) * 100, 1),
                               "formula": f"{d['a']} - {d['b']}", "source_type": st,
                               "value_flag": "API" if st == "api" else "수기"}
    for sid, st in out.items():
        if st["stale"]:
            warnings.append(f"{sid}: 기준일 {st['as_of']} ({st['age_days']}일 경과) — 오래된 데이터")
        if st["source_type"] == "manual":
            pass  # 아래에서 한 줄로 요약
        elif not st["verified"]:
            warnings.append(f"{sid}: 시리즈 코드 미검증(verified: false)")
    n_manual = sum(1 for st in out.values() if st["source_type"] == "manual")
    if n_manual:
        warnings.append(f"수기 입력값 {n_manual}개(data/manual/, value_flag=수기) — API 수집 후 교차검증 필요")
    # ECOS vs FRED 원/달러 교차검증
    if "krw_usd" in data and "krw_usd_fred" in data:
        e, f = data["krw_usd"], data["krw_usd_fred"]
        common = e.index.intersection(f.index)
        if len(common):
            d0 = common[-1]
            gap = abs(e[d0] / f[d0] - 1) * 100
            out["krw_usd"]["cross_check"] = {"date": d0.strftime("%Y-%m-%d"), "ecos": float(e[d0]),
                                             "fred": float(f[d0]), "gap_pct": round(gap, 3)}
            if gap > 1.0:
                warnings.append(f"원/달러 ECOS vs FRED 괴리 {gap:.2f}% ({d0.date()}) — 확인 필요")
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "ref_date": ref.isoformat(),
        "fetch_status": fetch_status or {},
        "warnings": warnings,
        "series": out,
    }


def run_fetchers() -> dict:
    import fetch_dart
    import fetch_ecos
    import fetch_eia
    import fetch_fred

    status = {}
    for name, fn in (("ecos", lambda: fetch_ecos.main([])), ("fred", lambda: fetch_fred.main([])),
                     ("eia", fetch_eia.main), ("dart", fetch_dart.main)):
        try:
            rc = fn()
            status[name] = {0: "ok", 2: "no_key"}.get(rc, "partial_failure")
        except Exception as e:  # noqa: BLE001 — 한 소스 실패가 전체를 막지 않도록
            log.error("%s 수집 중단: %s", name, e)
            status[name] = f"failed: {type(e).__name__}"
    return status


def print_key_values(snap: dict) -> None:
    from tabulate import tabulate

    rows = []
    for sid in KEY_SERIES:
        st = snap["series"].get(sid)
        if st:
            rows.append([sid, st["name"], st["last_value"], st["unit"], st["as_of"], st["chg_1w"], st["chg_unit"],
                         "⚠" if st["stale"] else ""])
        else:
            rows.append([sid, "-", "미확인", "", "", "", "", ""])
    print(tabulate(rows, headers=["series_id", "이름", "값", "단위", "기준일", "1주 변화", "변화단위", "stale"]))
    print(f"\n경고 {len(snap['warnings'])}건, 수집 상태: {snap['fetch_status']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--print", action="store_true")
    args = ap.parse_args(argv)
    status = {} if args.no_fetch else run_fetchers()
    snap = build_snapshot(fetch_status=status)
    if not snap["series"] and SNAPSHOT_PATH.exists():
        log.warning("수집된 시계열이 하나도 없어 기존 스냅샷을 유지합니다: %s", SNAPSHOT_PATH)
        return 1
    save_json(SNAPSHOT_PATH, snap)
    log.info("스냅샷 저장: %s (시계열 %d개, 경고 %d건)", SNAPSHOT_PATH, len(snap["series"]), len(snap["warnings"]))
    if args.print:
        print_key_values(snap)
    return 0 if snap["series"] else 1


if __name__ == "__main__":
    sys.exit(main())
