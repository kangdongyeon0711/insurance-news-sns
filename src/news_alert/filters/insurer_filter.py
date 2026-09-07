import json
import re
from pathlib import Path

from news_alert.filters.base import BaseFilter
from news_alert.models.article import Article

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_for_match(text: str) -> str:
    """공백을 모두 제거해 '삼성생명'과 '삼성 생명' 같은 표기 차이를 흡수한다."""
    return _WHITESPACE_RE.sub("", text or "")


def load_insurer_categories(path: Path) -> dict[str, list[str]]:
    """insurers.json을 카테고리(life/non_life/정유사 등)별 구조 그대로 읽는다."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_insurer_names(path: Path) -> list[str]:
    """insurers.json(카테고리별 회사명 목록)에서 전체 이름을 평탄화해 읽는다."""
    categories = load_insurer_categories(path)
    return [name for names in categories.values() for name in names]


def mentions_insurer(text: str, insurer_names: list[str]) -> bool:
    """text(제목+본문 등)에 insurer_names 중 하나라도 언급되면 True.

    비교 전 양쪽 모두 공백을 제거하고 부분 문자열로 매칭하므로
    '삼성 생명'처럼 띄어쓰기가 다른 표기도 '삼성생명'과 동일하게 인식한다.
    """
    haystack = normalize_for_match(text)
    return any(normalize_for_match(name) in haystack for name in insurer_names)


class InsurerFilter(BaseFilter):
    """insurers.json에 등록된 보험사명이 제목 또는 본문에 포함된 기사만 남긴다."""

    def __init__(self, insurers_path: Path):
        self.insurer_names = load_insurer_names(Path(insurers_path))

    def apply(self, articles: list[Article]) -> list[Article]:
        return [
            article
            for article in articles
            if mentions_insurer(f"{article.title} {article.content}", self.insurer_names)
        ]
