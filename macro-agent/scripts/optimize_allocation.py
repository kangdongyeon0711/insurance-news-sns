"""운용수익률 제고 배분 최적화 (선형계획) — 매크로 전망·K-ICS·ALM·Bear 손실·집중 한도 제약.

python scripts/optimize_allocation.py --portfolio knowledge/portfolios/현대해상/2026Q2.json \
    --shocks reports/tmp/2026-10-25_factor_shocks.json [--date 2026-10-25] [--out reports/tmp/2026-10-25_현대해상_opt]

- 자산군별 기대 총수익(연, %) = 시장 base(수기·웹확인 시계열) + spread − 기대손실 − 헤지비용(외화)
  + 확률가중 평가변화(calc_impact 엔진, 장기 Base/Bull/Bear 확률) ÷ horizon_years.  입력: config/yield_assumptions.yaml
- 변수: 자산군별 신규 배분 변화 ΔMV(십억원). 목표: Σ ΔMV × 기대 총수익 최대화.
- 제약: ΣΔMV = 0, 조정폭 ±step, 현금 하한, 대체투자 상한, K-ICS 하한(보수적으로 위험계수 상단 사용),
  공시 기준 듀레이션 갭 범위, Bear 시나리오 손실 추가 허용 한도, 보유액 이하 매도, 고정 자산군 불변.
- 출력: {out}.json (전략별 배분·수익률 개선·K-ICS 범위·갭·Bear·시나리오 영향) + 콘솔 표.
모든 결과는 가정 기반 근사이며 투자 권유가 아니다.
"""
from __future__ import annotations

import argparse
import copy
import glob
import sys
from pathlib import Path

from common import CONFIG_DIR, KNOWLEDGE_DIR, SNAPSHOT_PATH, TMP_REPORTS_DIR, load_json, load_yaml, save_json, today

import calc_impact as ci


def market_value(series_id: str, date: str) -> dict | None:
    """snapshot 우선, 없으면 macro_topics indicators에서 시계열 값 조회 → {value, as_of, flag}."""
    if SNAPSHOT_PATH.exists():
        s = load_json(SNAPSHOT_PATH)["series"].get(series_id)
        if s:
            return {"value": s["last_value"], "as_of": s["as_of"], "flag": s.get("value_flag", "API")}
    for f in sorted(glob.glob(str(KNOWLEDGE_DIR / "macro_topics" / date / "*.json"))):
        for i in load_json(Path(f))["current"]["indicators"]:
            if i["series_id"] == series_id and i.get("value") is not None:
                return {"value": i["value"], "as_of": i.get("as_of"), "flag": i.get("value_flag", "웹확인")}
    return None


def hedge_cost_pct(cfg: dict, date: str) -> dict:
    h = cfg["hedge_cost"]
    us, kr = market_value(h["usd_short"]["series"], date), market_value(h["krw_short"]["series"], date)
    if not us or not kr:
        return {"value": None, "note": "헤지비용 계산용 금리 미확인"}
    v = us["value"] + h["usd_short"].get("adj_bp", 0) / 100 - kr["value"] + h.get("basis_bp", 0) / 100
    return {"value": round(v, 3), "note": f"FFR 중간값 {us['value'] + h['usd_short'].get('adj_bp', 0) / 100:.3f}%({us['flag']}, {us['as_of']}) − "
                                          f"CD {kr['value']}%({kr['flag']}, {kr['as_of']}) + 베이시스 {h.get('basis_bp', 0)}bp(가정)"}


