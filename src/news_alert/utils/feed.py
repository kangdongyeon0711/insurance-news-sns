import re
from datetime import datetime, timezone

import feedparser
import requests

from news_alert.utils.logger import get_logger

logger = get_logger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
DEFAULT_TIMEOUT = 10
DEFAULT_USER_AGENT = "insurance-news-sns/0.1"


def fetch_feed(url: str, timeout: int = DEFAULT_TIMEOUT) -> feedparser.FeedParserDict:
    """RSS/Atom 피드를 내려받아 파싱한다. 응답이 정상 피드가 아니면 예외를 던진다."""
    response = requests.get(url, timeout=timeout, headers={"User-Agent": DEFAULT_USER_AGENT})
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    if feed.bozo and not feed.entries:
        raise ValueError(f"failed to parse feed as RSS/Atom: {url}")
    return feed


def strip_html(text: str) -> str:
    """HTML 태그를 제거하고 앞뒤 공백을 정리한다."""
    return _TAG_RE.sub("", text or "").strip()


def parse_published_at(entry) -> datetime:
    """entry에서 발행 시각을 파싱한다. 없으면 현재 시각(UTC)을 사용한다."""
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            return datetime(*value[:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)
