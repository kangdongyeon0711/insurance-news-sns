"""최종 리포트(Markdown)의 기계 검증 — fact-checker가 쓰는 보조 도구.

python scripts/check_report.py reports/2026-10-25_macro_brief.md --kind macro
python scripts/check_report.py reports/2026-10-25_현대해상_portfolio_impact.md --kind portfolio \
    --impact reports/tmp/2026-10-25_현대해상_impact.json

검사:
  공통: 면책 문구, [사실]/[하우스]/[판단] 태그, 남은 TODO, factor 이름(`*_bp|_pct|_pp`) ∈ factors.yaml
  macro: 표에서 `series_id`가 있는 행의 값·기준일 = latest_snapshot.json, 섹션별 시나리오 확률 합 = 1
  portfolio: 시나리오×자산군 표와 요약 표 금액 = impact JSON, 추정 셀의 '*' 표시
표 밖 문장 속 수치는 검사하지 않는다 (fact-checker가 직접 대조).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from common import CONFIG_DIR, SNAPSHOT_PATH, load_json, load_yaml

NUM = re.compile(r"[-+]?\d[\d,]*\.?\d*")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def num(s: str) -> float | None:
    m = NUM.search(s.replace("**", ""))
    return float(m.group().replace(",", "")) if m else None


def decimals(s: str) -> int:
    m = NUM.search(s)
    return len(m.group().split(".")[1]) if m and "." in m.group() else 0


def common_checks(text: str) -> tuple[list[str], list[str]]:
    errs, warns = [], []
    if "투자 권유가 아" not in text:
        errs.append("면책 문구('투자 권유가 아님') 없음")
    for tag in ("[사실]", "[하우스]", "[판단]"):
        if tag not in text:
            warns.append(f"{tag} 태그가 한 번도 쓰이지 않음")
    todos = re.findall(r"<!-- TODO", text)
    if todos:
        errs.append(f"채우지 않은 TODO {len(todos)}개")
    names = set(load_yaml(CONFIG_DIR / "factors.yaml")["factors"])
    for f in sorted(set(re.findall(r"`([a-z0-9_]+_(?:bp|pct|pp))`", text))):
        if f not in names:
            errs.append(f"factors.yaml에 없는 factor 이름: {f}")
    return errs, warns


def check_macro(text: str, snap: dict) -> tuple[list[str], list[str]]:
    errs, warns = [], []
    series = snap.get("series", {})
    section = ""
    probs: dict[str, list[float]] = {}
    for n, line in enumerate(text.splitlines(), 1):
        if line.startswith("### "):
            section = line
        if not line.startswith("|") or set(line.replace("|", "").strip()) <= {"-", " "}:
            continue
        cs = cells(line)
        if cs and cs[0] in ("Base", "Bull", "Bear") and len(cs) > 1:
            p = num(cs[1])
            if p is not None:
                probs.setdefault(section, []).append(p)
            continue
        for i, c in enumerate(cs):
            m = re.fullmatch(r"`([a-z0-9_]+)`", c)
            if not m or m.group(1) not in series:
                continue
            st = series[m.group(1)]
            rest = cs[:i] + cs[i + 1:]
            datecell = next((x for x in rest if DATE.fullmatch(x.split()[0] if x.split() else "")), None)
            valcell = next((x for x in cs[i + 1:] if num(x) is not None and not DATE.search(x)), None)
            if any("미확인" == x.split()[0] for x in cs[i + 1:i + 2] if x.split()):
                errs.append(f"L{n}: {st['series_id']} '미확인' 표기지만 snapshot 값 {st['last_value']} ({st['as_of']}) 있음")
                break
            if valcell is not None:
                v, d = num(valcell), decimals(valcell)
                tol = 0.5 * 10 ** (-d) + 1e-9
                if abs(v - st["last_value"]) > tol:
                    errs.append(f"L{n}: {st['series_id']} 값 {valcell} ≠ snapshot {st['last_value']}")
            if datecell is None:
                errs.append(f"L{n}: {st['series_id']} 기준일 없음")
            elif datecell.split()[0] != st["as_of"]:
                errs.append(f"L{n}: {st['series_id']} 기준일 {datecell} ≠ snapshot {st['as_of']}")
            if st.get("stale") and "stale" not in line and "⚠" not in line:
                warns.append(f"L{n}: {st['series_id']} stale인데 경고 표시 없음")
            break
    for sec, ps in probs.items():
        if abs(sum(ps) - 1) > 1e-3:
            errs.append(f"{sec.strip('# ')}: 시나리오 확률 합 {sum(ps):.3f} ≠ 1")
    return errs, warns


def check_portfolio(text: str, impact: dict) -> tuple[list[str], list[str]]:
    errs, warns = [], []
    scen = {s["name"]: s for s in impact["scenarios"]}
    lines = text.splitlines()
    # 시나리오 × 자산군 표 찾기
    try:
        start = next(i for i, l in enumerate(lines) if l.startswith("| 자산군 | 금액"))
    except StopIteration:
        return ["시나리오×자산군 영향 표를 찾지 못함"], warns
    hdr = cells(lines[start])[2:]
    rows_by_key = {r["key"]: i for i, r in enumerate(impact["scenarios"][0]["rows"])}
    for n in range(start + 2, len(lines)):
        l = lines[n]
        if not l.startswith("|"):
            break
        cs = cells(l)
        key = cs[0].replace("**", "")
        if key == "합계":
            for name, c in zip(hdr, cs[2:]):
                exp = impact["prob_weighted"]["total_100m"] if name == "확률가중" else scen[name]["total_100m"]
                if abs(num(c) - exp) > 0.6:
                    errs.append(f"L{n + 1}: 합계 {name} {c} ≠ {exp}")
            continue
        if key not in rows_by_key:
            continue
        idx = rows_by_key[key]
        for name, c in zip(hdr, cs[2:]):
            if name == "확률가중":
                exp, est = impact["prob_weighted"]["rows"][idx]["impact_100m"], None
            else:
                r = scen[name]["rows"][idx]
                exp, est = r["impact_100m"], r["estimated"]
            if num(c) is None or abs(num(c) - exp) > 0.6:
                errs.append(f"L{n + 1}: {key}/{name} {c} ≠ {exp:,.2f}")
            if est and "*" not in c:
                errs.append(f"L{n + 1}: {key}/{name} 추정값인데 '*' 표시 없음")
    # 요약 표 합계 (헤더 '| 시나리오 | 확률 | 운용자산 ...' 표만)
    s0 = next((i for i, l in enumerate(lines) if l.startswith("| 시나리오 | 확률 | 운용자산")), None)
    if s0 is None:
        errs.append("요약 표(시나리오별 평가손익)를 찾지 못함")
    else:
        for l in lines[s0 + 2:]:
            if not l.startswith("|"):
                break
            cs = cells(l)
            if cs[0] in scen:
                exp = scen[cs[0]]
                if abs(num(cs[2]) - exp["total_100m"]) > 0.6 or abs(num(cs[3]) - exp["total_bp"]) > 0.06:
                    errs.append(f"요약 {cs[0]}: {cs[2]}억원/{cs[3]}bp ≠ {exp['total_100m']}/{exp['total_bp']}")
            elif cs[0].startswith("확률가중") and impact.get("prob_weighted"):
                if abs(num(cs[2]) - impact["prob_weighted"]["total_100m"]) > 0.6:
                    errs.append(f"요약 확률가중: {cs[2]} ≠ {impact['prob_weighted']['total_100m']}")
    if impact.get("is_sample") and "가상" not in text:
        errs.append("가상 샘플 포트폴리오인데 '가상' 표시 없음")
    return errs, warns


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("report")
    ap.add_argument("--kind", choices=["macro", "portfolio"], required=True)
    ap.add_argument("--impact")
    ap.add_argument("--snapshot", default=str(SNAPSHOT_PATH))
    args = ap.parse_args(argv)
    text = Path(args.report).read_text(encoding="utf-8")
    errs, warns = common_checks(text)
    if args.kind == "macro":
        snap = load_json(Path(args.snapshot)) if Path(args.snapshot).exists() else {"series": {}}
        e, w = check_macro(text, snap)
    else:
        if not args.impact:
            print("--impact 필요")
            return 2
        e, w = check_portfolio(text, load_json(Path(args.impact)))
    errs, warns = errs + e, warns + w
    for x in errs:
        print(f"✗ {x}")
    for x in warns:
        print(f"⚠ {x}")
    print(f"\n{args.report}: 오류 {len(errs)}건, 경고 {len(warns)}건")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
