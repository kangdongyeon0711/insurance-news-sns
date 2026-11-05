"""미국 국채·회사채 시나리오별 보유 손익 — 달러 기준과 원화 헤지 기준(국내 투자자) 비교.

python scripts/us_bond_outlook_calc.py --date 2026-11-05 [--out reports/tmp/2026-11-05_us_bond_outlook_calc.json]

입력:
- 현황 금리·스프레드: knowledge/macro_topics/{date 이하 최신}/us_treasury.json, us_corp_bond.json indicators (웹확인 값)
- 시나리오: 같은 폴더 us_treasury·us_corp_bond(장기 Base/Bull/Bear·확률, 단기 충격), fx_krwusd(헤지비용 충격)
- 하우스 경로: 신한 2027 채권전망 분기 전망표(20261102_신한_2027채권전망_NextChapter p.45) — HOUSE_PATH
- 가정(모두 추정): 수정듀레이션, 신용등급별 기대손실(EL), 헤지비용 기준값, 회사채 기준 국채 만기
손익 = 금리 캐리 − 듀레이션 × 금리 변화 − 스프레드 듀레이션 × 스프레드 변화 − 기대손실 (롤다운·볼록성 제외, 근사).
장기 시나리오(1~3년 충격)는 1년 보유 손익에 그대로 적용한 단순화다. 투자 권유가 아니다.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import KNOWLEDGE_DIR, TMP_REPORTS_DIR, load_json, save_json

DUR = {"UST2Y": 1.9, "UST10Y": 8.0, "IG": 6.8, "HY": 3.2}          # 수정듀레이션(추정, 지수 평균 수준)
KTB10_DUR = 8.3   # 국고 10년 수정듀레이션(bond_strategy_calc.DUR[10]과 같은 가정)
EL = {"IG": {"단기": 0.03, "Base": 0.10, "Bull": 0.05, "Bear": 0.30},   # 연 기대손실 %(가정: 부도율 × LGD)
      "HY": {"단기": 0.40, "Base": 1.50, "Bull": 1.00, "Bear": 4.00}}
HEDGE_COST = 0.915   # 연 %, FFR 중간값 3.875% − CD 3.26% + 베이시스 30bp(optimize_allocation 산식, 추정)
HOUSE_PATH = {"이름": "신한 4Q27 경로", "ust_2y": 4.40, "ust_10y": 4.70, "ffr_upper": 4.25,
              "peak_1q27": {"ust_2y": 4.70, "ust_10y": 5.10}, "page": "20261102_신한_2027채권전망_NextChapter p.45"}


def latest_topics(date: str) -> Path:
    ds = sorted(p for p in (KNOWLEDGE_DIR / "macro_topics").iterdir() if p.is_dir() and p.name[:2] == "20" and p.name <= date)
    return ds[-1]


def ind(topic: dict, sid: str) -> dict:
    return next(x for x in topic["current"]["indicators"] if x["series_id"] == sid)


def pnl(y: float, d: float, dy_bp: float, h: float, sd: float = 0.0, ds_bp: float = 0.0, el: float = 0.0) -> float:
    """보유기간 h년 손익(%, 원금 대비)"""
    return y * h - d * dy_bp / 100 - sd * ds_bp / 100 - el * h


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    tdir = latest_topics(a.date)
    ut, uc, fx = (load_json(tdir / f"{t}.json") for t in ("us_treasury", "us_corp_bond", "fx_krwusd"))
    y2, y10 = ind(ut, "ust_2y")["value"], ind(ut, "ust_10y")["value"]
    ig, hy = ind(uc, "us_ig_oas")["value"], ind(uc, "us_hy_oas")["value"]
    # 회사채 기준 국채 금리: IG(듀레이션 6.8) ≈ 10년, HY(3.2) ≈ 2년·10년 선형 보간(3.2년) — 근사
    base = {"UST2Y": y2, "UST10Y": y10, "IG": y10 + ig, "HY": y2 + (y10 - y2) * (3.2 - 2) / 8 + hy}
    sc_t = {s["name"]: s for s in ut["long_term"]["scenarios"]}
    sc_c = {s["name"]: s for s in uc["long_term"]["scenarios"]}
    sc_fx = {s["name"]: s for s in fx["long_term"]["scenarios"]}
    names = ["Base", "Bull", "Bear"]

    def rate_shock(fs: dict, key: str) -> float:
        b2, b10 = fs.get("ust_2y_bp", 0.0), fs.get("ust_10y_bp", 0.0)
        return {"UST2Y": b2, "UST10Y": b10, "IG": b10, "HY": b2 + (b10 - b2) * (3.2 - 2) / 8}[key]

    out = {"as_of": a.date, "topics": str(tdir), "levels": {"ust_2y": ind(ut, "ust_2y"), "ust_10y": ind(ut, "ust_10y"),
           "us_ig_oas": ind(uc, "us_ig_oas"), "us_hy_oas": ind(uc, "us_hy_oas")},
           "yields_pct": {k: round(v, 3) for k, v in base.items()}, "assumptions": {"duration": DUR, "el_pct": EL, "hedge_cost_pct": HEDGE_COST},
           "probs": {"treasury": {n: sc_t[n]["prob"] for n in names}, "credit": {n: sc_c[n]["prob"] for n in names}}}
    rows = {}
    for k in DUR:
        sd = DUR[k] if k in ("IG", "HY") else 0.0
        r = {}
        # 장기 시나리오: 1년 보유
        for n in names:
            dy = rate_shock(sc_t[n]["factor_shocks"], k)
            ds = sc_c[n]["factor_shocks"].get(f"us_{k.lower()}_oas_bp", 0.0) if sd else 0.0
            el = EL[k][n] if k in EL else 0.0
            usd = pnl(base[k], DUR[k], dy, 1.0, sd, ds, el)
            hc = HEDGE_COST + sc_fx[n]["factor_shocks"].get("fx_hedge_cost_bp", 0.0) / 100 / 2   # 1년 평균: 충격의 절반만 반영(점진 하락 가정)
            r[n] = {"rate_bp": dy, "spread_bp": ds, "usd_pct": round(usd, 2), "krw_hedged_pct": round(usd - hc, 2)}
        prob = out["probs"]["credit" if sd else "treasury"]
        r["EV"] = {m: round(sum(prob[n] * r[n][m] for n in names), 2) for m in ("usd_pct", "krw_hedged_pct")}
        # 단기(3개월) 충격
        dy = rate_shock(ut["short_term_factor_shocks"], k)
        ds = uc["short_term_factor_shocks"].get(f"us_{k.lower()}_oas_bp", 0.0) if sd else 0.0
        usd = pnl(base[k], DUR[k], dy, 0.25, sd, ds, EL[k]["단기"] * 4 if k in EL else 0.0)
        r["단기_3M"] = {"rate_bp": dy, "spread_bp": ds, "usd_pct": round(usd, 2),
                       "krw_hedged_pct": round(usd - (HEDGE_COST + fx["short_term_factor_shocks"].get("fx_hedge_cost_bp", 0) / 100) * 0.25, 2)}
        # 1년 손익분기: 금리(또는 스프레드) 상승 허용폭
        carry_h = base[k] - HEDGE_COST - (EL[k]["Base"] if k in EL else 0.0)
        r["breakeven_1y_bp"] = {"rate_usd": round((base[k] - (EL[k]["Base"] if k in EL else 0)) / DUR[k] * 100, 1),
                                "rate_krw_hedged": round(carry_h / DUR[k] * 100, 1)}
        if sd:   # 듀레이션 같은 국채 대비 초과수익: OAS − SD × ΔOAS − EL, 손익분기 스프레드 확대폭 = (OAS − EL) / SD
            oas = ig if k == "IG" else hy
            r["excess_vs_ust_pct"] = {n: round(oas - sd * r[n]["spread_bp"] / 100 - EL[k][n], 2) for n in names}
            r["excess_vs_ust_pct"]["EV"] = round(sum(prob[n] * r["excess_vs_ust_pct"][n] for n in names), 2)
            r["breakeven_1y_bp"]["spread_vs_ust"] = round((oas - EL[k]["Base"]) / sd * 100, 1)
        rows[k] = r
    # 하우스 경로(2027년 말)와 1분기 고점 경유 손익
    hp = HOUSE_PATH
    for k, key in (("UST2Y", "ust_2y"), ("UST10Y", "ust_10y")):
        dy_end = (hp[key] - base[k]) * 100
        dy_pk = (hp["peak_1q27"][key] - base[k]) * 100
        rows[k]["house_path"] = {"to_4q27_bp": round(dy_end, 1), "usd_1y_pct": round(pnl(base[k], DUR[k], dy_end, 1.0), 2),
                                 "krw_hedged_1y_pct": round(pnl(base[k], DUR[k], dy_end, 1.0) - HEDGE_COST, 2),
                                 "to_1q27_peak_bp": round(dy_pk, 1), "usd_to_peak_3m_pct": round(pnl(base[k], DUR[k], dy_pk, 0.25), 2),
                                 "buy_at_peak_1y_usd_pct": round(pnl(hp["peak_1q27"][key], DUR[k], (hp[key] - hp["peak_1q27"][key]) * 100, 0.75), 2)}
    # 비교: 국고 10년 1년 보유(원화) — kr_govt_bond 시나리오
    kg = load_json(tdir / "kr_govt_bond.json"); k10 = ind(kg, "ktb_10y")["value"]
    sk = {s["name"]: s for s in kg["long_term"]["scenarios"]}
    kr = {n: {"rate_bp": sk[n]["factor_shocks"]["ktb_10y_bp"], "krw_pct": round(pnl(k10, KTB10_DUR, sk[n]["factor_shocks"]["ktb_10y_bp"], 1.0), 2)} for n in names}
    kr["EV"] = {"krw_pct": round(sum(sk[n]["prob"] * kr[n]["krw_pct"] for n in names), 2)}
    kr["단기_3M"] = {"rate_bp": kg["short_term_factor_shocks"]["ktb_10y_bp"], "krw_pct": round(pnl(k10, KTB10_DUR, kg["short_term_factor_shocks"]["ktb_10y_bp"], 0.25), 2)}
    out["ktb10_compare"] = {"level": ind(kg, "ktb_10y"), "probs": {n: sk[n]["prob"] for n in names}, **kr}
    out["rows"] = rows
    out["house_path"] = hp
    out["curve"] = {"2s10s_now_bp": round((y10 - y2) * 100, 1), "2s10s_house_4q27_bp": round((hp["ust_10y"] - hp["ust_2y"]) * 100, 1),
                    "2s10s_our_base_bp": round((y10 - y2) * 100 + sc_t["Base"]["factor_shocks"]["ust_10y_bp"] - sc_t["Base"]["factor_shocks"]["ust_2y_bp"], 1)}
    p = Path(a.out) if a.out else TMP_REPORTS_DIR / f"{a.date}_us_bond_outlook_calc.json"
    save_json(p, out)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
