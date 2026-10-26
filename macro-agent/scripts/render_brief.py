"""macro_topics JSON 16개 + snapshot + view_cards → 주간 매크로 브리프 Markdown 골격.

python scripts/render_brief.py --date 2026-10-25 [--out reports/2026-10-25_macro_brief.md] [--force]

수치·표는 JSON에서 결정적으로 생성하고, 서술이 필요한 섹션(핵심 변화, 이견, 크로스에셋)은
<!-- TODO: ... --> 자리로 남긴다 — 메인 에이전트가 채운 뒤 TODO 주석을 지운다.
이미 파일이 있으면 --force 없이 덮어쓰지 않는다.
"""
from __future__ import annotations

import re

import argparse
import sys
from pathlib import Path

from common import (CONFIG_DIR, KNOWLEDGE_DIR, REPORTS_DIR, SNAPSHOT_PATH, TOPIC_IDS, load_json, load_yaml)

TOPIC_NAMES = {
    "fx_krwusd": "환율 (원/달러, 달러인덱스)", "oil": "유가 (WTI, Brent)", "kr_rate": "한국 금리 (기준금리, 단기금리)",
    "kr_govt_bond": "한국 국채 (국고채 3·10·30년, 커브)", "kr_corp_bond": "한국 회사채 (AA-, BBB-, 크레딧 스프레드)",
    "us_rate": "미국 금리 (FFR, 정책 경로)", "us_treasury": "미국 국채 (UST 2·10·30년, 커브, BEI)",
    "us_corp_bond": "미국 회사채 (IG·HY OAS)", "kr_alt_re": "한국 대체투자 - 부동산", "kr_alt_infra": "한국 대체투자 - 인프라",
    "kr_alt_pe": "한국 대체투자 - PE (Equity)", "kr_alt_pd": "한국 대체투자 - PE (Debt) / 사모대출",
    "us_alt_re": "미국 대체투자 - 부동산", "us_alt_infra": "미국 대체투자 - 인프라", "us_alt_pe": "미국 대체투자 - PE (Equity)",
    "us_alt_pd": "미국 대체투자 - PE (Debt) / Private Credit",
}
# 항목별 대표 지표 우선순위 (한 장 요약·워드 요약본 공용)
PREF = {"fx_krwusd": ["krw_usd", "dxy_ice", "kr_us_policy_diff", "kr_current_account"],
        "us_treasury": ["ust_10y", "ust_2y", "ust_30y", "ust_10y_2y"],
        "kr_govt_bond": ["ktb_3y", "ktb_10y", "ktb_30y", "ktb_5y"],
        "kr_alt_re": ["kr_office_vacancy_national", "kr_retail_vacancy_national", "kr_pf_delinquency_rate", "kr_pf_exposure"],
        "us_corp_bond": ["us_ig_oas", "us_hy_oas"]}


def ordered_indicators(topic_id: str, inds: list[dict]) -> list[dict]:
    pref = PREF.get(topic_id, [])
    return sorted(inds, key=lambda x: pref.index(x["series_id"]) if x["series_id"] in pref else len(pref))


DISCLAIMER = ("본 자료는 개인의 의사결정 보조를 위한 분석 자료이며 투자 권유가 아닙니다. 현황 수치는 기준일 시점의 공개 API 데이터 "
              "또는 [웹확인] 표시된 웹 검색 값(공식 원문 대조 전)이고, "
              "전망·시나리오·확률은 하우스 뷰와 에이전트 판단에 기반한 추정으로 실제 결과와 다를 수 있습니다. "
              "증권사 리포트 내용은 개인 분석용으로 요약했으며 원문의 저작권은 각 발행사에 있습니다.")


