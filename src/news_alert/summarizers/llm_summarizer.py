import os

import anthropic
from pydantic import BaseModel

from news_alert.models.article import Article, SummarizedArticle
from news_alert.summarizers.base import BaseSummarizer
from news_alert.utils.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "너는 보험업계 뉴스 요약 전문가야. 기사 본문을 읽고 핵심 사실만 간결하게 "
    "3줄 이내로 요약해. 각 줄은 완결된 한 문장으로 쓰고, 본문에 없는 추측이나 "
    "의견은 덧붙이지 마. 이어서 기사에 언급된 보험사명과 핵심 키워드를 함께 추출해."
)


class _ArticleAnalysis(BaseModel):
    summary_lines: list[str]
    insurers: list[str]
    keywords: list[str]


class LlmSummarizer(BaseSummarizer):
    """Claude API로 기사를 3줄 요약하고 관련 보험사명/키워드를 함께 추출한다.

    API 키는 코드에 하드코딩하지 않는다. ANTHROPIC_API_KEY 환경변수(.env)에서
    anthropic.Anthropic()이 자동으로 읽어온다.
    """

    def __init__(self, model: str = "claude-opus-5", max_summary_lines: int = 3):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다. "
                ".env 파일에 값을 채운 뒤 다시 시도하세요. "
                "API 키를 코드에 직접 입력하지 마세요."
            )
        self.model = model
        self.max_summary_lines = max_summary_lines
        self.client = anthropic.Anthropic()

    def summarize(self, article: Article) -> SummarizedArticle:
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"제목: {article.title}\n"
                        f"언론사: {article.source}\n"
                        f"본문:\n{article.content}"
                    ),
                }
            ],
            output_format=_ArticleAnalysis,
        )
        analysis = response.parsed_output
        summary = "\n".join(analysis.summary_lines[: self.max_summary_lines])

        return SummarizedArticle(
            article=article,
            summary=summary,
            insurers=analysis.insurers,
            keywords=analysis.keywords,
        )
