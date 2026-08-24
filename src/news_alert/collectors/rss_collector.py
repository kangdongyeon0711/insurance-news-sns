from news_alert.collectors.base import BaseCollector
from news_alert.models.article import Article


class RssCollector(BaseCollector):
    """config/sources.yaml에 등록된 RSS 피드에서 기사를 수집한다."""

    def __init__(self, feed_urls: list[str]):
        self.feed_urls = feed_urls

    def collect(self) -> list[Article]:
        raise NotImplementedError
