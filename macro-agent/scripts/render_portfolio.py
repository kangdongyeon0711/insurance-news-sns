"""calc_impact 결과 + 익스포저(전 기간) → 포트폴리오 영향 리포트 Markdown 골격.

python scripts/render_portfolio.py --impact reports/tmp/2026-10-25_현대해상_impact.json \
    --portfolio-dir knowledge/portfolios/현대해상/ [--out ...] [--force]

수치 표는 impact JSON에서 그대로 옮긴다(* = 추정 포함 셀). 해석·제안은 <!-- TODO --> 자리로 남긴다.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from common import CONFIG_DIR, REPORTS_DIR, class_order, load_json, load_yaml, today
from render_brief import DISCLAIMER
from validate_exposures import class_weights, ifrs_break, period_key


def f0(v) -> str:
    return "—" if v is None else f"{v:,.0f}"


def render(impact: dict, portfolios: list[dict], date: str) -> str:
    L: list[str] = []
    a = L.append
    co = impact["company"]
    latest = portfolios[-1] if portfolios else None
    a(f"# {co} 포트폴리오 매크로 영향 분석 — {date}\n")
    if impact.get("is_sample"):
        a("> ⚠ **가상 샘플 포트폴리오** — 실제 회사 데이터가 아닙니다. 계산·리포트 흐름 시연용입니다.\n")
    a(f"> 익스포저 기준 {impact['period']} · 매크로 충격 기준일 {impact.get('shocks_as_of')} ({impact.get('shocks_source')}) · "
      f"금액 단위 억원, bp = 운용자산 대비 · `*` = 가정/추정값 포함 · 평가 기준: {impact.get('valuation_basis')}\n")
    scen = impact["scenarios"]
    pw = impact.get("prob_weighted")

    a("## 요약\n")
    a("| 시나리오 | 확률 | 운용자산 평가손익 (억원) | 운용자산 대비 (bp) | 추정 포함 |")
    a("|---|---|---|---|---|")
    for s in scen:
        p = "—" if s["prob"] is None else f"{s['prob']:g}"
        a(f"| {s['name']} | {p} | {f0(s['total_100m'])} | {s['total_bp']:+.1f} | {'예' if s['any_estimated'] else '아니오'} |")
    if pw:
        a(f"| 확률가중 기대값 ({'/'.join(pw['scenarios'])}) | — | {f0(pw['total_100m'])} | {pw['total_bp']:+.1f} | 예 |")
    # 취약 자산군: 확률 있는 시나리오 중 최악, 없으면 전체 시나리오 중 최악 손실(억원) 기준
    pool = [s for s in scen if s["prob"] is not None] or scen
    worst: dict[str, float] = defaultdict(float)
    worst_sc: dict[str, str] = {}
    for s in pool:
        for r in s["rows"]:
            if r["impact_100m"] < worst[r["key"]]:
                worst[r["key"]], worst_sc[r["key"]] = r["impact_100m"], s["name"]
    top3 = sorted((k for k in worst if worst[k] < 0), key=lambda k: worst[k])[:3]
    a("\n**가장 취약한 자산군 3개** (시나리오별 최대 손실 기준)\n")
    for k in top3:
        a(f"- {k}: {f0(worst[k])}억원 ({worst_sc[k]})")
    if not top3:
        a("- 손실이 계산된 자산군 없음")
    a("\n**핵심 제안 3가지**\n")
    a("<!-- TODO: 리밸런싱 제안 섹션의 결론 3개를 한 줄씩 ([판단] 태그) -->\n")

    a("## 포트폴리오 현황\n")
    if latest:
        a(f"총 운용자산 {latest['total_invested_assets_krw_bn'] / 1000:,.1f}조원 ({latest['period']}, "
          f"{latest.get('total_flag', '공시')}{', ' + latest['total_page_ref'] if latest.get('total_page_ref') else ''}) · "
          f"회계기준 {latest['accounting_basis']} · K-ICS {latest.get('kics_ratio') or '미확인'} · "
          f"운용수익률 {latest.get('investment_yield') or '미확인'}\n")
        a("| 자산군 | 지역 | 통화 | 금액 (십억원) | 비중 | 수정듀레이션 | 헤지비율 | 값 플래그 | 근거 |")
        a("|---|---|---|---|---|---|---|---|---|")
        for x in sorted(latest["assets"], key=lambda x: class_order(x["class"])):
            ff = x.get("field_flags") or {}
            dur = "—" if x.get("mod_duration") is None else f"{x['mod_duration']:g}{' (추정)' if ff.get('mod_duration') == '추정' else ''}"
            h = "—" if x.get("fx_hedge_ratio") is None else f"{x['fx_hedge_ratio']:.0%}"
            a(f"| {x['class']}{' · ' + x['label'] if x.get('label') else ''} | {x['region']} | {x['currency']} | "
              f"{x['mv_krw_bn']:,.0f} | {x['weight']:.1%} | {dur} | {h} | {x['value_flag']} | {x.get('page_ref') or '—'} |")
    if len(portfolios) > 1:
        a("\n**비중 추이 (%)**\n")
        classes = sorted({x["class"] for p in portfolios for x in p["assets"]}, key=class_order)
        hdr = [p["period"] + (" ⚠" if i and ifrs_break(portfolios[i - 1]["period"], p["period"]) else "")
               for i, p in enumerate(portfolios)]
        a("| 자산군 | " + " | ".join(hdr) + " |")
        a("|---|" + "---|" * len(hdr))
        cw = [class_weights(p) for p in portfolios]
        for c in classes:
            a(f"| {c} | " + " | ".join(f"{w.get(c, 0):.1f}" for w in cw) + " |")
        a("| 총 운용자산(조원) | " + " | ".join(f"{p['total_invested_assets_krw_bn'] / 1000:,.1f}" for p in portfolios) + " |")
        if any(ifrs_break(x["period"], y["period"]) for x, y in zip(portfolios, portfolios[1:])):
            a("\n⚠ 표시 구간은 IFRS17·IFRS9 도입(2023) 전후로 계정 분류가 달라 직접 비교에 주의.")
    a("\n**운용 전략 해석**\n")
    a("<!-- TODO: portfolio-analyst의 추이 해석을 [사실](수치 변화)/[판단](의도 해석)으로 정리 -->\n")

    a("## 매크로 → 포트폴리오 영향\n")
    a("**시나리오 × 자산군 영향 (억원)**\n")
    names = [s["name"] for s in scen] + (["확률가중"] if pw else [])
    a("| 자산군 | 금액 (십억원) | " + " | ".join(names) + " |")
    a("|---|---|" + "---|" * len(names))
    for i, r0 in enumerate(scen[0]["rows"]):
        cells = [f"{s['rows'][i]['impact_100m']:,.0f}{'*' if s['rows'][i]['estimated'] else ''}" for s in scen]
        if pw:
            est = any(s["rows"][i]["estimated"] for s in scen if s["prob"] is not None)
            cells.append(f"{pw['rows'][i]['impact_100m']:,.0f}{'*' if est else ''}")
        a(f"| {r0['key']} | {r0['mv_krw_bn']:,.0f} | " + " | ".join(cells) + " |")
    tot = [f"**{s['total_100m']:,.0f}**" for s in scen] + ([f"**{pw['total_100m']:,.0f}**"] if pw else [])
    bps = [f"{s['total_bp']:+.1f}" for s in scen] + ([f"{pw['total_bp']:+.1f}"] if pw else [])
    a("| **합계** | " + f"{impact['total_invested_assets_krw_bn']:,.0f} | " + " | ".join(tot) + " |")
    a("| 운용자산 대비 (bp) | | " + " | ".join(bps) + " |")
    a("\n**요인 분해 (억원)** — rate=금리, spread=스프레드, fx=환율(비헤지분), hedge_cost=헤지비용, 기타는 자산군별 팩터\n")
    a("| 시나리오 | " + " | ".join(["rate", "spread", "fx", "hedge_cost", "equity", "cap_rate", "credit_loss", "discount_rate",
                                     "valuation", "floating_income"]) + " |")
    a("|---|" + "---|" * 10)
    for s in scen:
        comp: dict[str, float] = defaultdict(float)
        for r in s["rows"]:
            for k, v in r["components_100m"].items():
                comp[k] += v
        a(f"| {s['name']} | " + " | ".join(f0(comp.get(k)) if k in comp else "—" for k in
                                         ["rate", "spread", "fx", "hedge_cost", "equity", "cap_rate", "credit_loss",
                                          "discount_rate", "valuation", "floating_income"]) + " |")
    miss = {s["name"]: s["missing_factors"] for s in scen if s["missing_factors"]}
    if miss:
        a("\n0으로 처리한 팩터 (시나리오에 값 없음): " + "; ".join(f"{k}: {', '.join(v)}" for k, v in miss.items()))
    a("\n**영향 경로 설명**\n")
    a("<!-- TODO: impact-mapping/sensitivity_matrix.md 기준으로 주요 경로와 계산이 포착하지 못한 정성 영향(PF 충당금 시차, "
      "대체투자 평가 지연, 회계 분류에 따른 손익 인식 차이)을 서술 -->\n")

    a("## ALM 관점\n")
    alms = [(s["name"], s["alm"]) for s in scen if s.get("alm")]
    if alms:
        a("| 시나리오 | 금리 팩터 | Δy (bp) | 자산 (억원) | 부채 (억원) | 순자산 (억원) | 순자산 (bp) | 듀레이션 갭 (년) | 추정 |")
        a("|---|---|---|---|---|---|---|---|---|")
        for n, x in alms:
            a(f"| {n} | `{x['rate_factor']}` | {x['dy_bp']:+g} | {f0(x['asset_100m'])} | {f0(x['liability_100m'])} | "
              f"{f0(x['net_100m'])} | {x['net_bp']:+.1f} | {x['duration_gap_years']} | {'예' if x['estimated'] else '아니오'} |")
        x = alms[0][1]
        a(f"\nD_A {x['D_A']}년 (운용자산 대비, 금리민감 자산만), D_L {x['D_L']}년, L {x['L_krw_bn']:,.0f}십억원. "
          "단일 금리 팩터 근사이며 IFRS17 할인율(유동성 프리미엄·LTFR)과 CSM 흡수 효과는 반영하지 않음.\n")
        a("<!-- TODO: 갭의 부호에 따른 금리 하락/상승 시 순자산 방향과 K-ICS 금리위험 시사점을 정성 서술 -->\n")
    else:
        a("부채 듀레이션 또는 금리민감 부채 규모가 공시에서 확인되지 않아(미확인) 순자산 영향은 계산하지 않음. "
          "정기경영공시의 금리위험·ALM 항목을 inbox/filings에 추가하면 보강됨.\n")

    a("## 리밸런싱 제안\n")
    cons = impact.get("constraints_current")
    if cons:
        a("**현재 제약 점검** (`config/constraints.yaml`)\n")
        a("| 제약 | 현재 | min | max | 판정 |")
        a("|---|---|---|---|---|")
        for c in cons:
            v = c["value"]
            vs = "미확인" if v is None else (f"{v:.1%}" if "년" not in c["name"] and "조정폭" not in c["name"] else f"{v:g}")
            judge = {True: "충족", False: "**위반**", None: "미확인"}[c["ok"]]
            a(f"| {c['name']} | {vs} | {c['min'] if c['min'] is not None else '—'} | {c['max'] if c['max'] is not None else '—'} | {judge} |")
        a("")
    step = load_yaml(CONFIG_DIR / "constraints.yaml").get("max_step_pp")
    a(f"<!-- TODO: 아래 표를 채운다. 폭은 %p 범위, 1회 최대 {step}%p. 제안안을 proposal.json으로 저장해 "
      "`calc_impact.py --proposal`로 제약 충족 여부를 확인하고 결과를 '제약' 열에 기입 -->\n")
    a("| 자산군 | 방향 | 폭 (%p) | 근거 | 실행 시 리스크 | 제약 충족 |")
    a("|---|---|---|---|---|---|")
    a("| | 확대/축소/유지 | | | | |\n")

    a("## 한계와 가정\n")
    reasons: dict[str, set] = defaultdict(set)
    for s in scen:
        for r in s["rows"]:
            for x in r["estimated_reasons"]:
                reasons[r["key"]].add(x)
    if reasons:
        a("**추정·가정값을 쓴 항목** (`config/assumptions.yaml` — 모두 가정)\n")
        for k, v in reasons.items():
            a(f"- {k}: {', '.join(sorted(v))}")
    if latest and latest.get("notes"):
        a(f"\n**익스포저 메모**: {latest['notes']}")
    a("\n- 평가손익은 경제적 가치(공정가치) 기준이며, AC 분류 채권·원가모형 부동산 등은 회계상 손익과 다름.")
    a("- 팩터 간 상관과 2차 효과(유가 → 물가 → 금리 등)는 시나리오 작성 단계에서만 반영되며 계산 엔진은 선형 합산.")
    a("- K-ICS 요구자본 영향은 위험계수 미입력(`assumptions.kics.verified: false`)으로 정성 서술만 가능.")
    a("\n---\n")
    a(f"**면책**: {DISCLAIMER}\n")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--impact", required=True)
    ap.add_argument("--portfolio-dir", help="회사 익스포저 폴더 (모든 기간). 생략 시 --portfolio 단일 파일")
    ap.add_argument("--portfolio", help="단일 익스포저 파일")
    ap.add_argument("--date", default=today().isoformat())
    ap.add_argument("--out")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    impact = load_json(Path(args.impact))
    files = sorted(Path(args.portfolio_dir).glob("*.json")) if args.portfolio_dir else ([Path(args.portfolio)] if args.portfolio else [])
    portfolios = sorted((load_json(f) for f in files), key=lambda d: period_key(d["period"]))
    out = Path(args.out) if args.out else REPORTS_DIR / f"{args.date}_{impact['company']}_portfolio_impact.md"
    if out.exists() and not args.force:
        print(f"이미 존재: {out} — 덮어쓰려면 --force (사용자 확인 후)")
        return 1
    out.write_text(render(impact, portfolios, args.date), encoding="utf-8")
    print(f"저장: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
