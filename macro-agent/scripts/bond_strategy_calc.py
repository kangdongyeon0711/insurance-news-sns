"""국내 채권 전략 비교 계산 — 캐리·롤다운·시나리오 기대값(국고채 아웃라이트·커브, 회사채 만기·스프레드 손익분기).

python scripts/bond_strategy_calc.py --date 2026-10-27 [--out reports/tmp/2026-10-27_kr_bond_strategy_calc.json]

입력:
- 금리 커브: 신한 Weekly Credit Monitor(2026-10-27) p.2 금리·스프레드 표(10월 23일 기준, 인포맥스) — 리포트 수치(하우스 자료의 시장 데이터)
- 시나리오: knowledge/macro_topics/{date 이하 최신}/kr_govt_bond.json, kr_corp_bond.json(장기 Base/Bull/Bear·확률, 단기 충격)
- 가정(모두 추정): 조달금리, 수정듀레이션, 5년물 충격(3년·10년 선형 보간)
모든 값은 근사 계산이며 투자 권유가 아니다.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import KNOWLEDGE_DIR, TMP_REPORTS_DIR, load_json, save_json

CURVE = {  # %, 2026-10-23, 신한 Weekly Credit Monitor 2026-10-27 p.2
    "KTB": {1: 3.57, 2: 3.76, 3: 3.809, 5: 3.96, 10: 4.110},
    "회사채AA-": {2: 4.43, 3: 4.49, 5: 4.60},
    "회사채AA+": {2: 4.35, 3: 4.40, 5: 4.43},
    "회사채AA0": {2: 4.38, 3: 4.44, 5: 4.50},
    "은행채AAA": {2: 4.13, 3: 4.20, 5: 4.28},
    "특수채AAA": {2: 4.10, 3: 4.17, 5: 4.26},
    "여전채AA-": {2: 4.50, 3: 4.55, 5: 4.67},
}
SPREAD_3_5 = {  # 국고 대비 신용스프레드(bp, 3·5년), 같은 표
    "회사채AA-": (68.0, 63.7), "회사채AA+": (59.0, 47.1), "회사채AA0": (63.0, 53.7),
    "은행채AAA": (39.1, 32.3), "특수채AAA": (36.4, 30.4), "여전채AA-": (74.4, 70.6),
}
DUR = {1: 0.95, 2: 1.9, 3: 2.8, 5: 4.5, 10: 8.3}   # 수정듀레이션(추정)
FUND_3M = 3.20    # 향후 3개월 평균 조달금리(콜 3.03% + 11월 인상 일부 반영, 추정)
FUND_1Y = 3.40    # 향후 1년 평균 조달금리(최종 3.50% 경로, 추정)


def yld(curve: dict, t: float) -> float:
    ks = sorted(curve)
    if t <= ks[0]:
        return curve[ks[0]]
    for a, b in zip(ks, ks[1:]):
        if a <= t <= b:
            return curve[a] + (curve[b] - curve[a]) * (t - a) / (b - a)
    return curve[ks[-1]]


def carry_roll(curve: dict, t: int, h: float, fund: float) -> float:
    """보유기간 h년의 캐리+롤다운(%, 원금 대비): (금리−조달)×h + (현재금리−h년 뒤 잔존만기 금리)×잔존듀레이션"""
    return (curve[t] - fund) * h + (curve[t] - yld(curve, t - h)) * DUR[t] * (t - h) / t


def latest_topics(date: str) -> Path:
    ds = sorted(p for p in (KNOWLEDGE_DIR / "macro_topics").iterdir() if p.is_dir() and p.name[:2] == "20" and p.name <= date)
    return ds[-1]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    tdir = latest_topics(a.date)
    gb, cb = load_json(tdir / "kr_govt_bond.json"), load_json(tdir / "kr_corp_bond.json")
    sc = {s["name"]: s for s in gb["long_term"]["scenarios"]}
    cs = {s["name"]: s for s in cb["long_term"]["scenarios"]}
    names = ["Base", "Bull", "Bear"]
    prob = {n: sc[n]["prob"] for n in names}
    # 국고 충격(bp): 3·10년은 시나리오값, 5년은 3·10년 선형 보간(추정), 2년은 3년과 같다고 가정(추정)
    def shocks(fs: dict) -> dict:
        s3, s10 = fs["ktb_3y_bp"], fs["ktb_10y_bp"]
        return {2: s3, 3: s3, 5: s3 + (s10 - s3) * 2 / 7, 10: s10}
    lt = {n: shocks(sc[n]["factor_shocks"]) for n in names}
    st = shocks(gb["short_term_factor_shocks"])
    out = {"as_of_curve": "2026-10-23", "topics": str(tdir), "probs": prob, "assumptions": {"fund_3m": FUND_3M, "fund_1y": FUND_1Y, "duration": DUR,
           "note": "5년 충격은 3·10년 선형 보간, 2년 충격은 3년과 동일(추정). 1년 보유 손익에 1~3년 시나리오 충격을 그대로 적용(단순화)"}}

    # 1) 국고 아웃라이트: 1년 보유 초과수익(조달 대비, bp) — 시나리오별·기대값·표준편차
    ktb = CURVE["KTB"]
    outr = {}
    for t in (2, 3, 5, 10):
        cr = carry_roll(ktb, t, 1.0, FUND_1Y) * 100
        res = {n: round(cr - lt[n][t] * DUR[t], 1) for n in names}
        ev = sum(prob[n] * res[n] for n in names)
        sd = sum(prob[n] * (res[n] - ev) ** 2 for n in names) ** 0.5
        outr[f"{t}Y"] = {"carry_roll_bp": round(cr, 1), "scenarios_bp": res, "ev_bp": round(ev, 1), "sd_bp": round(sd, 1), "ev_per_sd": round(ev / sd, 2)}
    out["ktb_outright_1y"] = outr

    # 2) 커브(DV01 중립): 3s10s 플래트너, 5s10s 스티프너 — 캐리·롤다운(3개월·1년)과 시나리오 손익(bp of curve)
    def curve_trade(short_t: int, long_t: int, flattener: bool) -> dict:
        # 플래트너 = 단기물 매도·장기물 매수(장기물 DV01 1단위 기준). 스티프너는 반대.
        sign = 1 if flattener else -1
        def cr_spread(h, fund):
            cl = carry_roll(ktb, long_t, h, fund) / DUR[long_t] * 100
            cs_ = carry_roll(ktb, short_t, h, fund) / DUR[short_t] * 100
            return sign * (cl - cs_)
        res_lt = {n: round(sign * (lt[n][short_t] - lt[n][long_t]), 1) for n in names}
        ev = sum(prob[n] * res_lt[n] for n in names)
        return {"carry_roll_3m_bp": round(cr_spread(0.25, FUND_3M), 1), "carry_roll_1y_bp": round(cr_spread(1.0, FUND_1Y), 1),
                "short_term_move_bp": round(sign * (st[short_t] - st[long_t]), 1),
                "scenarios_move_bp": res_lt, "ev_move_bp": round(ev, 1),
                "ev_total_1y_bp": round(ev + cr_spread(1.0, FUND_1Y), 1),
                "spread_now_bp": round((ktb[long_t] - ktb[short_t]) * 100, 1)}
    out["curve"] = {"3s10s_flattener": curve_trade(3, 10, True), "5s10s_steepener": curve_trade(5, 10, False),
                    "3s5s10s_fly_bp": round((2 * ktb[5] - ktb[3] - ktb[10]) * 100, 1),
                    "segment_slope_bp_per_year": {"2-3Y": round((ktb[3] - ktb[2]) * 100, 1), "3-5Y": round((ktb[5] - ktb[3]) * 100 / 2, 1),
                                                  "5-10Y": round((ktb[10] - ktb[5]) * 100 / 5, 1)}}

    # 3) 크레딧: 만기 연장 보상 분해(금리 기간 프리미엄 vs 신용스프레드), 1년 스프레드 손익분기, AA 시나리오 초과수익
    cr = {}
    for k, c in CURVE.items():
        if k == "KTB":
            continue
        s3, s5 = SPREAD_3_5[k]
        ext = {"2→3Y_yield_bp": round((c[3] - c[2]) * 100, 1), "3→5Y_yield_bp": round((c[5] - c[3]) * 100, 1),
               "3→5Y_KTB_bp": round((ktb[5] - ktb[3]) * 100, 1), "3→5Y_spread_change_bp": round(s5 - s3, 1)}
        be = round(s3 / (DUR[3] - 0.9), 1)   # 1년 뒤 잔존 2년, 스프레드 듀레이션 약 1.9
        res = {}
        if k.startswith("회사채AA"):
            for n in names:
                ds = cs[n]["factor_shocks"]["kr_aa_spread_bp"]
                res[n] = round(s3 - ds * (DUR[3] - 0.9) + (c[3] - c[2] - (ktb[3] - ktb[2])) * 100 * 1.9, 1)  # 스프레드 캐리 + 스프레드 변화 + 스프레드 롤다운
        cr[k] = {"extension": ext, "spread_3y_bp": s3, "spread_5y_bp": s5, "breakeven_widening_1y_bp": be,
                 **({"excess_vs_ktb_1y_bp": res, "ev_bp": round(sum(prob[n] * res[n] for n in names), 1)} if res else {})}
    out["credit"] = cr
    p = Path(a.out) if a.out else TMP_REPORTS_DIR / f"{a.date}_kr_bond_strategy_calc.json"
    save_json(p, out)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
