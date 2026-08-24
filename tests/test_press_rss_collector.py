from types import SimpleNamespace
from unittest.mock import patch

from news_alert.collectors.press_rss_collector import PressRssCollector


def _fake_feed(entries):
    return SimpleNamespace(entries=entries, bozo=False)


def test_collect_reads_csv_and_tags_articles_with_press_name(tmp_path, monkeypatch):
    monkeypatch.delenv("USE_MOCK", raising=False)
    csv_path = tmp_path / "press_rss.csv"
    csv_path.write_text("name,url\n예시언론사,https://example.com/rss\n", encoding="utf-8")

    entry = {
        "title": "보험료 인상 소식",
        "link": "https://news.example.com/press/1",
        "summary": "내용 요약",
        "published_parsed": (2026, 8, 24, 2, 0, 0, 0, 0, 0),
    }
    with patch(
        "news_alert.collectors.press_rss_collector.fetch_feed",
        return_value=_fake_feed([entry]),
    ):
        collector = PressRssCollector(csv_path=csv_path)
        articles = collector.collect()

    assert len(articles) == 1
    assert articles[0].source == "예시언론사"
    assert articles[0].title == "보험료 인상 소식"


def test_collect_continues_when_one_feed_fails(tmp_path, monkeypatch):
    monkeypatch.delenv("USE_MOCK", raising=False)
    csv_path = tmp_path / "press_rss.csv"
    csv_path.write_text(
        "name,url\n"
        "실패언론사,https://example.com/bad\n"
        "성공언론사,https://example.com/good\n",
        encoding="utf-8",
    )

    entry = {
        "title": "정상 기사",
        "link": "https://news.example.com/press/2",
        "summary": "",
        "published_parsed": (2026, 8, 24, 2, 0, 0, 0, 0, 0),
    }

    def fake_fetch(url, timeout=10):
        if "bad" in url:
            raise Exception("connection error")
        return _fake_feed([entry])

    with patch(
        "news_alert.collectors.press_rss_collector.fetch_feed", side_effect=fake_fetch
    ):
        collector = PressRssCollector(csv_path=csv_path)
        articles = collector.collect()

    assert len(articles) == 1
    assert articles[0].source == "성공언론사"


def test_collect_returns_sample_data_in_mock_mode_without_reading_csv(monkeypatch):
    monkeypatch.setenv("USE_MOCK", "true")

    with patch("news_alert.collectors.press_rss_collector.fetch_feed") as mock_fetch:
        # csv_path deliberately points at a file that doesn't exist — mock mode
        # must never touch it.
        collector = PressRssCollector(csv_path="/nonexistent/press_rss.csv")
        articles = collector.collect()

    mock_fetch.assert_not_called()
    assert len(articles) > 0
    assert all(a.url.startswith("https://mock.local/press/") for a in articles)
