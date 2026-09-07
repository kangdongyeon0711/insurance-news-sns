import sqlite3
from pathlib import Path

from news_alert.jobs.summarize_job import run_summarize_job
from news_alert.models.article import SummarizedArticle
from news_alert.storage.article_store import ArticleStore
from news_alert.storage.sqlite_store import SqliteStore
from news_alert.utils.env import load_env
from news_alert.utils.logger import get_logger

load_env()

logger = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data"


def clear_unsummarized_seen_marks() -> int:
    """summarized_articles에 없는 seen_articles 항목만 지운다.

    RSS는 "최신 N개"만 보여줄 뿐 기간을 지정해 과거 기사를 조회할 수 없다.
    그래서 한 번 놓친(예: API 키가 없어 요약이 실패한) 기사는 시간이 지나
    피드에서 밀려나면 다시는 수집할 수 없게 된다. seen_articles에는
    기록됐지만 summarized_articles에는 없는 기사들의 "이미 본 기록"만
    지워, 아직 피드에 남아있다면 다음 summarize_job 실행에서 재수집·
    재요약되게 한다. 이미 요약에 성공한 기사는 건드리지 않아 불필요한
    Claude API 재호출을 막는다.
    """
    db_path = DATA_DIR / "news_alert.db"
    SqliteStore(db_path)
    ArticleStore(db_path)

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(
            "DELETE FROM seen_articles WHERE url NOT IN (SELECT url FROM summarized_articles)"
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def run_backfill_job() -> list[SummarizedArticle]:
    """요약되지 못했던 기사들의 중복방지 기록을 지우고 다시 수집·요약한다.

    RSS 피드에 현재 남아있는 기사만 대상이 된다 — 특정 기간을 지정해
    과거 기사를 가져오는 기능은 아니다(README 참고).
    """
    cleared = clear_unsummarized_seen_marks()
    logger.info("%d개 기사의 처리 기록을 지웠습니다 (요약되지 않았던 것만)", cleared)
    return run_summarize_job()


if __name__ == "__main__":
    run_backfill_job()
