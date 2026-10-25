"""optimize_allocation 가정 민감도: 핵심 가정을 바꿔 전략별 결과(수익 개선·K-ICS·배분)가 얼마나 변하는지 점검.

python scripts/opt_sensitivity.py --portfolio ... --shocks ... --date 2026-10-25 [--out reports/tmp/..._opt_sens]
"""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

import optimize_allocation as oa
from common import CONFIG_DIR, TMP_REPORTS_DIR, load_json, load_yaml, save_json

VARIANTS = {
    "기준": lambda c: c,
    "PE 기대수익 9→7%": lambda c: _set(c, ["classes", "대체-PE", "fixed_pct"], 7.0),
    "헤지비용 +50bp": lambda c: _set(c, ["hedge_cost", "basis_bp"], c["hedge_cost"]["basis_bp"] + 50),
    "사모대출 기대손실 0.6→1.2%": lambda c: _set(c, ["classes", "대체-사모대출", "el_pct"], 1.2),
    "분산효과 없음(div 1.0)": lambda c: _set(c, ["diversification"], 1.0),
    "주식 기대수익 7→5%": lambda c: _set(c, ["classes", "주식", "fixed_pct"], 5.0),
}


def _set(cfg, path, value):
    c = cfg
    for k in path[:-1]:
        c = c[k]
    c[path[-1]] = value
    return cfg


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--portfolio", required=True)
    ap.add_argument("--shocks", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    pf, shocks = load_json(Path(args.portfolio)), load_json(Path(args.shocks))
    base_cfg = load_yaml(CONFIG_DIR / "yield_assumptions.yaml")
    out = {}
    for vname, fn in VARIANTS.items():
        cfg = fn(copy.deepcopy(base_cfg))
        rets = oa.class_returns(cfg, shocks, args.date, pf.get("entity_type", "insurer"))["classes"]
        out[vname] = {}
        for sname, st in cfg["strategies"].items():
            o = oa.optimize(pf, rets, cfg, st)
            out[vname][sname] = {k: o.get(k) for k in ("status", "deltas_pp", "delta_total_return_bp", "delta_carry_bp", "kics_after", "gap_after", "bear_delta_bp")}
    path = Path(args.out) if args.out else TMP_REPORTS_DIR / f"{args.date}_{pf['company']}_opt_sens"
    save_json(path.with_suffix(".json"), out)
    from tabulate import tabulate

    rows = []
    for v, d in out.items():
        for s, o in d.items():
            dp = o["deltas_pp"] or {}
            top = ", ".join(f"{k}{x:+.1f}" for k, x in sorted(dp.items(), key=lambda kv: -kv[1])[:4] if x > 0)
            rows.append([v, s, o["delta_total_return_bp"], o["delta_carry_bp"],
                         f"{o['kics_after']['high']}~{o['kics_after']['low']}" if o.get("kics_after") else "—", o["bear_delta_bp"], top])
    print(tabulate(rows, headers=["가정 변형", "전략", "총수익 +bp", "캐리 +bp", "K-ICS 후(%)", "Bear Δbp", "주요 증가(%p)"]))
    print(f"\n저장: {path.with_suffix('.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
