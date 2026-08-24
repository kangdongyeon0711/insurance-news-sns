from dataclasses import dataclass, field
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
    insurers: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
