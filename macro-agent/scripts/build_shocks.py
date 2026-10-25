"""knowledge/macro_topics/{date}/*.json의 factor_shocks를 합쳐 calc_impact용 시나리오 세트를 만든다.

python scripts/build_shocks.py [--date YYYY-MM-DD] [--out reports/tmp/{date}_factor_shocks.json]

결합 규칙 (README '설계 결정'):
1. 팩터별 '주인 topic'은 config/factors.yaml의 topic_id. 주인 topic이 그 팩터를 제시하면 그 값을 쓰고,
   없으면 그 팩터를 제시한 다른 topic들의 평균을 쓴다 (factor_sources에 기록).
2. 시나리오: 단기(prob 없음), 장기-Base/Bull/Bear(같은 이름끼리 결합 — 모든 topic이 같은 시나리오에 있다고 보는
   공동 단조 가정), 확률가중(팩터별로 주인 topic의 확률로 가중한 기대 충격, prob 없음).
3. 장기 시나리오 확률 = topic별 확률의 평균을 합 1로 정규화.
날짜를 생략하면 가장 최근 폴더를 쓴다.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from common import CONFIG_DIR, KNOWLEDGE_DIR, TMP_REPORTS_DIR, load_json, load_yaml, save_json, today

LT = ["Base", "Bull", "Bear"]


def latest_date(base: Path = KNOWLEDGE_DIR / "macro_topics") -> str | None:
    dates = sorted(p.name for p in base.iterdir() if p.is_dir()) if base.exists() else []
    return dates[-1] if dates else None


def _merge(per_topic: dict[str, dict], owners: dict[str, str | None]) -> tuple[dict, dict]:
    merged, sources = {}, {}
    names = {f for shocks in per_topic.values() for f in shocks}
    for f in sorted(names):
        owner = owners.get(f)
        if owner in per_topic and f in per_topic[owner]:
            merged[f], sources[f] = float(per_topic[owner][f]), owner
        else:
            vals = {t: float(s[f]) for t, s in per_topic.items() if f in s}
            merged[f] = round(sum(vals.values()) / len(vals), 4)
            sources[f] = "평균(" + ",".join(sorted(vals)) + ")"
    return merged, sources


def build(topic_dir: Path) -> dict:
    factors = load_yaml(CONFIG_DIR / "factors.yaml")["factors"]
    owners = {k: v.get("topic_id") for k, v in factors.items()}
    topics = {p.stem: load_json(p) for p in sorted(topic_dir.glob("*.json"))}
    if not topics:
        raise FileNotFoundError(f"{topic_dir}에 macro_topic JSON이 없음")
    st, st_src = _merge({t: d.get("short_term_factor_shocks", {}) for t, d in topics.items()}, owners)
    scenarios = [{"name": "단기", "prob": None, "horizon": "3-6M", "shocks": st}]
    sources = {"단기": st_src}
    probs, lt_shocks = {}, {}
    by_topic_sc = {t: {s["name"]: s for s in d["long_term"]["scenarios"]} for t, d in topics.items()}
    for name in LT:
        per = {t: sc[name].get("factor_shocks", {}) for t, sc in by_topic_sc.items() if name in sc}
        lt_shocks[name], sources[f"장기-{name}"] = _merge(per, owners)
        ps = [sc[name]["prob"] for sc in by_topic_sc.values() if name in sc]
        probs[name] = sum(ps) / len(ps) if ps else 0.0
    psum = sum(probs.values()) or 1.0
    for name in LT:
        scenarios.append({"name": f"장기-{name}", "prob": round(probs[name] / psum, 4), "horizon": "1-3Y",
                          "shocks": lt_shocks[name]})
    # 반올림 오차 보정: 확률 합을 정확히 1로
    diff = round(1 - sum(s["prob"] for s in scenarios[1:]), 4)
    scenarios[1]["prob"] = round(scenarios[1]["prob"] + diff, 4)
    # 확률가중 기대 충격: 팩터별로 주인 topic(없으면 제시 topic들)의 시나리오 확률로 가중
    expected, exp_src = {}, {}
    all_f = {f for d in lt_shocks.values() for f in d}
    for f in sorted(all_f):
        owner = owners.get(f)
        cands = [owner] if owner in by_topic_sc and any(f in s.get("factor_shocks", {}) for s in by_topic_sc[owner].values()) \
            else [t for t, sc in by_topic_sc.items() if any(f in s.get("factor_shocks", {}) for s in sc.values())]
        vals = []
        for t in cands:
            sc = by_topic_sc[t]
            vals.append(sum(sc[n]["prob"] * float(sc[n].get("factor_shocks", {}).get(f, 0.0)) for n in LT if n in sc))
        expected[f] = round(sum(vals) / len(vals), 4)
        exp_src[f] = ",".join(cands)
    scenarios.append({"name": "확률가중", "prob": None, "horizon": "1-3Y", "shocks": expected})
    sources["확률가중"] = exp_src
    return {"as_of": topic_dir.name, "source": f"knowledge/macro_topics/{topic_dir.name}/ (build_shocks.py)",
            "topics_used": sorted(topics), "missing_topics": [], "note": "장기 시나리오는 topic 간 공동 단조(같은 이름끼리 결합) 가정",
            "factor_sources": sources, "scenarios": scenarios}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    date = args.date or latest_date()
    if not date:
        print("knowledge/macro_topics/에 결과가 없음 — /macro-brief를 먼저 실행하세요")
        return 1
    doc = build(KNOWLEDGE_DIR / "macro_topics" / date)
    from common import TOPIC_IDS

    doc["missing_topics"] = [t for t in TOPIC_IDS if t not in doc["topics_used"]]
    out = Path(args.out) if args.out else TMP_REPORTS_DIR / f"{date}_factor_shocks.json"
    save_json(out, doc)
    age = (today() - __import__("datetime").date.fromisoformat(date)).days
    print(f"저장: {out} (topic {len(doc['topics_used'])}개, 누락 {doc['missing_topics'] or '없음'}, 기준일 {date}, {age}일 경과"
          f"{' ⚠ 7일 초과' if age > 7 else ''})")
    for s in doc["scenarios"]:
        print(f"  {s['name']:8s} prob={s['prob']}  " + ", ".join(f"{k}={v:g}" for k, v in s["shocks"].items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
