from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from news_alert.models.article import Article
from news_alert.summarizers.llm_summarizer import SYSTEM_PROMPT, LlmSummarizer, _ArticleAnalysis


def _article() -> Article:
    return Article(
        source="예시언론사",
        title="삼성생명, 3분기 실적 발표",
        url="https://example.com/a",
        published_at=datetime.now(timezone.utc),
        content="삼성생명이 3분기 순이익이 전년 대비 늘었다고 밝혔다. 배당 확대도 검토 중이다.",
    )


def test_init_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("USE_MOCK", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        LlmSummarizer()


def test_summarize_calls_claude_with_system_prompt_and_parses_result(monkeypatch):
    monkeypatch.delenv("USE_MOCK", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    analysis = _ArticleAnalysis(
        summary_lines=["삼성생명 3분기 순이익 증가.", "배당 확대 검토 중.", "실적 발표는 오늘 있었다."],
        insurers=["삼성생명"],
        keywords=["3분기 실적", "배당"],
    )
    mock_response = SimpleNamespace(parsed_output=analysis)

    with patch("news_alert.summarizers.llm_summarizer.anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.parse.return_value = mock_response
        mock_anthropic_cls.return_value = mock_client

        summarizer = LlmSummarizer()
        result = summarizer.summarize(_article())

    call_kwargs = mock_client.messages.parse.call_args.kwargs
    assert call_kwargs["system"] == SYSTEM_PROMPT
    assert call_kwargs["model"] == "claude-opus-5"
    assert call_kwargs["output_format"] is _ArticleAnalysis
    assert "삼성생명" in call_kwargs["messages"][0]["content"]

    assert result.summary == (
        "삼성생명 3분기 순이익 증가.\n배당 확대 검토 중.\n실적 발표는 오늘 있었다."
    )
    assert result.insurers == ["삼성생명"]
    assert result.keywords == ["3분기 실적", "배당"]
    assert result.article.title == "삼성생명, 3분기 실적 발표"


def test_summarize_truncates_to_max_summary_lines(monkeypatch):
    monkeypatch.delenv("USE_MOCK", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    analysis = _ArticleAnalysis(
        summary_lines=["한 줄", "두 줄", "세 줄", "네 줄"],
        insurers=[],
        keywords=[],
    )
    mock_response = SimpleNamespace(parsed_output=analysis)

    with patch("news_alert.summarizers.llm_summarizer.anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.parse.return_value = mock_response
        mock_anthropic_cls.return_value = mock_client

        summarizer = LlmSummarizer(max_summary_lines=3)
        result = summarizer.summarize(_article())

    assert result.summary == "한 줄\n두 줄\n세 줄"


def test_init_does_not_require_api_key_in_mock_mode(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("USE_MOCK", "true")

    summarizer = LlmSummarizer()

    assert summarizer.client is None


def test_summarize_in_mock_mode_never_calls_claude_api(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("USE_MOCK", "true")

    article = _article()
    with patch("news_alert.summarizers.llm_summarizer.anthropic.Anthropic") as mock_anthropic_cls:
        summarizer = LlmSummarizer()
        result = summarizer.summarize(article)

    mock_anthropic_cls.assert_not_called()
    assert result.summary == f"{article.content[:100]}...(요약 테스트)"
    assert "삼성생명" in result.insurers
    assert result.article.title == "삼성생명, 3분기 실적 발표"


def test_summarize_in_mock_mode_truncates_content_to_100_chars(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("USE_MOCK", "true")

    article = Article(
        source="예시언론사",
        title="긴 본문 테스트",
        url="https://example.com/long",
        published_at=datetime.now(timezone.utc),
        content="가" * 150,
    )

    with patch("news_alert.summarizers.llm_summarizer.anthropic.Anthropic"):
        summarizer = LlmSummarizer()
        result = summarizer.summarize(article)

    assert result.summary == ("가" * 100) + "...(요약 테스트)"
