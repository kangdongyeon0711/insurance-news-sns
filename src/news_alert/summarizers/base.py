from abc import ABC, abstractmethod

from news_alert.models.article import Article, SummarizedArticle


class BaseSummarizer(ABC):
    """Article을 짧은 알림용 요약으로 변환한다."""

    @abstractmethod
    def summarize(self, article: Article) -> SummarizedArticle:
        ...
