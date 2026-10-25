"""익스포저 정합성 검증 + 기간별 비중 추이.

python scripts/validate_exposures.py knowledge/portfolios/현대해상/ [--trend] [--md]

검사:
  - 자산 mv 합계가 total_invested_assets_krw_bn과 ±2% 안
  - weight ≈ mv/total (±0.5%p), weight 합 ≈ 1 (±2%)
  - 전기 대비 자산군 비중 ±5%p 이상 급변 → 경고 (원문 재확인 대상)
  - '추정' 플래그 목록
  - 2022 이전 ↔ 2023 이후 비교 구간은 IFRS17·IFRS9 도입에 따른 분류 변경 주의 표시
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

from common import class_order, load_json

TOL_TOTAL = 0.02
TOL_SHIFT_PP = 5.0


def period_key(p: str) -> tuple[int, int]:
    m = re.match(r"(\d{4})(?:Q([1-4])|H([12])|FY)?$", p)
    if not m:
        return (0, 0)
    y = int(m[1])
    if m[2]:
        return (y, int(m[2]))
    if m[3]:
        return (y, 2 if m[3] == "1" else 4)
    return (y, 4)


def class_weights(doc: dict) -> dict[str, float]:
    total = doc["total_invested_assets_krw_bn"]
    w = defaultdict(float)
    for a in doc["assets"]:
        w[a["class"]] += a["mv_krw_bn"] / total * 100 if total else 0
    return dict(w)


def check_one(doc: dict) -> tuple[list[str], list[str]]:
    errs, warns = [], []
    total = doc["total_invested_assets_krw_bn"]
    s = sum(a["mv_krw_bn"] for a in doc["assets"])
    if total and abs(s / total - 1) > TOL_TOTAL:
        errs.append(f"자산 합계 {s:,.1f} vs 총 운용자산 {total:,.1f} (차이 {(s / total - 1) * 100:+.2f}%, 허용 ±2%)")
    ws = sum(a["weight"] for a in doc["assets"])
    if abs(ws - 1) > TOL_TOTAL:
        errs.append(f"weight 합 {ws:.4f} ≠ 1 (±2%)")
    for a in doc["assets"]:
        if total and abs(a["weight"] - a["mv_krw_bn"] / total) > 0.005:
            warns.append(f"{a['class']}: weight {a['weight']:.4f} ≠ mv/total {a['mv_krw_bn'] / total:.4f}")
        if a.get("page_ref") in (None, "") and a.get("value_flag") == "공시":
            warns.append(f"{a['class']}: value_flag=공시인데 page_ref 없음")
    est = [a["class"] for a in doc["assets"] if a.get("value_flag") == "추정"] + \
          [f"{a['class']}.{k}" for a in doc["assets"] for k, v in (a.get("field_flags") or {}).items() if v == "추정"]
    if est:
        warns.append("추정 값: " + ", ".join(est))
    return errs, warns


def ifrs_break(p0: str, p1: str) -> bool:
    return (period_key(p0)[0] <= 2022) != (period_key(p1)[0] <= 2022)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--trend", action="store_true")
    ap.add_argument("--md", action="store_true", help="추이 표를 Markdown으로 출력")
    args = ap.parse_args(argv)
    files: list[Path] = []
    for p in map(Path, args.paths):
        files += sorted(p.glob("*.json")) if p.is_dir() else [p]
    docs = sorted((load_json(f) | {"_file": str(f)} for f in files), key=lambda d: (d["company"], period_key(d["period"])))
    n_err = 0
    prev_by_co: dict[str, dict] = {}
    for d in docs:
        errs, warns = check_one(d)
        prev = prev_by_co.get(d["company"])
        if prev:
            w0, w1 = class_weights(prev), class_weights(d)
            for c in sorted(set(w0) | set(w1)):
                delta = w1.get(c, 0) - w0.get(c, 0)
                if abs(delta) >= TOL_SHIFT_PP:
                    tag = " ⚠ IFRS17·IFRS9 전환 구간 — 계정 재분류 가능성" if ifrs_break(prev["period"], d["period"]) else ""
                    warns.append(f"{c}: {prev['period']}→{d['period']} 비중 {delta:+.1f}%p 급변 — 원문 재확인{tag}")
        prev_by_co[d["company"]] = d
        n_err += len(errs)
        print(f"{'OK ' if not errs else 'ERR'} {d['_file']} ({d['company']} {d['period']})")
        for e in errs:
            print(f"    ✗ {e}")
        for w in warns:
            print(f"    ⚠ {w}")
    if args.trend and docs:
        from tabulate import tabulate

        for co in sorted({d["company"] for d in docs}):
            ds = [d for d in docs if d["company"] == co]
            classes = sorted({a["class"] for d in ds for a in d["assets"]}, key=class_order)
            cw = [class_weights(d) for d in ds]
            hdr = ["자산군(%)"] + [d["period"] + (" ⚠IFRS" if i and ifrs_break(ds[i - 1]["period"], d["period"]) else "")
                                 for i, d in enumerate(ds)]
            rows = [[c] + [f"{w.get(c, 0):.1f}" for w in cw] for c in classes]
            rows.append(["총 운용자산(조원)"] + [f"{d['total_invested_assets_krw_bn'] / 1000:.1f}" for d in ds])
            print(f"\n{co} 비중 추이")
            print(tabulate(rows, headers=hdr, tablefmt="github" if args.md else "simple", disable_numparse=True))
            if any(ifrs_break(a["period"], b["period"]) for a, b in zip(ds, ds[1:])):
                print("⚠ 2022 이전과 2023 이후는 IFRS17·IFRS9 도입으로 계정 분류가 달라 직접 비교에 주의")
    print(f"\n{len(docs)}개 파일, 오류 {n_err}건")
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())
