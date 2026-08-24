from abc import ABC, abstractmethod

from news_alert.models.article import Article


class BaseFilter(ABC):
    """Article 목록을 받아 조건을 만족하는 것만 남긴다."""

    @abstractmethod
    def apply(self, articles: list[Article]) -> list[Article]:
        ...
