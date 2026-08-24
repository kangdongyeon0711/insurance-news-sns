from datetime import datetime, timezone
from unittest.mock import MagicMock

from news_alert.models.article import Article, SummarizedArticle
from news_alert.pipeline import Pipeline


def _article(url: str) -> Article:
    return Article(
        source="예시언론사",
        title=f"제목-{url}",
        url=url,
        published_at=datetime.now(timezone.utc),
        content="본문",
    )


def test_run_executes_stages_in_order_and_notifies_result():
    collector = MagicMock()
    collector.collect.return_value = [
        _article("https://example.com/a"),
        _article("https://example.com/b"),
    ]

    keep_only_a = MagicMock()
    keep_only_a.apply.side_effect = lambda articles: [a for a in articles if a.url.endswith("a")]

    summarized = SummarizedArticle(
        article=_article("https://example.com/a"), summary="요약", insurers=[], keywords=[]
    )
    summarizer = MagicMock()
    summarizer.summarize.return_value = summarized

    notifier = MagicMock()

    pipeline = Pipeline(
        collectors=[collector],
        filters=[keep_only_a],
        summarizer=summarizer,
        notifiers=[notifier],
    )
    pipeline.run()

    collector.collect.assert_called_once()
    keep_only_a.apply.assert_called_once()
    summarizer.summarize.assert_called_once()
    notifier.send.assert_called_once_with([summarized])


def test_run_skips_article_when_summarizer_raises_but_continues():
    collector = MagicMock()
    collector.collect.return_value = [
        _article("https://example.com/a"),
        _article("https://example.com/b"),
    ]

    ok_summary = SummarizedArticle(
        article=_article("https://example.com/b"), summary="요약", insurers=[], keywords=[]
    )
    summarizer = MagicMock()
    summarizer.summarize.side_effect = [Exception("boom"), ok_summary]

    notifier = MagicMock()

    pipeline = Pipeline(
        collectors=[collector], filters=[], summarizer=summarizer, notifiers=[notifier]
    )
    pipeline.run()

    assert summarizer.summarize.call_count == 2
    sent_articles = notifier.send.call_args.args[0]
    assert len(sent_articles) == 1
    assert sent_articles[0].article.url == "https://example.com/b"


def test_run_sends_to_every_notifier():
    collector = MagicMock()
    collector.collect.return_value = []

    notifier_a = MagicMock()
    notifier_b = MagicMock()

    pipeline = Pipeline(
        collectors=[collector],
        filters=[],
        summarizer=MagicMock(),
        notifiers=[notifier_a, notifier_b],
    )
    pipeline.run()

    notifier_a.send.assert_called_once_with([])
    notifier_b.send.assert_called_once_with([])
