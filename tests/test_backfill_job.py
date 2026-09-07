from datetime import datetime, timezone
from unittest.mock import patch

from news_alert.jobs import backfill_job
from news_alert.models.article import Article, SummarizedArticle
from news_alert.storage.article_store import ArticleStore
from news_alert.storage.sqlite_store import SqliteStore


def _article(url: str) -> Article:
    return Article(
        source="예시언론사",
        title=f"제목-{url}",
        url=url,
        published_at=datetime.now(timezone.utc),
        content="",
    )


def test_clear_unsummarized_seen_marks_keeps_only_summarized(tmp_path, monkeypatch):
    monkeypatch.setattr(backfill_job, "DATA_DIR", tmp_path)
    db_path = tmp_path / "news_alert.db"

    dedup_store = SqliteStore(db_path)
    dedup_store.mark_seen("https://example.com/summarized")
    dedup_store.mark_seen("https://example.com/missed-1")
    dedup_store.mark_seen("https://example.com/missed-2")

    article_store = ArticleStore(db_path)
    article_store.save(
        SummarizedArticle(
            article=_article("https://example.com/summarized"),
            summary="요약",
            insurers=[],
            keywords=[],
        )
    )

    cleared = backfill_job.clear_unsummarized_seen_marks()

    assert cleared == 2
    assert dedup_store.has_seen("https://example.com/summarized") is True
    assert dedup_store.has_seen("https://example.com/missed-1") is False
    assert dedup_store.has_seen("https://example.com/missed-2") is False


def test_clear_unsummarized_seen_marks_handles_fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(backfill_job, "DATA_DIR", tmp_path)

    cleared = backfill_job.clear_unsummarized_seen_marks()

    assert cleared == 0


def test_run_backfill_job_clears_then_runs_summarize_job(tmp_path, monkeypatch):
    monkeypatch.setattr(backfill_job, "DATA_DIR", tmp_path)

    with patch.object(
        backfill_job, "run_summarize_job", return_value=["fake-result"]
    ) as mock_run:
        result = backfill_job.run_backfill_job()

    mock_run.assert_called_once()
    assert result == ["fake-result"]
