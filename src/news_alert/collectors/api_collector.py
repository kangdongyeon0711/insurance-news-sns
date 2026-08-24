from news_alert.collectors.base import BaseCollector
from news_alert.models.article import Article


class ApiCollector(BaseCollector):
    """뉴스 검색 API(예: 네이버 뉴스 API)에서 기사를 수집한다."""

    def __init__(self, endpoint: str, api_key: str, query: str):
        self.endpoint = endpoint
        self.api_key = api_key
        self.query = query

    def collect(self) -> list[Article]:
        raise NotImplementedError
