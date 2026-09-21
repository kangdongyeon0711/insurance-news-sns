#!/usr/bin/env python
"""이미 저장된 기사의 기업 태그(insurers)를 insurers.json의 정식 명칭으로 다시 채운다.

예전 요약기는 기업 태그를 Claude 응답에서 그대로 가져왔다. 그런데 시스템
프롬프트가 "보험사명"을 요구했기 때문에, 정유사·증권사 기사는 태그가 비워진 채
저장됐고(회사명은 keywords로 밀려남) 웹페이지에서 그 회사를 선택하면 0건으로
나왔다. 이 스크립트는 그렇게 저장된 기존 기사들을 한 번에 고친다.

기사 본문은 DB에 보관하지 않으므로 제목 + 요약 + 기존 태그/키워드를 근거로
정식 명칭을 다시 찾는다. 정식 명칭이 하나도 발견되지 않으면 기존 값을 그대로
둔다(지우지 않는다).

사용법:
    python scripts/repair_insurer_tags.py
"""

import json
import sqlite3
from pathlib import Path

from news_alert.filters.insurer_filter import load_insurer_names, normalize_for_match
from news_alert.utils.logger import get_logger

logger = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = REPO_ROOT / "config"
DATA_DIR = REPO_ROOT / "data"


def repair_insurer_tags(db_path: Path, insurers_path: Path) -> tuple[int, int]:
    """저장된 기사들의 기업 태그를 다시 계산해 갱신한다. (갱신 건수, 전체 건수) 반환."""
    insurer_names = load_insurer_names(insurers_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT url, title, summary, insurers, keywords FROM summarized_articles"
        ).fetchall()

        updated = 0
        for row in rows:
            stored = json.loads(row["insurers"])
            haystack = normalize_for_match(
                " ".join([row["title"], row["summary"], row["insurers"], row["keywords"]])
            )
            detected = [
                name for name in insurer_names if normalize_for_match(name) in haystack
            ]
            if not detected or detected == stored:
                continue

            conn.execute(
                "UPDATE summarized_articles SET insurers = ? WHERE url = ?",
                (json.dumps(detected, ensure_ascii=False), row["url"]),
            )
            updated += 1
            logger.info("%s: %s -> %s", row["title"][:40], stored, detected)

        conn.commit()
        return updated, len(rows)
    finally:
        conn.close()


def main() -> None:
    updated, total = repair_insurer_tags(
        DATA_DIR / "news_alert.db", CONFIG_DIR / "insurers.json"
    )
    logger.info("전체 %d건 중 %d건의 기업 태그를 정식 명칭으로 고쳤습니다.", total, updated)


if __name__ == "__main__":
    main()
