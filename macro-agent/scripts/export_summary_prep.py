"""16개 macro_topic JSON → 워드 요약용 데이터 (reports/tmp/{date}_summary_prep.json).

사용: python scripts/export_summary_prep.py 2026-10-25 && node scripts/export_summary_docx.js 2026-10-25
"""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from render_brief import TOPIC_NAMES, fmt_num, ind_stale
from common import TOPIC_IDS
DATE = sys.argv[1]
tdir = ROOT / "knowledge/macro_topics" / DATE

def clip(t, n=170):
    t = " ".join(t.split())
    if len(t) <= n:
        return t
    cut = t[:n]
    m = max(cut.rfind(". "), cut.rfind("다. "), cut.rfind("음. "), cut.rfind("함. "))
    return (cut[:m + 1] if m > 60 else cut.rstrip() + "…")

# 항목별 대표 지표 우선순위 (요약표는 첫 번째, 상세표는 앞 4개)
PREF = {"fx_krwusd": ["krw_usd", "dxy_ice", "kr_us_policy_diff", "kr_current_account"],
        "us_treasury": ["ust_10y", "ust_2y", "ust_30y", "ust_10y_2y"],
        "kr_govt_bond": ["ktb_3y", "ktb_10y", "ktb_30y", "ktb_5y"],
        "kr_alt_re": ["kr_office_vacancy_national", "kr_retail_vacancy_national", "kr_pf_delinquency_rate", "kr_pf_exposure"],
        "us_corp_bond": ["us_ig_oas", "us_hy_oas"]}
out = {"date": DATE, "topics": []}
cards = set()
for i, t in enumerate(TOPIC_IDS, 1):
    p = tdir / f"{t}.json"
    if not p.exists():
        out["topics"].append({"no": i, "id": t, "name": TOPIC_NAMES[t], "missing": True}); continue
    d = json.loads(p.read_text())
    inds = []
    pref = PREF.get(t, [])
    ordered = sorted(d["current"]["indicators"], key=lambda x: pref.index(x["series_id"]) if x["series_id"] in pref else len(pref))
    for x in ordered:
        if x.get("value") is None:
            continue
        vf = x.get("value_flag", "API")
        # 웹확인·추정 값은 에이전트가 적은 stale 필드 대신 기준일로 직접 판정
        chk = x if vf in ("API", "수기") else {k: v for k, v in x.items() if k != "stale"}
        policy = any(k in x["series_id"] for k in ("ffr_upper", "ffr_lower", "base_rate"))  # 결정일 기준 값은 다음 결정 전까지 유효
        flag = vf + (" ⚠" if ind_stale(chk, DATE) and not policy else "")
        nm = x.get("name") or x["series_id"]
        short = re.sub(r"\s*\((?:[^()]*(?:ECOS|웹|FRED|STEO|PitchBook|Trepp|한국부동산원|TTM|분기|부실)[^()]*)\)", "", nm)
        inds.append({"short": short[:22], "name": nm, "value": f"{fmt_num(x['value'])} {x['unit']}".strip(),
                     "as_of": x.get("as_of") or "미확인", "flag": flag})
    sc = {s["name"]: s for s in d["long_term"]["scenarios"]}
    hv = d["house_views"]
    cards |= set(hv["cards_used"])
    out["topics"].append({
        "no": i, "id": t, "name": TOPIC_NAMES[t], "missing": False,
        "indicators": inds[:4], "n_ind_more": max(0, len(inds) - 4),
        "summary": clip(d["current"]["summary"], 150),
        "st_dir": d["short_term"].get("direction") or clip(d["short_term"]["view"], 60),
        "st_view": clip(d["short_term"]["view"], 150), "st_conf": d["short_term"]["confidence"],
        "scen": [{"name": n, "prob": sc[n]["prob"], "text": clip(sc[n]["narrative"], 85), "short": clip(sc[n]["narrative"], 60)} for n in ("Base", "Bull", "Bear") if n in sc],
        "house": clip(hv["consensus"], 260) if hv["consensus"] else "하우스 뷰 없음",
        "cards": hv["cards_used"],
        "gaps": [clip(g, 70) for g in d["data_gaps"][:2]],
    })
cinfo = []
for c in sorted(cards):
    cp = ROOT / "knowledge/view_cards" / f"{c}.json"
    cd = json.loads(cp.read_text()) if cp.exists() else {}
    cinfo.append({"id": c, "house": cd.get("house", "미확인"), "published": cd.get("published", ""),
                  "title": cd.get("report_title", "")})
out["cards"] = cinfo
houses = sorted({c["house"] for c in cinfo})
out["houses"] = houses
json.dump(out, open(ROOT / "reports/tmp" / f"{DATE}_summary_prep.json", "w"), ensure_ascii=False, indent=1)
print("ok", sum(1 for x in out["topics"] if not x["missing"]), "topics")
