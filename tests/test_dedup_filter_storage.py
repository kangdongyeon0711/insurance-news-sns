from datetime import datetime, timezone

from news_alert.filters.dedup_filter import DedupFilter
from news_alert.models.article import Article
from news_alert.storage.sqlite_store import SqliteStore


def _article(url: str) -> Article:
    return Article(
        source="예시언론사",
        title="제목",
        url=url,
        published_at=datetime.now(timezone.utc),
        content="내용",
    )


def test_sqlite_store_has_seen_roundtrip(tmp_path):
    store = SqliteStore(tmp_path / "test.db")
    assert store.has_seen("https://example.com/a") is False

    store.mark_seen("https://example.com/a")
    assert store.has_seen("https://example.com/a") is True


def test_dedup_filter_removes_already_seen_and_in_batch_duplicates(tmp_path):
    store = SqliteStore(tmp_path / "test.db")
    store.mark_seen("https://example.com/old")

    articles = [
        _article("https://example.com/old"),
        _article("https://example.com/new"),
        _article("https://example.com/new"),
    ]

    result = DedupFilter(store).apply(articles)

    assert [a.url for a in result] == ["https://example.com/new"]