def ind_stale(ind: dict, ref: str) -> bool:
    """indicator 기준일이 오래되었는지.
    - API·수기 값: snapshot이 주기별 기준으로 계산한 stale 필드를 따른다.
    - 웹확인·추정 값: 에이전트가 적은 stale 필드는 무시하고 기준일로 판정(일자 = 7일, YYYY-MM = 월말 + 45일).
    - 정책금리(FFR 목표, 기준금리)는 결정일이 기준일이고 다음 결정 전까지 유효하므로 제외."""
    sid = ind.get("series_id", "")
    if any(k in sid for k in ("ffr_upper", "ffr_lower", "base_rate")):
        return False
    if ind.get("value_flag", "API") in ("API", "수기") and ind.get("stale") is not None:
        return bool(ind["stale"])
    d = ind.get("as_of")
    if not d or ind.get("value") is None:
        return False
    from datetime import date, timedelta
    import calendar

    r = date.fromisoformat(ref)
    try:
        if len(d) == 7:
            y, m = map(int, d.split("-"))
            return (r - date(y, m, calendar.monthrange(y, m)[1])).days > 45
        return (r - date.fromisoformat(d[:10])).days > 7
    except ValueError:
        return False


def fmt_unit(u: str | None) -> str:
    """값 뒤에 붙일 단위. '2020=100' 같은 기준연도 표기는 괄호로 감싼다."""
    u = (u or "").strip()
    if not u:
        return ""
    return f" ({u})" if "=" in u else f" {u}"


def fmt_num(v) -> str:
    if v is None:
        return "미확인"
    if isinstance(v, float) and abs(v) >= 100:
        return f"{v:,.2f}".rstrip("0").rstrip(".")
    return f"{v:g}" if isinstance(v, float) else str(v)


def ind_cell(ind: dict, ref: str) -> str:
    if ind.get("value") is None:
        return f"{ind.get('name') or ind['series_id']} 미확인"
    flag = "" if ind.get("value_flag", "API") == "API" else f" [{ind['value_flag']}]"
    flag += " ⚠stale" if ind_stale(ind, ref) else ""
    return f"{ind.get('name') or ind['series_id']} {fmt_num(ind['value'])}{fmt_unit(ind['unit'])} ({ind.get('as_of')}){flag}"


def shocks_str(sh: dict) -> str:
    return ", ".join(f"`{k}` {v:+g}" for k, v in sh.items()) or "—"


_SENT_END = re.compile(r"(?<=[^\sA-Za-z0-9]\.)\s+")


def sentences(text: str, n: int = 60) -> str:
    """완결된 문장만 n자 안에서 이어 붙인다(최소 첫 문장 1개). 문장 중간을 자르거나 '…'를 붙이지 않는다."""
    parts = _SENT_END.split(" ".join(text.split()))
    out = parts[0]
    for s in parts[1:]:
        if len(out) + 1 + len(s) > n:
            break
        out += " " + s
    return out


def scenario_line(s: dict) -> str:
    """시나리오 한 문장 요약: headline(작성 시 1문장) 우선, 없으면 narrative 첫 문장."""
    return s.get("headline") or sentences(s["narrative"], 0)


def short(text: str, n: int = 60) -> str:
    return sentences(text, n)


