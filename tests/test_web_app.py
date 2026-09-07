from datetime import datetime, timedelta, timezone

from news_alert.models.article import Article, SummarizedArticle
from news_alert.storage.article_store import ArticleStore
from news_alert.web.app import create_app


def _summarized(url: str, published_at: datetime, insurers: list[str]) -> SummarizedArticle:
    article = Article(
        source="예시언론사",
        title=f"제목-{url}",
        url=url,
        published_at=published_at,
        content="",
    )
    return SummarizedArticle(
        article=article,
        summary="요약 1줄\n요약 2줄\n요약 3줄",
        insurers=insurers,
        keywords=["키워드1"],
    )


def _seeded_client(tmp_path):
    db_path = tmp_path / "test.db"
    store = ArticleStore(db_path)
    now = datetime.now(timezone.utc)

    store.save(_summarized("https://example.com/older", now - timedelta(hours=1), ["한화생명"]))
    store.save(_summarized("https://example.com/newer", now, ["삼성생명"]))

    app = create_app(db_path=db_path)
    return app.test_client()


def test_index_page_returns_html(tmp_path):
    client = _seeded_client(tmp_path)

    response = client.get("/")

    assert response.status_code == 200
    assert "보험 뉴스 요약" in response.get_data(as_text=True)


def test_api_articles_returns_newest_first(tmp_path):
    client = _seeded_client(tmp_path)

    response = client.get("/api/articles")
    data = response.get_json()

    assert response.status_code == 200
    assert [a["url"] for a in data] == [
        "https://example.com/newer",
        "https://example.com/older",
    ]


def test_api_articles_filters_by_insurer(tmp_path):
    client = _seeded_client(tmp_path)

    response = client.get("/api/articles?insurer=삼성생명")
    data = response.get_json()

    assert len(data) == 1
    assert data[0]["url"] == "https://example.com/newer"
    assert data[0]["insurers"] == ["삼성생명"]
    assert data[0]["summary"] == "요약 1줄\n요약 2줄\n요약 3줄"


def test_api_insurers_returns_grouped_categories(tmp_path):
    client = _seeded_client(tmp_path)

    response = client.get("/api/insurers")
    data = response.get_json()

    assert response.status_code == 200
    assert set(data.keys()) == {"보험사", "정유사"}
    assert "삼성생명" in data["보험사"]
    assert "삼성화재" in data["보험사"]
    assert len(data["보험사"]) == 20
    assert set(data["정유사"]) == {"SK에너지", "GS칼텍스", "S-OIL", "HD현대오일뱅크"}
