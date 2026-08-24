from news_alert.models.article import SummarizedArticle
from news_alert.notifiers.base import BaseNotifier


class TelegramNotifier(BaseNotifier):
    """텔레그램 봇 API로 요약을 전송한다."""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send(self, articles: list[SummarizedArticle]) -> None:
        raise NotImplementedError
