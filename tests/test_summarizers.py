from news_alert.summarizers.llm_summarizer import LlmSummarizer


def test_llm_summarizer_placeholder():
    s = LlmSummarizer(model="claude-sonnet-5", max_summary_chars=200)
    assert s.max_summary_chars == 200
