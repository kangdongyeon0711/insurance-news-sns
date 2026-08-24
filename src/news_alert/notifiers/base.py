from abc import ABC, abstractmethod

from news_alert.models.article import SummarizedArticle


class BaseNotifier(ABC):
    """요약된 기사를 채널로 발송한다."""

    @abstractmethod
    def send(self, articles: list[SummarizedArticle]) -> None:
        ...
