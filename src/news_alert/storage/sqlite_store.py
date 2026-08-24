import sqlite3
from pathlib import Path


class SqliteStore:
    """발송 완료된 기사 URL을 기록해 중복 발송을 방지한다."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    def is_sent(self, url: str) -> bool:
        raise NotImplementedError

    def mark_sent(self, url: str) -> None:
        raise NotImplementedError
