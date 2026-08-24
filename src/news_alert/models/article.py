from dataclasses import dataclass
from datetime import datetime


@dataclass
class Article:
    source: str
    title: str
    url: str
    published_at: datetime
    content: str


@dataclass
class SummarizedArticle:
    article: Article
    summary: str
