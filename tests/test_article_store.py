from datetime import datetime, timedelta, timezone

from news_alert.models.article import Article, SummarizedArticle
from news_alert.storage.article_store import ArticleStore


def _summarized(url: str, published_at: datetime, insurers: list[str]) -> SummarizedArticle:
    article = Article(
        source="예시언론사",
        title=f"제목-{url}",
        url=url,
        published_at=published_at,
        content="본문",
    )
    return SummarizedArticle(
        article=article,
        summary="요약 1줄\n요약 2줄\n요약 3줄",
        insurers=insurers,
        keywords=["키워드1", "키워드2"],
    )


def test_save_and_list_recent_orders_by_published_at_desc(tmp_path):
    store = ArticleStore(tmp_path / "test.db")
    now = datetime.now(timezone.utc)

    store.save(_summarized("https://example.com/old", now - timedelta(hours=2), ["삼성생명"]))
    store.save(_summarized("https://example.com/new", now, ["한화생명"]))
    store.save(_summarized("https://example.com/mid", now - timedelta(hours=1), ["교보생명"]))

    result = store.list_recent(limit=10)

    assert [a.article.url for a in result] == [
        "https://example.com/new",
        "https://example.com/mid",
        "https://example.com/old",
    ]


def test_list_recent_filters_by_insurer(tmp_path):
    store = ArticleStore(tmp_path / "test.db")
    now = datetime.now(timezone.utc)

    store.save(_summarized("https://example.com/a", now, ["삼성생명", "삼성화재"]))
    store.save(_summarized("https://example.com/b", now, ["한화생명"]))

    result = store.list_recent(limit=10, insurer="삼성생명")

    assert [a.article.url for a in result] == ["https://example.com/a"]


def test_list_recent_respects_limit(tmp_path):
    store = ArticleStore(tmp_path / "test.db")
    now = datetime.now(timezone.utc)

    for i in range(5):
        store.save(_summarized(f"https://example.com/{i}", now - timedelta(minutes=i), []))

    result = store.list_recent(limit=2)

    assert len(result) == 2


def test_save_upserts_by_url(tmp_path):
    store = ArticleStore(tmp_path / "test.db")
    now = datetime.now(timezone.utc)

    store.save(_summarized("https://example.com/a", now, ["삼성생명"]))
    updated = _summarized("https://example.com/a", now, ["삼성생명"])
    updated.summary = "수정된 요약"
    store.save(updated)

    result = store.list_recent(limit=10)

    assert len(result) == 1
    assert result[0].summary == "수정된 요약"


def test_round_trips_full_summarized_article(tmp_path):
    store = ArticleStore(tmp_path / "test.db")
    now = datetime.now(timezone.utc)
    original = _summarized("https://example.com/full", now, ["삼성생명", "한화생명"])
    store.save(original)

    result = store.list_recent(limit=10)[0]

    assert result.article.title == original.article.title
    assert result.article.source == original.article.source
    assert result.summary == original.summary
    assert result.insurers == original.insurers
    assert result.keywords == original.keywords
