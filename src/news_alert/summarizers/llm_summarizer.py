from news_alert.models.article import Article, SummarizedArticle
from news_alert.summarizers.base import BaseSummarizer


class LlmSummarizer(BaseSummarizer):
    """LLM API를 호출해 기사를 요약한다."""

    def __init__(self, model: str, max_summary_chars: int):
        self.model = model
        self.max_summary_chars = max_summary_chars

    def summarize(self, article: Article) -> SummarizedArticle:
        raise NotImplementedError
