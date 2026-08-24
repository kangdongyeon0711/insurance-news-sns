from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from news_alert.jobs import summarize_job
from news_alert.models.article import Article, SummarizedArticle
from news_alert.storage.article_store import ArticleStore


def _article(url: str, title: str) -> Article:
    return Article(
        source="예시언론사",
        title=title,
        url=url,
        published_at=datetime.now(timezone.utc),
        content="",
    )


def _patch_collectors_and_summarizer(naver_articles, summarizer_mock):
    mock_naver = MagicMock()
    mock_naver.collect.return_value = naver_articles
    mock_press = MagicMock()
    mock_press.collect.return_value = []

    return patch.multiple(
        summarize_job,
        NaverNewsRssCollector=MagicMock(return_value=mock_naver),
        PressRssCollector=MagicMock(return_value=mock_press),
        LlmSummarizer=MagicMock(return_value=summarizer_mock),
    )


def test_run_summarize_job_filters_by_insurer_and_persists(tmp_path, monkeypatch):
    monkeypatch.setattr(summarize_job, "DATA_DIR", tmp_path)

    relevant = _article("https://example.com/relevant", "삼성생명, 신제품 출시")
    irrelevant = _article("https://example.com/irrelevant", "전혀 관련 없는 기사")

    fake_summary = SummarizedArticle(
        article=relevant, summary="요약1\n요약2\n요약3", insurers=["삼성생명"], keywords=["신제품"]
    )
    mock_summarizer = MagicMock()
    mock_summarizer.summarize.return_value = fake_summary

    with _patch_collectors_and_summarizer([relevant, irrelevant], mock_summarizer):
        result = summarize_job.run_summarize_job()

    assert len(result) == 1
    assert result[0].article.url == "https://example.com/relevant"
    mock_summarizer.summarize.assert_called_once_with(relevant)

    store = ArticleStore(tmp_path / "news_alert.db")
    stored = store.list_recent(limit=10)
    assert [a.article.url for a in stored] == ["https://example.com/relevant"]


def test_run_summarize_job_skips_article_on_summarize_error(tmp_path, monkeypatch):
    monkeypatch.setattr(summarize_job, "DATA_DIR", tmp_path)

    relevant = _article("https://example.com/relevant", "한화생명 관련 소식")
    mock_summarizer = MagicMock()
    mock_summarizer.summarize.side_effect = Exception("boom")

    with _patch_collectors_and_summarizer([relevant], mock_summarizer):
        result = summarize_job.run_summarize_job()

    assert result == []


def test_run_summarize_job_does_not_reprocess_already_seen_articles(tmp_path, monkeypatch):
    monkeypatch.setattr(summarize_job, "DATA_DIR", tmp_path)

    relevant = _article("https://example.com/relevant", "삼성화재 소식")
    fake_summary = SummarizedArticle(
        article=relevant, summary="요약", insurers=["삼성화재"], keywords=[]
    )
    mock_summarizer = MagicMock()
    mock_summarizer.summarize.return_value = fake_summary

    with _patch_collectors_and_summarizer([relevant], mock_summarizer):
        first = summarize_job.run_summarize_job()
        second = summarize_job.run_summarize_job()

    assert len(first) == 1
    assert len(second) == 0
