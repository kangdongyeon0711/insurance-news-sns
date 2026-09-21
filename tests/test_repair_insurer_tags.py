import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from news_alert.models.article import Article, SummarizedArticle
from news_alert.storage.article_store import ArticleStore

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from repair_insurer_tags import repair_insurer_tags  # noqa: E402

INSURERS_JSON = '{"life": ["삼성생명"], "정유사": ["S-OIL"], "증권사": ["키움증권"]}'


def _insurers_path(tmp_path: Path) -> Path:
    path = tmp_path / "insurers.json"
    path.write_text(INSURERS_JSON, encoding="utf-8")
    return path


def _save(store: ArticleStore, url: str, title: str, summary: str, insurers, keywords) -> None:
    store.save(
        SummarizedArticle(
            article=Article(
                source="예시언론사",
                title=title,
                url=url,
                published_at=datetime.now(timezone.utc),
                content="",
            ),
            summary=summary,
            insurers=insurers,
            keywords=keywords,
        )
    )


def _stored_insurers(store: ArticleStore, url: str) -> list[str]:
    return next(a.insurers for a in store.list_recent(limit=10) if a.article.url == url)


def test_fills_in_tag_left_empty_by_the_llm(tmp_path):
    db_path = tmp_path / "test.db"
    store = ArticleStore(db_path)
    _save(store, "https://example.com/oil", "S-OIL, 마포사옥 글판 새 단장", "S-OIL이 글판을 단장했다.", [], ["마포 사옥"])

    updated, total = repair_insurer_tags(db_path, _insurers_path(tmp_path))

    assert (updated, total) == (1, 1)
    assert _stored_insurers(store, "https://example.com/oil") == ["S-OIL"]


def test_recovers_company_name_stored_only_as_keyword(tmp_path):
    db_path = tmp_path / "test.db"
    store = ArticleStore(db_path)
    _save(store, "https://example.com/kiwoom", "증권가 소식", "실적이 개선됐다.", [], ["키움증권", "실적"])

    repair_insurer_tags(db_path, _insurers_path(tmp_path))

    assert _stored_insurers(store, "https://example.com/kiwoom") == ["키움증권"]


def test_leaves_correct_tags_untouched(tmp_path):
    db_path = tmp_path / "test.db"
    store = ArticleStore(db_path)
    _save(store, "https://example.com/life", "삼성생명 실적 발표", "삼성생명이 발표했다.", ["삼성생명"], ["실적"])

    updated, total = repair_insurer_tags(db_path, _insurers_path(tmp_path))

    assert (updated, total) == (0, 1)
    assert _stored_insurers(store, "https://example.com/life") == ["삼성생명"]


def test_keeps_existing_tags_when_nothing_canonical_is_found(tmp_path):
    db_path = tmp_path / "test.db"
    store = ArticleStore(db_path)
    _save(store, "https://example.com/other", "관련 없는 기사", "아무 회사도 없다.", ["에쓰오일"], ["기타"])

    updated, _ = repair_insurer_tags(db_path, _insurers_path(tmp_path))

    assert updated == 0
    assert _stored_insurers(store, "https://example.com/other") == ["에쓰오일"]


def test_writes_canonical_json_readable_by_the_web_filter(tmp_path):
    db_path = tmp_path / "test.db"
    store = ArticleStore(db_path)
    _save(store, "https://example.com/oil", "S-OIL 소식", "S-OIL이 발표했다.", [], [])

    repair_insurer_tags(db_path, _insurers_path(tmp_path))

    # 웹 필터는 insurers 컬럼을 '%"S-OIL"%'로 LIKE 검색하므로 한글/기호가 이스케이프되면 안 된다.
    assert store.list_recent(limit=10, insurer="S-OIL")
    assert json.dumps(["S-OIL"], ensure_ascii=False) == '["S-OIL"]'
