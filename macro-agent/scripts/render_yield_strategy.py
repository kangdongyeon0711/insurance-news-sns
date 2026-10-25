"""운용수익률 제고 전략 리포트 골격 (optimize_allocation·opt_sensitivity 결과 + 손익 분해 → Markdown).

python scripts/render_yield_strategy.py --company 현대해상 --date 2026-10-25 \
    [--opt reports/tmp/{date}_{회사}_opt.json] [--opt3y reports/tmp/{date}_{회사}_opt_3y.json] \
    [--sens reports/tmp/{date}_{회사}_opt_sens.json] [--income knowledge/portfolios/{회사}/income_1H26.json] [--force]

표는 JSON에서 결정적으로 만들고, 해석·제안은 <!-- TODO --> 자리로 남긴다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common import KNOWLEDGE_DIR, REPORTS_DIR, TMP_REPORTS_DIR, load_json
from render_portfolio import PF_DISCLAIMER

ORDER = ["현금예금", "국공채", "특수채", "회사채", "대출-기업", "대출-부동산담보", "대체-사모대출", "대체-인프라", "부동산", "대체-PE",
         "해외채", "주식", "수익증권"]


def f0(v) -> str:
    return "—" if v is None else f"{v:,.0f}"


def kics_range(k: dict | None) -> str:
    if not k:
        return "—"
    lo, hi = sorted([k["low"], k["high"]])
    return f"{lo}~{hi}%"


def strategy_table(L, strategies: dict, title: str) -> None:
    a = L.append
    names = [n for n, o in strategies.items() if o.get("status") == "ok"]
    a(f"**{title} — 자산군별 배분 변화 (%p, 운용자산 대비)**\n")
    a("| 자산군 | " + " | ".join(names) + " |")
    a("|---|" + "---|" * len(names))
    for c in ORDER:
        vals = [strategies[n]["deltas_pp"].get(c) for n in names]
        if all(v is None for v in vals):
            continue
        a(f"| {c} | " + " | ".join("—" if v is None else f"{v:+.2f}" for v in vals) + " |")
    a("")
    a("**결과 지표**\n")
    a("| 지표 | " + " | ".join(names) + " |")
    a("|---|" + "---|" * len(names))
    rows = [
        ("기대 총수익 개선 (bp/년)", lambda o: f"+{o['delta_total_return_bp']}"),
        ("기대 총수익 개선 (억원/년)", lambda o: f"+{f0(o['delta_total_return_100m'])}"),
        ("순캐리 개선 (bp/년)", lambda o: f"+{o['delta_carry_bp']}"),
        ("이동 규모 (십억원, 매수 합계)", lambda o: f0(o.get("turnover_krw_bn"))),
        ("K-ICS (현재 → 후, 위험계수 범위)", lambda o: f"{o['kics_now']}% → {kics_range(o['kics_after'])}"),
        ("공시 기준 듀레이션 갭 (년)", lambda o: f"{o['gap_before']} → {o['gap_after']}"),
        ("Bear 손실 변화 (억원 / bp)", lambda o: f"{f0(o['bear_delta_100m'])} / {o['bear_delta_bp']:+}"),
    ]
    for label, fn in rows:
        a(f"| {label} | " + " | ".join(fn(strategies[n]) if strategies[n].get("kics_now") is not None or "K-ICS" not in label else "—"
                                       for n in names) + " |")
    if all("scenarios_after" in strategies[n] for n in names):
        for sc in ("장기-Base", "장기-Bear"):
            a(f"| 조정 후 {sc} 평가손익 (억원, 엔진 / 공시보정) | " + " | ".join(
                f"{f0(strategies[n]['scenarios_after'][sc]['total_100m'])} / {f0(strategies[n]['scenarios_after'][sc]['calibrated_100m'])}"
                for n in names) + " |")
    a("")


def render(company: str, date: str, opt: dict, opt3y: dict | None, sens: dict | None, inc: dict | None) -> str:
    L: list[str] = []
    a = L.append
    a(f"# {company} 운용수익률 제고 전략 — {date}\n")
    a(f"> 익스포저 {opt['period']} 공시 기준 · 매크로 시나리오 {date} (`build_shocks.py` 결합) · 신규 자금 기대수익은 "
      "`config/yield_assumptions.yaml`(시장 수치는 수기·웹확인, 스프레드·기대손실·K-ICS 계수는 가정) · 금액 억원 · 투자 권유 아님\n")
    a("## 요약\n")
    a("<!-- TODO: 핵심 결론 5줄 ([사실]/[하우스]/[판단]) -->\n")

    if inc:
        a("## 1. 진단 — 운용수익률은 어디서 새는가\n")
        a(f"공시 투자손익(보험금융손익 제외) 분해 · 단위 십억원 · 연환산 수익률 = 1H × 2 ÷ 평균 운용자산 {inc['avg_invested_assets_krw_bn']:,.1f}십억원 "
          f"({inc['avg_basis']}) · 출처 `{inc['source']}`\n")
        a("| 구성 | 1H25 | 1H26 | 증감 | 1H26 연환산 기여 |")
        a("|---|---|---|---|---|")
        for k, v in inc["components"].items():
            a(f"| {k} | {v['1H25']:,.1f} | {v['1H26']:,.1f} | {v['1H26'] - v['1H25']:+,.1f} | {v['annualized_yield_pct_1H26']:+.2f}% |")
        a(f"| **투자손익 합계** | **{inc['total_1H25']:,.1f}** | **{inc['total_1H26']:,.1f}** | {inc['total_1H26'] - inc['total_1H25']:+,.1f} | "
          f"{inc['total_1H26'] * 2 / inc['avg_invested_assets_krw_bn'] * 100:.2f}% |")
        a(f"\n파생·외환 순손실을 평균 외화유가증권({inc['foreign_securities_avg_krw_bn']:,.1f}십억원)으로 나누면 연 {inc['fx_deriv_drag_vs_foreign_pct']}%. "
          f"기타포괄손익 {inc['oci_krw_bn_2026_06']:,.1f}십억원({inc['oci_source']}).\n")
        a("<!-- TODO: 진단 해석 -->\n")

    inp = opt["inputs"]
    a("## 2. 신규 자금 기준 자산군별 기대수익과 자본 효율\n")
    hc = inp["hedge_cost"]
    a(f"헤지비용(연) {hc['value']}% — {hc['note']}\n")
    base_ret = inp["classes"]["국공채"]["total_pct"]
    a("| 자산군 | 시장 base | 스프레드 | 기대손실 | 헤지 | 순캐리 | 평가변화/년 | **기대 총수익** | Bear 시나리오 | K-ICS 계수 | 국공채 대비 초과수익 ÷ 자본(중간값) | 근거 |")
    a("|---|---|---|---|---|---|---|---|---|---|---|---|")
    div = opt.get("diversification", 0.7)
    for c in ORDER:
        v = inp["classes"].get(c)
        if not v:
            continue
        mid = (v["charge"][0] + v["charge"][1]) / 2 * div
        eff = "—" if mid == 0 else f"{(v['total_pct'] - base_ret) / (mid * 100):+.2f}"
        a(f"| {c} | {v['base_pct']}% | {v['spread_pct']:+.2f} | −{v['el_pct']} | −{v['hedge_pct']} | {v['carry_net_pct']}% | {v['mtm_pct_per_year']:+.2f} | "
          f"**{v['total_pct']}%** | {v['bear_pct']:+.1f}% | {v['charge'][0]:.0%}~{v['charge'][1]:.0%} | {eff} | {v['source']} |")
    a("\n평가변화/년 = 이번 주 장기 시나리오(Base/Bull/Bear 확률가중) 평가손익 ÷ 2년. 초과수익 ÷ 자본 = (기대 총수익 − 국공채) ÷ (K-ICS 계수 중간값 × 분산효과) — "
      "자본 1단위당 추가 수익(%p). K-ICS 계수: 주식 35%·기타주식 48%·부동산 25%는 웹확인(2차 출처), 나머지는 가정 범위.\n")
    a("<!-- TODO: 자본 효율 해석 -->\n")

    a("## 3. 최적 배분 — 1년 실행안\n")
    a("목표: 기대 총수익 최대화. 제약: 자금 중립, 자산군별 연간 조정 한도(`class_bounds_pp`), 현금 하한, 대체투자 상한, "
      "K-ICS 하한(위험계수 상단 기준), 공시 듀레이션 갭 범위, Bear 손실 추가 허용폭.\n")
    a("| 전략 | K-ICS 하한 | 대체 상한 | Bear 추가 허용 | 현금 하한 | 갭 범위 |")
    a("|---|---|---|---|---|---|")
    for n, o in opt["strategies"].items():
        c = o["constraints"]
        a(f"| {n} | {c['kics_floor'] * 100:.0f}% | {c['alt_cap']:.0%} | {c['bear_extra_bp']}bp | {c['cash_min']:.1%} | {c['gap_range']} |")
    a("")
    strategy_table(L, opt["strategies"], "1년")
    a("<!-- TODO: 1년 실행안 해석·권고 전략 -->\n")

    if opt3y:
        a("## 4. 3년 누적 경로\n")
        a(f"> {opt3y.get('note', '')}\n")
        strategy_table(L, opt3y["strategies"], "3년 누적")
        alt = {n: o.get("alt_share_after") for n, o in opt3y["strategies"].items()}
        a("대체투자 비중(3년 후): " + ", ".join(f"{n} {v}%" for n, v in alt.items()) + "\n")
        a("<!-- TODO: 3년 경로 해석 -->\n")

    if sens:
        a("## 5. 가정 민감도\n")
        a("| 가정 변형 | 전략 | 총수익 +bp | 캐리 +bp | K-ICS 후 | Bear Δbp | 주요 증가 자산군 (%p) |")
        a("|---|---|---|---|---|---|---|")
        for v, d in sens.items():
            for s, o in d.items():
                dp = o.get("deltas_pp") or {}
                top = ", ".join(f"{k} {x:+.1f}" for k, x in sorted(dp.items(), key=lambda kv: -kv[1])[:4] if x > 0)
                a(f"| {v} | {s} | {o['delta_total_return_bp']} | {o['delta_carry_bp']} | {kics_range(o.get('kics_after'))} | {o['bear_delta_bp']} | {top} |")
        a("\n<!-- TODO: 민감도 해석 -->\n")

    a("## 6. 배분 외 레버\n")
    a("<!-- TODO: 헤지·평가손익 변동성·비용·현금·ALM·자본 레버 -->\n")
    a("## 7. 기사에 나온 전략 평가\n")
    a("<!-- TODO: 자회사 활용 대체투자(부동산 대출형 사모펀드, 시니어하우징) 평가 -->\n")
    a("## 8. 매크로 연계 실행 순서와 점검 트리거\n")
    a("<!-- TODO: 실행 순서·트리거 -->\n")
    a("## 9. 한계와 가정\n")
    a("<!-- TODO: 한계 -->\n")
    a("---\n")
    a(f"**면책**: {PF_DISCLAIMER}\n")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--opt")
    ap.add_argument("--opt3y")
    ap.add_argument("--sens")
    ap.add_argument("--income")
    ap.add_argument("--out")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    pre = TMP_REPORTS_DIR / f"{args.date}_{args.company}"
    opt = load_json(Path(args.opt or f"{pre}_opt.json"))
    opt3y = load_json(Path(args.opt3y or f"{pre}_opt_3y.json")) if Path(args.opt3y or f"{pre}_opt_3y.json").exists() else None
    sens = load_json(Path(args.sens or f"{pre}_opt_sens.json")) if Path(args.sens or f"{pre}_opt_sens.json").exists() else None
    ip = Path(args.income) if args.income else next(iter(sorted((KNOWLEDGE_DIR / "portfolios" / args.company).glob("income_*.json"))), None)
    inc = load_json(ip) if ip and ip.exists() else None
    out = Path(args.out) if args.out else REPORTS_DIR / f"{args.date}_{args.company}_yield_strategy.md"
    if out.exists() and not args.force:
        print(f"이미 존재: {out} — 덮어쓰려면 --force")
        return 1
    out.write_text(render(args.company, args.date, opt, opt3y, sens, inc), encoding="utf-8")
    print(f"저장: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
