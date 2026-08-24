from abc import ABC, abstractmethod

from news_alert.models.article import Article


class BaseCollector(ABC):
    """뉴스 소스로부터 원문 기사를 가져와 Article로 정규화한다."""

    @abstractmethod
    def collect(self) -> list[Article]:
        ...
