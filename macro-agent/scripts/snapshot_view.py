"""latest_snapshot.json에서 topic별 지표를 표/JSON으로 출력 (에이전트가 현황 수치를 인용할 때 사용).

python scripts/snapshot_view.py --topics kr_rate,kr_govt_bond [--json]
"""
from __future__ import annotations

import argparse
import json
import sys

from common import SNAPSHOT_PATH, load_json


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topics", default="", help="쉼표 구분 topic_id (비우면 전체)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if not SNAPSHOT_PATH.exists():
        print("latest_snapshot.json 없음 — python scripts/fetch_all.py 먼저 실행 (현황 수치: 미확인)")
        return 1
    snap = load_json(SNAPSHOT_PATH)
    topics = {t for t in args.topics.split(",") if t}
    rows = [v for v in snap["series"].values() if not topics or v["topic_id"] in topics]
    if args.json:
        print(json.dumps({"ref_date": snap["ref_date"], "generated_at": snap["generated_at"], "indicators": rows},
                         ensure_ascii=False, indent=2))
        return 0
    from tabulate import tabulate

    print(f"snapshot 생성 {snap['generated_at']} / 수집 상태 {snap.get('fetch_status')}")
    if not rows:
        print("해당 topic 지표 없음 → indicators value=null, value_flag='미확인', data_gaps에 'API 데이터 미수집' 기록")
        return 0
    print(tabulate([[r["series_id"], r["name"], r["last_value"], r["unit"], r["as_of"], r["chg_1w"], r["chg_1m"],
                     r["chg_3m"], r["chg_1y"], r["chg_unit"], r["pct_rank_5y"], "⚠stale" if r["stale"] else "",
                     "" if r["verified"] else "미검증"] for r in rows],
                   headers=["series_id", "이름", "값", "단위", "기준일", "1W", "1M", "3M", "1Y", "변화단위", "5Y백분위", "", ""]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