def render(date: str) -> str:
    tdir = KNOWLEDGE_DIR / "macro_topics" / date
    topics = {t: load_json(tdir / f"{t}.json") for t in TOPIC_IDS if (tdir / f"{t}.json").exists()}
    snap = load_json(SNAPSHOT_PATH) if SNAPSHOT_PATH.exists() else {"series": {}, "warnings": [], "fetch_status": {}}
    factors = load_yaml(CONFIG_DIR / "factors.yaml")["factors"]
    L: list[str] = []
    a = L.append
    a(f"# 주간 매크로 브리프 — {date}\n")
    a(f"> 작성 기준일 {date} · 표기: `[사실]` 데이터·공식 발표 / `[하우스]` 증권사 리포트(view_card) / `[판단]` 에이전트 자체 판단 · "
      f"수치 옆 괄호는 기준일(as_of)\n")
    status = snap.get("fetch_status") or {}
    bad = {k: v for k, v in status.items() if v != "ok"}
    stale = [s for s in snap["series"].values() if s.get("stale")]
    manual = [s for s in snap["series"].values() if s.get("source_type") == "manual"]
    if not snap["series"] or bad or stale or manual:
        a("> ⚠ **데이터 경고**")
        if not snap["series"]:
            a("> - API 시계열이 하나도 수집되지 않았습니다. 현황 수치는 `[웹확인]`(웹 검색, 공식 원문 대조 전) 또는 **미확인**입니다 "
              "(`.env`에 API 키 입력 후 `python scripts/fetch_all.py`).")
        if manual:
            a(f"> - 수기 입력값 {len(manual)}개 (`data/manual/`, ECOS 홈페이지 등 사용자 확인값) — 표에 `수기`로 표시, API 수집 후 교차검증 필요")
        if bad:
            a("> - 수집 상태: " + ", ".join(f"{k}={v}" for k, v in bad.items()))
        for s in stale:
            a(f"> - `{s['series_id']}` 기준일 {s['as_of']} ({s['age_days']}일 경과) — 오래된 데이터")
        a("")
    missing = [t for t in TOPIC_IDS if t not in topics]
    if missing:
        a(f"> ⚠ macro_topic 누락: {', '.join(missing)}\n")

    a("## 한 장 요약\n")
    a("| # | 항목 | 현황 핵심 수치 (기준일) | 단기 방향 (3-6M) | 장기 Base (1-3Y) | 확신도 |")
    a("|---|---|---|---|---|---|")
    for i, t in enumerate(TOPIC_IDS, 1):
        d = topics.get(t)
        if not d:
            a(f"| {i} | {TOPIC_NAMES[t]} | 미확인 | 미확인 | 미확인 | — |")
            continue
        inds = [x for x in ordered_indicators(t, d["current"]["indicators"]) if x.get("value") is not None][:2]
        cur = "<br>".join(ind_cell(x, date) for x in inds) or "미확인"
        st = d["short_term"]
        base = next(s for s in d["long_term"]["scenarios"] if s["name"] == "Base")
        a(f"| {i} | {TOPIC_NAMES[t]} | {cur} | {short(st.get('direction') or st['view'], 50)} | "
          f"{scenario_line(base)} (p={base['prob']:g}) | {st['confidence']} |")
    a("")

    movers = sorted((s for s in snap["series"].values() if s.get("chg_1w") is not None),
                    key=lambda s: abs(s["chg_1w"]) / (10 if s["chg_unit"] == "bp" else 1), reverse=True)[:6]
    a("## 이번 주 핵심 변화 3가지\n")
    a("<!-- TODO: 아래 후보(1주 변화 상위 지표)와 신규 하우스 뷰를 바탕으로 3가지를 [사실]/[하우스]/[판단] 태그로 작성 -->")
    if movers:
        a("<!-- 후보: " + "; ".join(f"{m['series_id']} {m['chg_1w']:+g}{m['chg_unit']} ({m['as_of']})" for m in movers) + " -->")
    a("")
    a("## 하우스 간 이견이 큰 항목\n")
    div = [(t, d["house_views"]["divergence"]) for t, d in topics.items() if d["house_views"].get("divergence")]
    a("<!-- TODO: 아래 자동 목록을 바탕으로 이견이 큰 항목을 골라 정리. 하우스 뷰가 부족한 항목은 명시 -->")
    for t, txt in div:
        a(f"- **{TOPIC_NAMES[t]}**: {txt}")
    if not div:
        a("- 이견을 비교할 만큼 하우스 뷰가 확보된 항목 없음 (하우스 뷰 부족)")
    a("")

    a("## 항목별 상세\n")
    for i, t in enumerate(TOPIC_IDS, 1):
        d = topics.get(t)
        a(f"### {i}. {TOPIC_NAMES[t]} (`{t}`)\n")
        if not d:
            a("미확인 — macro_topic 결과 없음\n")
            continue
        a("**현황**\n")
        a("| 지표 | series_id | 값 | 기준일 | 1M 변화 | 출처 플래그 |")
        a("|---|---|---|---|---|---|")
        for x in d["current"]["indicators"]:
            chg = "—" if x.get("chg_1m") is None else f"{x['chg_1m']:+g}{x.get('chg_unit', '')}"
            val = "미확인" if x.get("value") is None else f"{fmt_num(x['value'])}{fmt_unit(x['unit'])}"
            flag = x.get("value_flag", "API") + (" ⚠stale" if ind_stale(x, date) else "")
            src = f" ({x['source']})" if x.get("source") else ""
            a(f"| {x.get('name', '')} | `{x['series_id']}` | {val} | {x.get('as_of') or '미확인'} | {chg} | {flag}{src} |")
        a(f"\n{d['current']['summary']}\n")
        st = d["short_term"]
        a(f"**단기 (3-6M)** — 확신도 {st['confidence']}\n")
        a(f"{st['view']}\n")
        if st.get("drivers"):
            a("- 드라이버: " + "; ".join(st["drivers"]))
        a("\n**장기 시나리오 (1-3Y)**\n")
        a("| 시나리오 | 확률 | 내용 | 팩터 충격 | 번역 근거 |")
        a("|---|---|---|---|---|")
        for s in d["long_term"]["scenarios"]:
            a(f"| {s['name']} | {s['prob']:g} | {('**' + s['headline'] + '** ') if s.get('headline') else ''}{s['narrative']} | {shocks_str(s['factor_shocks'])} | {s.get('shock_rationale', '')} |")
        hv = d["house_views"]
        a("\n**하우스 뷰**\n")
        a(f"- 컨센서스: {hv['consensus'] or '—'}")
        a(f"- 이견: {hv['divergence'] or '—'}")
        a(f"- 사용 카드: {', '.join(f'`{c}`' for c in hv['cards_used']) or '없음'}")
        a("\n**단기 팩터 충격**\n")
        if d["short_term_factor_shocks"]:
            a("| factor | 충격 | 단위 |")
            a("|---|---|---|")
            for k, v in d["short_term_factor_shocks"].items():
                a(f"| `{k}` | {v:+g} | {factors.get(k, {}).get('unit', '?')} |")
            if d.get("short_term_shock_rationale"):
                a(f"\n번역 근거: {d['short_term_shock_rationale']}")
        else:
            a("—")
        a("\n**데이터 공백**: " + ("; ".join(d["data_gaps"]) or "없음") + "\n")

    a("## 크로스에셋 시사점\n")
    a("<!-- TODO: 항목 간 연결 (한미 금리차 → 환율 → 해외채 헤지비용, 유가 → 물가 → 금리, 금리 → 캡레이트 → 부동산·인프라, "
      "크레딧 → 사모대출 부도율 등)을 impact-mapping 스킬 기준으로 서술 -->\n")

    a("## 부록\n")
    a("### A. 사용한 view_card\n")
    used = sorted({c for d in topics.values() for c in d["house_views"]["cards_used"]})
    cdir = KNOWLEDGE_DIR / "view_cards"
    if used:
        a("| card_id | 하우스 | 발간일 | topics |")
        a("|---|---|---|---|")
        for c in used:
            p = cdir / f"{c}.json"
            if p.exists():
                cd = load_json(p)
                est = " (추정)" if cd.get("published_estimated") else ""
                a(f"| `{c}` | {cd['house']} | {cd['published']}{est} | {', '.join(cd['topics'])} |")
            else:
                a(f"| `{c}` | 카드 파일 없음 | | |")
    else:
        a("사용한 카드 없음")
    a("\n### B. 데이터 기준일\n")
    if snap["series"]:
        a("| series_id | 이름 | 최신값 | 단위 | 기준일 | stale | 코드 검증 |")
        a("|---|---|---|---|---|---|---|")
        for s in snap["series"].values():
            a(f"| `{s['series_id']}` | {s['name']} | {fmt_num(s['last_value'])} | {s['unit']} | {s['as_of']} | "
              f"{'⚠' if s['stale'] else ''} | {'확인' if s['verified'] else '미검증'} |")
    else:
        a("수집된 시계열 없음 (snapshot 비어 있음)")
    srcs = sorted({x for d in topics.values() for x in d["sources"] if x.startswith("http")})
    if srcs:
        a("\n### C. 웹 출처\n")
        for u in srcs:
            a(f"- {u}")
    a("\n---\n")
    a(f"**면책**: {DISCLAIMER}\n")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--out")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    out = Path(args.out) if args.out else REPORTS_DIR / f"{args.date}_macro_brief.md"
    if out.exists() and not args.force:
        print(f"이미 존재: {out} — 덮어쓰려면 --force (사용자 확인 후)")
        return 1
    out.write_text(render(args.date), encoding="utf-8")
    print(f"저장: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
