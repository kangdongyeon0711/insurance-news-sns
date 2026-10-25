"""knowledge/view_cards/에서 기준일로부터 N일 이내 카드 중 지정 topic의 views를 모아 출력.

python scripts/recent_cards.py --topics us_rate,us_treasury [--as-of 2026-10-25] [--days 30] [--json] [--include-samples]

card_id에 '_샘플_'이 들어간 카드(통합 테스트용 가상 리포트)는 --include-samples 없이는 제외한다.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta

from common import KNOWLEDGE_DIR, load_json, today


def collect(topics: set[str], as_of, days: int, include_samples: bool = False) -> list[dict]:
    out = []
    lo = as_of - timedelta(days=days)
    for p in sorted((KNOWLEDGE_DIR / "view_cards").glob("*.json")):
        c = load_json(p)
        if "_샘플_" in c["card_id"] and not include_samples:
            continue
        pub = datetime.strptime(c["published"], "%Y-%m-%d").date()
        if not (lo <= pub <= as_of):
            continue
        views = [v for v in c.get("views", []) if not topics or v["topic_id"] in topics]
        if views:
            out.append({"card_id": c["card_id"], "house": c["house"], "published": c["published"],
                        "published_estimated": c.get("published_estimated", False), "views": views,
                        "key_risks": c.get("key_risks", [])})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topics", default="")
    ap.add_argument("--as-of", default=None)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--include-samples", action="store_true")
    args = ap.parse_args(argv)
    as_of = datetime.strptime(args.as_of, "%Y-%m-%d").date() if args.as_of else today()
    cards = collect({t for t in args.topics.split(",") if t}, as_of, args.days, args.include_samples)
    if args.json:
        print(json.dumps(cards, ensure_ascii=False, indent=2))
        return 0
    houses = {c["house"] for c in cards}
    print(f"{as_of} 기준 {args.days}일 이내 카드 {len(cards)}개, 하우스 {len(houses)}곳: {sorted(houses)}")
    for c in cards:
        for v in c["views"]:
            print(f"- [{c['card_id']}] {c['house']} {c['published']} | {v['topic_id']}.{v['variable']} "
                  f"{v['direction']}({v['horizon']}) 목표={v['target']} 확신={v['conviction']} {v['page_ref']} — {v['rationale']}")
    if len(houses) <= 1:
        print("→ 하우스 뷰 부족 (1곳 이하): data_gaps에 기록")
    return 0


if __name__ == "__main__":
    sys.exit(main())
