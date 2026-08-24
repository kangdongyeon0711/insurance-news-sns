from news_alert.models.article import SummarizedArticle
from news_alert.notifiers.base import BaseNotifier


class EmailNotifier(BaseNotifier):
    """SMTP를 통해 요약을 이메일로 전송한다."""

    def __init__(self, smtp_host: str, smtp_port: int, sender: str, recipients: list[str]):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.sender = sender
        self.recipients = recipients

    def send(self, articles: list[SummarizedArticle]) -> None:
        raise NotImplementedError
