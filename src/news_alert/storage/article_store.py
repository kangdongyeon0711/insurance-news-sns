import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from news_alert.models.article import Article, SummarizedArticle


class ArticleStore:
    """요약이 끝난 기사(SummarizedArticle)를 저장하고 최신순으로 조회한다.

    웹 조회 페이지(web/app.py)가 읽는 데이터 소스다. 수집/중복방지에 쓰이는
    SqliteStore(seen_articles)와는 다른 테이블(summarized_articles)을 쓰므로
    같은 DB 파일을 공유해도 서로 간섭하지 않는다.
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS summarized_articles (
                    url TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    insurers TEXT NOT NULL,
                    keywords TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def save(self, summarized: SummarizedArticle) -> None:
        article = summarized.article
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO summarized_articles
                    (url, source, title, published_at, summary, insurers, keywords, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    article.url,
                    article.source,
                    article.title,
                    article.published_at.isoformat(),
                    summarized.summary,
                    json.dumps(summarized.insurers, ensure_ascii=False),
                    json.dumps(summarized.keywords, ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def list_recent(self, limit: int = 50, insurer: str | None = None) -> list[SummarizedArticle]:
        """발행 시각 최신순으로 기사를 반환한다. insurer가 주어지면 해당 보험사가

        insurers 목록에 포함된 기사만 반환한다.
        """
        query = "SELECT * FROM summarized_articles"
        params: list[str | int] = []
        if insurer:
            query += " WHERE insurers LIKE ?"
            params.append(f'%"{insurer}"%')
        query += " ORDER BY published_at DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        return [self._row_to_summarized_article(row) for row in rows]

    @staticmethod
    def _row_to_summarized_article(row: sqlite3.Row) -> SummarizedArticle:
        article = Article(
            source=row["source"],
            title=row["title"],
            url=row["url"],
            published_at=datetime.fromisoformat(row["published_at"]),
            content="",
        )
        return SummarizedArticle(
            article=article,
            summary=row["summary"],
            insurers=json.loads(row["insurers"]),
            keywords=json.loads(row["keywords"]),
        )
