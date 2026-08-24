from datetime import datetime, timezone

from news_alert.models.article import Article, SummarizedArticle


def _article() -> Article:
    return Article(
        source="예시언론사",
        title="제목",
        url="https://example.com/a",
        published_at=datetime.now(timezone.utc),
        content="본문",
    )


def test_summarized_article_default_insurers_and_keywords_are_empty():
    result = SummarizedArticle(article=_article(), summary="요약")

    assert result.insurers == []
    assert result.keywords == []


def test_summarized_article_defaults_are_independent_between_instances():
    article = _article()
    a = SummarizedArticle(article=article, summary="요약 A")
    b = SummarizedArticle(article=article, summary="요약 B")

    a.insurers.append("삼성생명")

    assert a.insurers == ["삼성생명"]
    assert b.insurers == []