def class_returns(cfg: dict, shocks_doc: dict, date: str, entity: str) -> dict:
    """자산군별 기대 총수익과 구성요소. 평가변화는 신규 자금 가정(듀레이션 등)으로 엔진을 돌려 계산."""
    eng = ci.Engine(floating_income=False, entity_type=entity)
    lt = [s for s in shocks_doc["scenarios"] if s.get("prob") is not None]
    psum = sum(s["prob"] for s in lt) or 1.0
    bear = next((s for s in lt if "Bear" in s["name"]), None)
    hc = hedge_cost_pct(cfg, date)
    out = {}
    for cls, c in cfg["classes"].items():
        if c.get("base"):
            mv = market_value(c["base"], date)
            base, src = (mv["value"], f"{c['base']} {mv['value']}%({mv['flag']}, {mv['as_of']})") if mv else (None, f"{c['base']} 미확인")
        else:
            base, src = c.get("fixed_pct"), f"고정 가정 {c.get('fixed_pct')}%"
        if base is None:
            continue
        spread = c.get("spread_bp", 0) / 100
        if c.get("spread_series"):
            sm = market_value(c["spread_series"], date)
            if sm:
                spread += sm["value"]
                src += f" + {c['spread_series']} {sm['value']}%({sm['flag']}, {sm['as_of']})"
        hedge = (hc["value"] or 0.0) if c.get("hedged") else 0.0
        asset = {"class": cls, "region": c.get("region", "KR"), "currency": c.get("currency", "KRW"), "mv_krw_bn": 100.0,
                 "mod_duration": c.get("duration") or None, "spread_duration": c.get("duration") or None,
                 "credit_grade": "AA" if cls == "회사채" else ("IG" if cls == "해외채" else None),
                 "fx_hedge_ratio": 1.0 if c.get("hedged") else None, "value_flag": "추정"}
        pw = sum(s["prob"] * eng.asset_impact(asset, s["shocks"], set()).impact_bn for s in lt) / psum   # 100 기준 → %
        bear_pct = eng.asset_impact(asset, bear["shocks"], set()).impact_bn if bear else 0.0
        mtm = pw / cfg["horizon_years"]
        total = base + spread - c.get("el_pct", 0) - hedge + mtm
        out[cls] = {"base_pct": round(base, 3), "spread_pct": round(spread, 3), "el_pct": c.get("el_pct", 0),
                    "hedge_pct": round(hedge, 3), "mtm_pct_per_year": round(mtm, 3), "carry_net_pct": round(base + spread - c.get("el_pct", 0) - hedge, 3),
                    "total_pct": round(total, 3), "bear_pct": round(bear_pct, 3), "charge": c["charge"],
                    "duration": c.get("duration", 0.0), "source": src, "note": c.get("note", ""),
                    "region": c.get("region", "KR"), "currency": c.get("currency", "KRW"), "hedged": bool(c.get("hedged"))}
    return {"classes": out, "hedge_cost": hc}


def kics_capital(pf: dict, cfg: dict) -> dict:
    """가용·요구자본(십억원). 공시 K-ICS 비율이 있으면 요구자본 = 가용 ÷ 비율로 맞춘다(반올림 오차 제거)."""
    fb = cfg["kics_capital_fallback"]
    avail = fb["available_trn"] * 1000
    ratio = next((c["value"] for c in pf.get("capital_ratios") or [] if c["name"].upper().startswith("K-ICS") and c.get("value")), None)
    req = avail / (ratio / 100) if ratio else fb["required_trn"] * 1000
    return {"available": avail, "required": round(req, 1), "source": fb["source"] + (f"; 요구자본 = 가용 ÷ 공시 K-ICS {ratio}%" if ratio else "")}


def disclosed_gap_base(pf: dict) -> tuple[float | None, float | None]:
    """공시 듀레이션 갭(자산 D − 부채 D)과 금리민감 자산 기준액(십억원, 공시 민감도 역산)."""
    km = pf.get("key_metrics") or {}
    da = next((v["value"] for k, v in km.items() if k.startswith("자산 Duration")), None)
    dl = (pf.get("liabilities") or {}).get("duration")
    sens = next((d for d in pf.get("rate_sensitivity_disclosed") or [] if d["shock_bp"] > 0 and d.get("asset_chg_krw_bn")), None)
    base = abs(sens["asset_chg_krw_bn"]) / (da * sens["shock_bp"] / 1e4) if (sens and da) else None
    gap = (da - dl) if (da is not None and dl is not None) else None
    return gap, base


