from datetime import datetime, timezone

from news_alert.filters.insurer_filter import (
    InsurerFilter,
    load_insurer_categories,
    load_insurer_names,
    mentions_insurer,
    normalize_for_match,
)
from news_alert.models.article import Article


def _article(title: str, content: str = "") -> Article:
    return Article(
        source="예시언론사",
        title=title,
        url="https://example.com/a",
        published_at=datetime.now(timezone.utc),
        content=content,
    )


def test_normalize_for_match_removes_whitespace():
    assert normalize_for_match("삼성 생명") == "삼성생명"
    assert normalize_for_match("삼성생명") == "삼성생명"


def test_mentions_insurer_matches_exact_and_spaced_variant():
    names = ["삼성생명"]
    assert mentions_insurer("삼성생명, 3분기 실적 발표", names) is True
    assert mentions_insurer("삼성 생명, 3분기 실적 발표", names) is True
    assert mentions_insurer("교보생명 관련 소식", names) is False


def test_load_insurer_names_flattens_categories(tmp_path):
    insurers_path = tmp_path / "insurers.json"
    insurers_path.write_text(
        '{"life": ["삼성생명"], "non_life": ["삼성화재"]}', encoding="utf-8"
    )
    names = load_insurer_names(insurers_path)
    assert set(names) == {"삼성생명", "삼성화재"}


def test_load_insurer_categories_keeps_structure(tmp_path):
    insurers_path = tmp_path / "insurers.json"
    insurers_path.write_text(
        '{"life": ["삼성생명"], "정유사": ["GS칼텍스"]}', encoding="utf-8"
    )
    categories = load_insurer_categories(insurers_path)
    assert categories == {"life": ["삼성생명"], "정유사": ["GS칼텍스"]}


def test_insurer_filter_uses_real_config():
    config_path = (
        __import__("pathlib").Path(__file__).resolve().parents[1] / "config" / "insurers.json"
    )
    f = InsurerFilter(insurers_path=config_path)

    articles = [
        _article("한화생명, 신규 상품 출시", "이번 상품은..."),
        _article("한화 생명 보험료 인상 검토", "관계자에 따르면..."),
        _article("전혀 관련 없는 기사", "보험사 이름이 없다"),
    ]
    result = f.apply(articles)

    assert [a.title for a in result] == ["한화생명, 신규 상품 출시", "한화 생명 보험료 인상 검토"]


def test_insurer_filter_loads_all_tracked_companies():
    config_path = (
        __import__("pathlib").Path(__file__).resolve().parents[1] / "config" / "insurers.json"
    )
    f = InsurerFilter(insurers_path=config_path)
    assert len(f.insurer_names) == 24
    assert "GS칼텍스" in f.insurer_names
    assert "SK에너지" in f.insurer_names
    assert "S-OIL" in f.insurer_names
    assert "HD현대오일뱅크" in f.insurer_names
