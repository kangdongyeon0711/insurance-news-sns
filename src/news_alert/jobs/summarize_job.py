from pathlib import Path

from news_alert.collectors.naver_news_collector import NaverNewsRssCollector
from news_alert.collectors.press_rss_collector import PressRssCollector
from news_alert.filters.dedup_filter import DedupFilter
from news_alert.filters.insurer_filter import InsurerFilter
from news_alert.models.article import SummarizedArticle
from news_alert.storage.article_store import ArticleStore
from news_alert.storage.sqlite_store import SqliteStore
from news_alert.summarizers.llm_summarizer import LlmSummarizer
from news_alert.utils.config_loader import load_yaml
from news_alert.utils.logger import get_logger

logger = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = REPO_ROOT / "config"
DATA_DIR = REPO_ROOT / "data"


def run_summarize_job() -> list[SummarizedArticle]:
    """새 기사를 수집 → 보험사 관련 기사만 추리기 → Claude로 3줄 요약 → 저장까지 수행한다.

    저장된 결과는 web/app.py가 제공하는 조회 페이지의 데이터 소스가 된다.
    """
    settings = load_yaml(CONFIG_DIR / "settings.yaml")
    keywords = settings.get("naver_news", {}).get("keywords", [])
    summarizer_cfg = settings.get("summarizer", {})

    collectors = [
        NaverNewsRssCollector(keywords=keywords),
        PressRssCollector(csv_path=CONFIG_DIR / "press_rss.csv"),
    ]
    articles = [article for collector in collectors for article in collector.collect()]
    logger.info("collected %d articles before filtering", len(articles))

    dedup_store = SqliteStore(DATA_DIR / "news_alert.db")
    new_articles = DedupFilter(dedup_store).apply(articles)
    for article in new_articles:
        dedup_store.mark_seen(article.url)
    logger.info("%d articles are new (not previously seen)", len(new_articles))

    insurer_filter = InsurerFilter(insurers_path=CONFIG_DIR / "insurers.json")
    relevant_articles = insurer_filter.apply(new_articles)
    logger.info("%d new articles mention a tracked insurer", len(relevant_articles))

    summarizer = LlmSummarizer(
        model=summarizer_cfg.get("model", "claude-opus-5"),
        max_summary_lines=summarizer_cfg.get("max_summary_lines", 3),
    )
    article_store = ArticleStore(DATA_DIR / "news_alert.db")

    summarized: list[SummarizedArticle] = []
    for article in relevant_articles:
        try:
            result = summarizer.summarize(article)
        except Exception:
            logger.exception("failed to summarize article: %s", article.url)
            continue
        article_store.save(result)
        summarized.append(result)

    logger.info("summarized and stored %d articles", len(summarized))
    return summarized


if __name__ == "__main__":
    run_summarize_job()