def optimize(pf: dict, rets: dict, cfg: dict, strat: dict) -> dict:
    from scipy.optimize import linprog

    T = float(pf["total_invested_assets_krw_bn"])
    hold: dict[str, float] = {}
    for a in pf["assets"]:
        hold[a["class"]] = hold.get(a["class"], 0.0) + float(a["mv_krw_bn"])
    universe = [c for c in rets if c not in cfg["fixed_classes"]]
    n = len(universe)
    r = [rets[c]["total_pct"] / 100 for c in universe]
    step = strat["step_pp"] / 100 * T
    cb = cfg.get("class_bounds_pp") or {}
    bounds = []
    for c in universe:
        lo, hi = -min(hold.get(c, 0.0), step), step
        if c in cb:
            lo, hi = max(lo, cb[c][0] / 100 * T), min(hi, cb[c][1] / 100 * T)
        bounds.append((lo, hi))
    A_ub, b_ub = [], []
    # 현금 하한: −x_cash ≤ hold_cash − cash_min·T
    if "현금예금" in universe:
        row = [0.0] * n; row[universe.index("현금예금")] = -1.0
        A_ub.append(row); b_ub.append(hold.get("현금예금", 0.0) - strat["cash_min"] * T)
    # 대체 상한
    alt = cfg["alt_classes"]
    A_ub.append([1.0 if c in alt else 0.0 for c in universe]); b_ub.append(strat["alt_cap"] * T - sum(hold.get(c, 0.0) for c in alt))
    # K-ICS 하한 (위험계수 상단, 보수적): Σ x·c_hi·div ≤ avail/floor − required
    cap = kics_capital(pf, cfg)
    div = cfg["diversification"]
    A_ub.append([rets[c]["charge"][1] * div for c in universe]); b_ub.append(cap["available"] / strat["kics_floor"] - cap["required"])
    # 듀레이션 갭 (공시 기준)
    gap0, base = disclosed_gap_base(pf)
    if gap0 is not None and base:
        lo, hi = strat["gap_range"]
        dur = [rets[c]["duration"] / base for c in universe]
        A_ub.append(dur); b_ub.append(hi - gap0)
        A_ub.append([-d for d in dur]); b_ub.append(gap0 - lo)
    # Bear 손실 추가 허용: Σ x·bear_pct ≥ −extra·T  →  −Σ x·bear_pct ≤ extra·T
    A_ub.append([-rets[c]["bear_pct"] / 100 for c in universe]); b_ub.append(strat["bear_extra_bp"] / 1e4 * T)
    res = linprog(c=[-x for x in r], A_ub=A_ub, b_ub=b_ub, A_eq=[[1.0] * n], b_eq=[0.0], bounds=bounds, method="highs")
    if not res.success:
        return {"status": "infeasible", "message": res.message}
    x = {c: round(float(v), 1) for c, v in zip(universe, res.x) if abs(v) > 0.05}
    d_income = sum(x[c] * rets[c]["total_pct"] / 100 for c in x)
    d_carry = sum(x[c] * rets[c]["carry_net_pct"] / 100 for c in x)
    scr = {k: sum(x[c] * rets[c]["charge"][i] * div for c in x) for i, k in enumerate(("low", "high"))}
    gap_after = gap0 + sum(x[c] * rets[c]["duration"] for c in x) / base if (gap0 is not None and base) else None
    bear_delta = sum(x[c] * rets[c]["bear_pct"] / 100 for c in x)
    kics_now = cap["available"] / cap["required"]
    return {
        "status": "ok", "deltas_krw_bn": x, "deltas_pp": {c: round(v / T * 100, 2) for c, v in x.items()},
        "turnover_krw_bn": round(sum(v for v in x.values() if v > 0), 1),
        "delta_total_return_100m": round(d_income * 10, 1), "delta_total_return_bp": round(d_income / T * 1e4, 1),
        "delta_carry_100m": round(d_carry * 10, 1), "delta_carry_bp": round(d_carry / T * 1e4, 1),
        "delta_scr_krw_bn": {k: round(v, 1) for k, v in scr.items()},
        "kics_now": round(kics_now * 100, 1),
        "kics_after": {k: round(cap["available"] / (cap["required"] + scr[k]) * 100, 1) for k in ("low", "high")},
        "gap_before": None if gap0 is None else round(gap0, 2), "gap_after": None if gap_after is None else round(gap_after, 2),
        "bear_delta_100m": round(bear_delta * 10, 1), "bear_delta_bp": round(bear_delta / T * 1e4, 1),
    }


