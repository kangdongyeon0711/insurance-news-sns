from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from news_alert.jobs import collect_job
from news_alert.models.article import Article
from news_alert.storage.sqlite_store import SqliteStore


def _article(url: str, title: str) -> Article:
    return Article(
        source="예시언론사",
        title=title,
        url=url,
        published_at=datetime.now(timezone.utc),
        content="",
    )


def _patch_collectors(naver_articles, press_articles=None):
    mock_naver = MagicMock()
    mock_naver.collect.return_value = naver_articles
    mock_press = MagicMock()
    mock_press.collect.return_value = press_articles or []

    return patch.multiple(
        collect_job,
        NaverNewsRssCollector=MagicMock(return_value=mock_naver),
        PressRssCollector=MagicMock(return_value=mock_press),
    )


def test_run_collect_job_returns_and_marks_new_articles(tmp_path, monkeypatch):
    monkeypatch.setattr(collect_job, "DATA_DIR", tmp_path)
    article = _article("https://example.com/a", "삼성생명 소식")

    with _patch_collectors([article]):
        result = collect_job.run_collect_job()

    assert [a.url for a in result] == ["https://example.com/a"]

    store = SqliteStore(tmp_path / "news_alert.db")
    assert store.has_seen("https://example.com/a") is True


def test_run_collect_job_excludes_already_seen_articles(tmp_path, monkeypatch):
    monkeypatch.setattr(collect_job, "DATA_DIR", tmp_path)
    article = _article("https://example.com/a", "삼성생명 소식")

    with _patch_collectors([article]):
        first = collect_job.run_collect_job()
        second = collect_job.run_collect_job()

    assert len(first) == 1
    assert second == []


def test_run_collect_job_combines_both_collectors(tmp_path, monkeypatch):
    monkeypatch.setattr(collect_job, "DATA_DIR", tmp_path)
    naver_article = _article("https://example.com/naver", "네이버발 기사")
    press_article = _article("https://example.com/press", "언론사발 기사")

    with _patch_collectors([naver_article], [press_article]):
        result = collect_job.run_collect_job()

    assert {a.url for a in result} == {
        "https://example.com/naver",
        "https://example.com/press",
    }
