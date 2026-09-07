#!/usr/bin/env python
"""config/press_rss.csv에 등록된 모든 RSS 피드가 실제로 파싱 가능한지 한 번에 검사한다.

전체 파이프라인(수집→필터→요약)을 다 돌리지 않고도 URL만 빠르게 검증할 수 있다.
언론사 RSS를 추가할 때마다 이 스크립트로 먼저 확인하고, 실패하는 항목은
config/press_rss.csv에서 지우거나 올바른 URL로 고친다.

사용법:
    python scripts/validate_press_rss.py
"""

import csv
import sys
from pathlib import Path

from news_alert.utils.feed import fetch_feed
from news_alert.utils.logger import get_logger

logger = get_logger(__name__)

CSV_PATH = Path(__file__).resolve().parents[1] / "config" / "press_rss.csv"


def _read_rows() -> list[tuple[str, str]]:
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        return [
            (row["name"].strip(), row["url"].strip())
            for row in csv.DictReader(f)
            if row.get("name") and row.get("url")
        ]


def main() -> None:
    rows = _read_rows()
    print(f"{CSV_PATH}에서 {len(rows)}개 피드 검증 시작...\n")

    ok: list[tuple[str, str, int]] = []
    failed: list[tuple[str, str, str]] = []

    for name, url in rows:
        try:
            feed = fetch_feed(url, timeout=10)
            count = len(feed.entries)
            ok.append((name, url, count))
            print(f"OK   [{count:>3}건] {name} — {url}")
        except Exception as exc:
            failed.append((name, url, str(exc)))
            print(f"FAIL         {name} — {url}\n       -> {exc}")

    print(f"\n{len(ok)}개 정상 / {len(failed)}개 실패 (총 {len(rows)}개)")

    if failed:
        print("\n실패한 항목 (config/press_rss.csv에서 지우거나 URL을 고치세요):")
        for name, url, _ in failed:
            print(f"  - {name}: {url}")
        sys.exit(1)


if __name__ == "__main__":
    main()
