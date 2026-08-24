import csv
from pathlib import Path

from news_alert.collectors.base import BaseCollector
from news_alert.mocks.sample_data import press_sample_articles
from news_alert.models.article import Article
from news_alert.utils.feed import fetch_feed, parse_published_at, strip_html
from news_alert.utils.logger import get_logger
from news_alert.utils.mock import is_mock_mode

logger = get_logger(__name__)


class PressRssCollector(BaseCollector):
    """CSV로 등록된 언론사 RSS 피드 목록에서 기사를 수집한다.

    CSV 형식 (헤더 필수): name,url
    """

    def __init__(self, csv_path: Path, timeout: int = 10):
        self.csv_path = Path(csv_path)
        self.timeout = timeout

    def collect(self) -> list[Article]:
        if is_mock_mode():
            logger.info("USE_MOCK=true — 언론사 RSS 피드 대신 샘플 데이터를 반환합니다.")
            return press_sample_articles()

        articles: list[Article] = []
        for press_name, feed_url in self._read_feed_list():
            try:
                feed = fetch_feed(feed_url, timeout=self.timeout)
            except Exception:
                logger.exception("failed to fetch RSS feed: %s (%s)", press_name, feed_url)
                continue

            for entry in feed.entries:
                link = entry.get("link")
                if not link:
                    continue
                articles.append(
                    Article(
                        source=press_name,
                        title=strip_html(entry.get("title", "")),
                        url=link,
                        published_at=parse_published_at(entry),
                        content=strip_html(entry.get("summary", entry.get("description", ""))),
                    )
                )

        return articles

    def _read_feed_list(self) -> list[tuple[str, str]]:
        with open(self.csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [
                (row["name"].strip(), row["url"].strip())
                for row in reader
                if row.get("name") and row.get("url")
            ]
