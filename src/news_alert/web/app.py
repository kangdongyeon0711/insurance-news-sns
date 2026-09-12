from pathlib import Path

from flask import Flask, jsonify, render_template, request

from news_alert.filters.insurer_filter import load_insurer_categories
from news_alert.models.article import SummarizedArticle
from news_alert.storage.article_store import ArticleStore
from news_alert.utils.env import load_env

load_env()

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = REPO_ROOT / "config"
DATA_DIR = REPO_ROOT / "data"

# insurers.json의 세부 카테고리를 웹 필터 드롭다운 그룹으로 묶는다.
# life/non_life는 "보험사" 하나로 합치고, 정유사/증권사는 각각 별도 드롭다운으로 둔다.
FILTER_GROUPS = {
    "보험사": ["life", "non_life"],
    "정유사": ["정유사"],
    "증권사": ["증권사"],
}


def create_app(db_path: Path | None = None) -> Flask:
    """요약된 기사를 최신순으로 보여주고 보험사별로 필터링하는 조회 페이지.

    파이프라인(수집→필터링→요약→발송) 자체의 단계는 아니며, jobs/summarize_job.py가
    저장해 둔 결과(ArticleStore)를 읽기 전용으로 보여주는 별도의 뷰어다.
    """
    app = Flask(__name__)
    article_store = ArticleStore(db_path or DATA_DIR / "news_alert.db")

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/insurers")
    def api_insurers():
        categories = load_insurer_categories(CONFIG_DIR / "insurers.json")
        grouped = {
            label: [name for key in keys for name in categories.get(key, [])]
            for label, keys in FILTER_GROUPS.items()
        }
        return jsonify(grouped)

    @app.get("/api/articles")
    def api_articles():
        insurer = request.args.get("insurer") or None
        limit = request.args.get("limit", default=50, type=int)
        articles = article_store.list_recent(limit=limit, insurer=insurer)
        return jsonify([_serialize(a) for a in articles])

    return app


def _serialize(summarized: SummarizedArticle) -> dict:
    article = summarized.article
    return {
        "title": article.title,
        "url": article.url,
        "source": article.source,
        "published_at": article.published_at.isoformat(),
        "summary": summarized.summary,
        "insurers": summarized.insurers,
        "keywords": summarized.keywords,
    }


if __name__ == "__main__":
    create_app().run(debug=True, port=5000)
