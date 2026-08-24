from news_alert.filters.base import BaseFilter
from news_alert.models.article import Article
from news_alert.storage.sqlite_store import SqliteStore


class DedupFilter(BaseFilter):
    """이미 발송 이력이 있는 기사(URL 기준)를 제거한다."""

    def __init__(self, store: SqliteStore):
        self.store = store

    def apply(self, articles: list[Article]) -> list[Article]:
        raise NotImplementedError
