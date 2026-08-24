from news_alert.filters.base import BaseFilter
from news_alert.models.article import Article


class KeywordFilter(BaseFilter):
    """config/keywords.yaml의 포함/제외 키워드로 관련성을 판단한다."""

    def __init__(self, include_keywords: list[str], exclude_keywords: list[str]):
        self.include_keywords = include_keywords
        self.exclude_keywords = exclude_keywords

    def apply(self, articles: list[Article]) -> list[Article]:
        raise NotImplementedError