def adjusted_portfolio(pf: dict, deltas: dict, rets: dict) -> dict:
    """최적 배분을 반영한 포트폴리오 (없는 자산군은 신규 행 추가, 신규분 가정은 yield_assumptions 기준)."""
    p = copy.deepcopy(pf)
    for cls, dv in deltas.items():
        rows = [a for a in p["assets"] if a["class"] == cls]
        if rows:
            tot = sum(float(a["mv_krw_bn"]) for a in rows) or 1.0
            for a in rows:
                a["mv_krw_bn"] = float(a["mv_krw_bn"]) + dv * float(a["mv_krw_bn"]) / tot
        elif dv > 0:
            c = rets[cls]
            p["assets"].append({"class": cls, "label": "신규 배분(최적화)", "region": c["region"], "currency": c["currency"],
                                "mv_krw_bn": dv, "weight": dv / p["total_invested_assets_krw_bn"],
                                "mod_duration": c["duration"] or None, "fx_hedge_ratio": 1.0 if c["hedged"] else None,
                                "value_flag": "추정", "page_ref": None, "field_flags": {"mod_duration": "추정"}})
    for a in p["assets"]:
        a["weight"] = float(a["mv_krw_bn"]) / p["total_invested_assets_krw_bn"]
    return p


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--portfolio", required=True)
    ap.add_argument("--shocks", required=True)
    ap.add_argument("--date", default=today().isoformat())
    ap.add_argument("--out")
    ap.add_argument("--assumptions", default=str(CONFIG_DIR / "yield_assumptions.yaml"))
    args = ap.parse_args(argv)
    pf, shocks = load_json(Path(args.portfolio)), load_json(Path(args.shocks))
    cfg = load_yaml(Path(args.assumptions))
    entity = pf.get("entity_type", "insurer")
    rets = class_returns(cfg, shocks, args.date, entity)
    base_run = ci.run(pf, shocks)
    result = {"company": pf["company"], "period": pf["period"], "as_of": args.date, "inputs": rets,
              "kics_capital": kics_capital(pf, cfg), "disclosed_gap_and_base": disclosed_gap_base(pf),
              "baseline_scenarios": {s["name"]: {"total_100m": s["total_100m"], "total_bp": s["total_bp"]} for s in base_run["scenarios"]},
              "strategies": {}}
    for name, st in cfg["strategies"].items():
        o = optimize(pf, rets["classes"], cfg, st)
        if o["status"] == "ok":
            adj = adjusted_portfolio(pf, o["deltas_krw_bn"], rets["classes"])
            run = ci.run(adj, shocks)
            o["scenarios_after"] = {s["name"]: {"total_100m": s["total_100m"], "total_bp": s["total_bp"],
                                                "calibrated_100m": (s.get("calibrated") or {}).get("total_100m")} for s in run["scenarios"]}
            o["alm_after"] = {s["name"]: {k: s["alm"].get(k) for k in ("disclosed_capital_100m", "disclosed_ratio_pp", "duration_gap_years")}
                              for s in run["scenarios"] if s.get("alm")}
        o["constraints"] = st
        result["strategies"][name] = o
    out = Path(args.out) if args.out else TMP_REPORTS_DIR / f"{args.date}_{pf['company']}_opt"
    save_json(out.with_suffix(".json"), result)
    from tabulate import tabulate

    print(f"헤지비용(연): {rets['hedge_cost']['value']}% — {rets['hedge_cost']['note']}")
    print(tabulate([[c, v["base_pct"], v["spread_pct"], -v["el_pct"], -v["hedge_pct"], v["carry_net_pct"], v["mtm_pct_per_year"],
                     v["total_pct"], v["bear_pct"], f"{v['charge'][0]:.0%}~{v['charge'][1]:.0%}"] for c, v in rets["classes"].items()],
                   headers=["자산군", "base%", "spread%", "EL%", "헤지%", "순캐리%", "평가/년%", "총기대%", "Bear%", "K-ICS계수"]))
    for name, o in result["strategies"].items():
        print(f"\n[{name}] {o['status']}")
        if o["status"] != "ok":
            print("  ", o.get("message"))
            continue
        print("  Δ(%p):", o["deltas_pp"])
        print(f"  기대 총수익 +{o['delta_total_return_bp']}bp(+{o['delta_total_return_100m']:,.0f}억원/년), 순캐리 +{o['delta_carry_bp']}bp; "
              f"K-ICS {o['kics_now']}% → {o['kics_after']['high']}~{o['kics_after']['low']}%; 갭 {o['gap_before']}→{o['gap_after']}; "
              f"Bear Δ {o['bear_delta_100m']:,.0f}억원({o['bear_delta_bp']}bp)")
    print(f"\n저장: {out.with_suffix('.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
