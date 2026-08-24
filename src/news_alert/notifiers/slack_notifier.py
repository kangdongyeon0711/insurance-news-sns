from news_alert.models.article import SummarizedArticle
from news_alert.notifiers.base import BaseNotifier


class SlackNotifier(BaseNotifier):
    """Slack Incoming Webhook으로 요약을 전송한다."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, articles: list[SummarizedArticle]) -> None:
        raise NotImplementedError
