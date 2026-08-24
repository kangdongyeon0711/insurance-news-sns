from news_alert.collectors.base import BaseCollector
from news_alert.filters.base import BaseFilter
from news_alert.notifiers.base import BaseNotifier
from news_alert.summarizers.base import BaseSummarizer
from news_alert.utils.logger import get_logger

logger = get_logger(__name__)


class Pipeline:
    """수집 -> 필터링 -> 요약 -> 발송 순서로 각 단계를 실행한다."""

    def __init__(
        self,
        collectors: list[BaseCollector],
        filters: list[BaseFilter],
        summarizer: BaseSummarizer,
        notifiers: list[BaseNotifier],
    ):
        self.collectors = collectors
        self.filters = filters
        self.summarizer = summarizer
        self.notifiers = notifiers

    def run(self) -> None:
        articles = [a for c in self.collectors for a in c.collect()]
        logger.info("collected %d articles", len(articles))

        for f in self.filters:
            articles = f.apply(articles)
        logger.info("%d articles remain after filtering", len(articles))

        summarized = []
        for article in articles:
            try:
                summarized.append(self.summarizer.summarize(article))
            except Exception:
                logger.exception("failed to summarize article: %s", article.url)

        for notifier in self.notifiers:
            notifier.send(summarized)
