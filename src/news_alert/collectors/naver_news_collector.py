from urllib.parse import urlencode, urlparse

from news_alert.collectors.base import BaseCollector
from news_alert.models.article import Article
from news_alert.utils.feed import fetch_feed, parse_published_at, strip_html
from news_alert.utils.logger import get_logger

logger = get_logger(__name__)

NAVER_NEWS_RSS_URL = "https://search.naver.com/search.naver"


class NaverNewsRssCollector(BaseCollector):
    """네이버 뉴스 검색 RSS에서 키워드별 최신 기사를 수집한다.

    주의: 이 엔드포인트는 네이버가 공식 문서화한 API가 아니라 검색 결과 페이지의
    RSS 출력이므로 예고 없이 형식이 바뀌거나 중단될 수 있다. 응답이 비어있거나
    파싱에 계속 실패하면 base_url을 갱신해야 한다.
    """

    def __init__(
        self,
        keywords: list[str],
        base_url: str = NAVER_NEWS_RSS_URL,
        timeout: int = 10,
    ):
        self.keywords = keywords
        self.base_url = base_url
        self.timeout = timeout

    def collect(self) -> list[Article]:
        articles: dict[str, Article] = {}
        for keyword in self.keywords:
            query = urlencode({"where": "rss", "query": keyword})
            url = f"{self.base_url}?{query}"
            try:
                feed = fetch_feed(url, timeout=self.timeout)
            except Exception:
                logger.exception("failed to fetch Naver News RSS for keyword=%r", keyword)
                continue

            for entry in feed.entries:
                link = entry.get("link")
                if not link or link in articles:
                    continue
                articles[link] = Article(
                    source=self._extract_publisher(entry, link),
                    title=strip_html(entry.get("title", "")),
                    url=link,
                    published_at=parse_published_at(entry),
                    content=strip_html(entry.get("summary", entry.get("description", ""))),
                )

        return list(articles.values())

    @staticmethod
    def _extract_publisher(entry, link: str) -> str:
        source = entry.get("source")
        if isinstance(source, dict) and source.get("title"):
            return source["title"]
        author = entry.get("author")
        if author:
            return author
        return urlparse(link).netloc or "네이버뉴스"
