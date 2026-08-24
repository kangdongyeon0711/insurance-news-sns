from news_alert.filters.base import BaseFilter
from news_alert.models.article import Article
from news_alert.storage.sqlite_store import SqliteStore


class DedupFilter(BaseFilter):
    """이미 처리한 적 있는 기사(URL 기준)를 제거한다."""

    def __init__(self, store: SqliteStore):
        self.store = store

    def apply(self, articles: list[Article]) -> list[Article]:
        new_articles = []
        seen_in_batch = set()
        for article in articles:
            if article.url in seen_in_batch:
                continue
            seen_in_batch.add(article.url)
            if not self.store.has_seen(article.url):
                new_articles.append(article)
        return new_articles
