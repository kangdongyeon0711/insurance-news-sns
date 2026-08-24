from pathlib import Path

from news_alert.collectors.naver_news_collector import NaverNewsRssCollector
from news_alert.collectors.press_rss_collector import PressRssCollector
from news_alert.filters.dedup_filter import DedupFilter
from news_alert.models.article import Article
from news_alert.storage.sqlite_store import SqliteStore
from news_alert.utils.config_loader import load_yaml
from news_alert.utils.logger import get_logger

logger = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = REPO_ROOT / "config"
DATA_DIR = REPO_ROOT / "data"


def run_collect_job() -> list[Article]:
    """네이버 뉴스 검색 RSS + 언론사 RSS 목록에서 새 기사를 수집해 반환한다.

    이미 수집한 적 있는 기사(URL 기준)는 제외하고, 새로 발견한 기사만
    SqliteStore에 기록한 뒤 반환한다.
    """
    settings = load_yaml(CONFIG_DIR / "settings.yaml")
    keywords = settings.get("naver_news", {}).get("keywords", [])

    collectors = [
        NaverNewsRssCollector(keywords=keywords),
        PressRssCollector(csv_path=CONFIG_DIR / "press_rss.csv"),
    ]

    articles = [article for collector in collectors for article in collector.collect()]
    logger.info("collected %d articles before dedup", len(articles))

    store = SqliteStore(DATA_DIR / "news_alert.db")
    new_articles = DedupFilter(store).apply(articles)

    for article in new_articles:
        store.mark_seen(article.url)
        logger.info(
            "[NEW] %s | %s | %s | %s",
            article.source,
            article.title,
            article.published_at.isoformat(),
            article.url,
        )

    logger.info("%d new articles found", len(new_articles))
    return new_articles


if __name__ == "__main__":
    run_collect_job()
