"""한국은행 ECOS 시계열 수집.

사용:
  python scripts/fetch_ecos.py            # series.yaml의 source: ecos 항목 수집
  python scripts/fetch_ecos.py --verify   # StatisticItemList로 항목코드/이름/주기 확인 후 verified 갱신
"""
from __future__ import annotations

import argparse
import sys

from common import (RAW_DIR, MissingApiKey, ecos_date, get_logger, http_get, load_series_config,
                    load_yaml, CONFIG_DIR, parse_ecos_time, require_key, save_json, set_verified, today,
                    write_series_csv, years_ago, iso)

BASE = "https://ecos.bok.or.kr/api"
log = get_logger("ecos")


def _rows(payload: dict, service: str) -> list[dict]:
    if service in payload:
        return payload[service].get("row", [])
    result = payload.get("RESULT", {})
    code, msg = result.get("CODE", ""), result.get("MESSAGE", "")
    if code == "INFO-200":  # 해당 데이터 없음
        return []
    raise RuntimeError(f"ECOS 오류 {code}: {msg}")


def fetch_series(key: str, spec: dict, years: int) -> list[tuple[str, float]]:
    cycle = spec["cycle"]
    start, end = ecos_date(years_ago(years), cycle), ecos_date(today(), cycle)
    url = f"{BASE}/StatisticSearch/{key}/json/kr/1/100000/{spec['stat_code']}/{cycle}/{start}/{end}/{spec['item_code']}"
    payload = http_get(url, logger=log).json()
    save_json(RAW_DIR / "ecos" / f"{spec['series_id']}.json", payload)
    out = []
    for r in _rows(payload, "StatisticSearch"):
        v = r.get("DATA_VALUE")
        if v in (None, "", "-"):
            continue
        out.append((parse_ecos_time(r["TIME"], cycle), float(v.replace(",", ""))))
    return out


def verify(key: str, specs: list[dict]) -> int:
    cache: dict[str, list[dict]] = {}
    bad = 0
    for s in specs:
        stat = s["stat_code"]
        if stat not in cache:
            url = f"{BASE}/StatisticItemList/{key}/json/kr/1/10000/{stat}"
            payload = http_get(url, logger=log).json()
            save_json(RAW_DIR / "ecos" / f"itemlist_{stat}.json", payload)
            cache[stat] = _rows(payload, "StatisticItemList")
        matches = [r for r in cache[stat] if r.get("ITEM_CODE") == s["item_code"]]
        cycles = {r.get("CYCLE") for r in matches}
        names = {r.get("ITEM_NAME", "") for r in matches}
        ok = bool(matches) and s["cycle"] in cycles and any(s.get("expect_name", "") in n for n in names)
        set_verified(s["series_id"], ok)
        log.info("%-16s %s/%s 주기=%s 이름=%s → %s", s["series_id"], stat, s["item_code"],
                 sorted(cycles), sorted(names), "확인" if ok else "불일치/미확인")
        if not ok:
            bad += 1
            same_name = [f"{r['ITEM_CODE']}:{r['ITEM_NAME']}({r.get('CYCLE')})" for r in cache[stat]
                         if s.get("expect_name", "@@") in r.get("ITEM_NAME", "")]
            if same_name:
                log.info("   이름 후보: %s", ", ".join(same_name[:10]))
    return bad


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args(argv)
    specs = [s for s in load_series_config() if s["source"] == "ecos"]
    try:
        key = require_key("ECOS_API_KEY")
    except MissingApiKey as e:
        log.error(str(e))
        return 2
    if args.verify:
        return 1 if verify(key, specs) else 0
    years = load_yaml(CONFIG_DIR / "series.yaml").get("lookback_years", 10)
    failed = 0
    for s in specs:
        try:
            rows = fetch_series(key, s, years)
            write_series_csv(s["series_id"], rows)
            log.info("%s: %d건 (마지막 %s)", s["series_id"], len(rows), rows[-1][0] if rows else "없음")
        except Exception as e:  # noqa: BLE001 — 개별 실패는 로깅 후 계속
            failed += 1
            log.error("%s 수집 실패: %s", s["series_id"], e)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
