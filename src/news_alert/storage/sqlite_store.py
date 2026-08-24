import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class SqliteStore:
    """이미 처리(수집/발송)된 기사 URL을 기록해 중복 처리를 방지한다."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_articles (
                    url TEXT PRIMARY KEY,
                    seen_at TEXT NOT NULL
                )
                """
            )

    def has_seen(self, url: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM seen_articles WHERE url = ?", (url,)
            ).fetchone()
        return row is not None

    def mark_seen(self, url: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO seen_articles (url, seen_at) VALUES (?, ?)",
                (url, datetime.now(timezone.utc).isoformat()),
            )
