from types import SimpleNamespace
from unittest.mock import patch

from news_alert.collectors.naver_news_collector import NaverNewsRssCollector


def _fake_feed(entries):
    return SimpleNamespace(entries=entries, bozo=False)


def test_collect_parses_articles_and_strips_html(monkeypatch):
    monkeypatch.delenv("USE_MOCK", raising=False)
    entry = {
        "title": "<b>삼성화재</b> 실적 발표",
        "link": "https://news.example.com/1",
        "summary": "<p>3분기 실적이 발표됐다.</p>",
        "published_parsed": (2026, 8, 24, 1, 0, 0, 0, 0, 0),
        "source": {"title": "예시신문"},
    }
    with patch(
        "news_alert.collectors.naver_news_collector.fetch_feed",
        return_value=_fake_feed([entry]),
    ):
        collector = NaverNewsRssCollector(keywords=["삼성화재"])
        articles = collector.collect()

    assert len(articles) == 1
    article = articles[0]
    assert article.title == "삼성화재 실적 발표"
    assert article.content == "3분기 실적이 발표됐다."
    assert article.source == "예시신문"
    assert article.url == "https://news.example.com/1"


def test_collect_dedupes_across_keywords(monkeypatch):
    monkeypatch.delenv("USE_MOCK", raising=False)
    entry = {
        "title": "공통 기사",
        "link": "https://news.example.com/dup",
        "summary": "",
        "published_parsed": (2026, 8, 24, 1, 0, 0, 0, 0, 0),
    }
    with patch(
        "news_alert.collectors.naver_news_collector.fetch_feed",
        return_value=_fake_feed([entry]),
    ):
        collector = NaverNewsRssCollector(keywords=["삼성화재", "DB손해보험"])
        articles = collector.collect()

    assert len(articles) == 1


def test_collect_skips_keyword_on_fetch_error(monkeypatch):
    monkeypatch.delenv("USE_MOCK", raising=False)
    with patch(
        "news_alert.collectors.naver_news_collector.fetch_feed",
        side_effect=Exception("boom"),
    ):
        collector = NaverNewsRssCollector(keywords=["삼성화재"])
        articles = collector.collect()

    assert articles == []


def test_collect_returns_sample_data_in_mock_mode_without_calling_fetch_feed(monkeypatch):
    monkeypatch.setenv("USE_MOCK", "true")

    with patch("news_alert.collectors.naver_news_collector.fetch_feed") as mock_fetch:
        collector = NaverNewsRssCollector(keywords=["삼성화재"])
        articles = collector.collect()

    mock_fetch.assert_not_called()
    assert len(articles) > 0
    assert all(a.url.startswith("https://mock.local/naver/") for a in articles)
