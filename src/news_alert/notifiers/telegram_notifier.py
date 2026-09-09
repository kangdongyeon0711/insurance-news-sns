import requests

from news_alert.models.article import SummarizedArticle
from news_alert.notifiers.base import BaseNotifier
from news_alert.utils.logger import get_logger
from news_alert.utils.mock import is_mock_mode

logger = get_logger(__name__)

_TELEGRAM_MESSAGE_LIMIT = 3500


class TelegramNotifier(BaseNotifier):
    """텔레그램 봇 API(sendMessage)로 요약된 기사를 전송한다."""

    def __init__(self, bot_token: str, chat_id: str, timeout: int = 10):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.timeout = timeout

    def send(self, articles: list[SummarizedArticle]) -> None:
        if not articles:
            return

        if is_mock_mode():
            logger.info("USE_MOCK=true — 텔레그램 발송 대신 로그만 남깁니다 (%d건)", len(articles))
            return

        for chunk in self._chunk_messages(articles):
            self._send_message(chunk)

    def _chunk_messages(self, articles: list[SummarizedArticle]) -> list[str]:
        """텔레그램 메시지 길이 제한(4096자)을 넘지 않도록 기사 블록을 나눠 담는다."""
        chunks: list[str] = []
        current = ""
        for article in articles:
            block = self._format_article(article)
            if current and len(current) + len(block) > _TELEGRAM_MESSAGE_LIMIT:
                chunks.append(current)
                current = ""
            current += block
        if current:
            chunks.append(current)
        return chunks

    @staticmethod
    def _format_article(article: SummarizedArticle) -> str:
        insurers = ", ".join(article.insurers) if article.insurers else "-"
        return (
            f"[{article.article.source}] {article.article.title}\n"
            f"{article.summary}\n"
            f"관련: {insurers}\n"
            f"{article.article.url}\n\n"
        )

    def _send_message(self, text: str) -> None:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        response = requests.post(
            url,
            json={
                "chat_id": self.chat_id,
                "text": text,
                "disable_web_page_preview": True,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
