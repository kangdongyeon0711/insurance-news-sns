"""공용 유틸: 경로, .env 로드, 로깅, 날짜, 파일 저장, HTTP 재시도, 시계열 CSV 입출력."""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
SCHEMA_DIR = ROOT / "schemas"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
SERIES_DIR = DATA_DIR / "series"
SNAPSHOT_PATH = DATA_DIR / "latest_snapshot.json"
INBOX_DIR = ROOT / "inbox"
PROCESSED_DIR = ROOT / "processed"
MANIFEST_PATH = PROCESSED_DIR / "manifest.json"
KNOWLEDGE_DIR = ROOT / "knowledge"
REPORTS_DIR = ROOT / "reports"
TMP_REPORTS_DIR = REPORTS_DIR / "tmp"

TOPIC_IDS = [
    "fx_krwusd", "oil", "kr_rate", "kr_govt_bond", "kr_corp_bond",
    "us_rate", "us_treasury", "us_corp_bond",
    "kr_alt_re", "kr_alt_infra", "kr_alt_pe", "kr_alt_pd",
    "us_alt_re", "us_alt_infra", "us_alt_pe", "us_alt_pd",
]


class MissingApiKey(RuntimeError):
    """API 키가 .env/환경변수에 없을 때."""


def load_env() -> None:
    """ROOT/.env를 환경변수로 로드한다 (이미 설정된 값은 덮어쓰지 않음)."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover
        return
    load_dotenv(ROOT / ".env", override=False)


def require_key(name: str) -> str:
    load_env()
    value = os.environ.get(name, "").strip()
    if not value:
        raise MissingApiKey(
            f"{name}가 설정되지 않았습니다. {ROOT / '.env'} 파일에 '{name}=발급받은키'를 추가하세요 "
            f"(.env.example 참고, 발급처는 README.md의 'API 키' 절)."
        )
    return value


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%H:%M:%S"))
        logger.addHandler(handler)
        logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
    return logger


def today() -> date:
    """기준일. 테스트/재현용으로 AS_OF_DATE=YYYY-MM-DD 환경변수로 고정할 수 있다."""
    override = os.environ.get("AS_OF_DATE")
    if override:
        return datetime.strptime(override, "%Y-%m-%d").date()
    return date.today()


def years_ago(n: int, ref: date | None = None) -> date:
    ref = ref or today()
    try:
        return ref.replace(year=ref.year - n)
    except ValueError:  # 2/29
        return ref.replace(year=ref.year - n, day=28)


def days_between(a: date, b: date) -> int:
    return abs((a - b).days)


def load_yaml(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, obj: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)
        f.write("\n")
    tmp.replace(path)
    return path


def save_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def http_get(url: str, params: dict | None = None, retries: int = 3, timeout: int = 30,
             logger: logging.Logger | None = None):
    """GET with 재시도(지수 백오프). 마지막 실패 시 예외를 그대로 올린다."""
    import requests

    log = logger or get_logger("http")
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            log.warning("요청 실패 (%d/%d): %s", attempt, retries, _redact(str(exc)))
            if attempt < retries:
                time.sleep(2 ** attempt)
    assert last_exc is not None
    raise last_exc


def _redact(text: str) -> str:
    """로그에 API 키가 찍히지 않도록 마스킹."""
    for key in ("ECOS_API_KEY", "FRED_API_KEY", "EIA_API_KEY", "DART_API_KEY"):
        v = os.environ.get(key)
        if v:
            text = text.replace(v, "***")
    return text


def write_series_csv(series_id: str, rows: list[tuple[str, float]], directory: Path | None = None) -> Path:
    """rows: [(YYYY-MM-DD, value)] → data/series/{series_id}.csv (date 오름차순, 중복 제거)."""
    import pandas as pd

    directory = directory or SERIES_DIR
    directory.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows, columns=["date", "value"]).dropna()
    df = df.drop_duplicates("date", keep="last").sort_values("date")
    path = directory / f"{series_id}.csv"
    df.to_csv(path, index=False)
    return path


def read_series_csv(series_id: str, directory: Path | None = None):
    """data/series/{series_id}.csv → pandas Series(index=Timestamp, float). 없으면 None."""
    import pandas as pd

    path = (directory or SERIES_DIR) / f"{series_id}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, parse_dates=["date"])
    if df.empty:
        return None
    return df.set_index("date")["value"].astype(float).sort_index()


def load_series_config() -> list[dict]:
    return load_yaml(CONFIG_DIR / "series.yaml")["series"]


def ecos_date(d: date, cycle: str) -> str:
    if cycle == "D":
        return d.strftime("%Y%m%d")
    if cycle == "M":
        return d.strftime("%Y%m")
    if cycle == "Q":
        return f"{d.year}Q{(d.month - 1) // 3 + 1}"
    if cycle == "A":
        return str(d.year)
    raise ValueError(f"지원하지 않는 ECOS 주기: {cycle}")


def parse_ecos_time(t: str, cycle: str) -> str:
    """ECOS TIME 필드 → YYYY-MM-DD (월/분기/연은 기간 말일)."""
    import pandas as pd

    if cycle == "D":
        return f"{t[:4]}-{t[4:6]}-{t[6:8]}"
    if cycle == "M":
        return (pd.Timestamp(f"{t[:4]}-{t[4:6]}-01") + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d")
    if cycle == "Q":
        q = int(t[-1])
        return (pd.Timestamp(f"{t[:4]}-{q * 3:02d}-01") + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d")
    if cycle == "A":
        return f"{t[:4]}-12-31"
    raise ValueError(cycle)


def stale_threshold_days(cycle: str) -> int:
    """원칙 7: 일별/주별은 7일. 월별 이상은 발표 주기상 7일 기준이 무의미하므로 별도 기준(README 설계 결정)."""
    return {"D": 7, "W": 10, "M": 45, "Q": 120, "A": 400}.get(cycle, 7)


def iso(d: date | datetime) -> str:
    return d.strftime("%Y-%m-%d")


def week_ago(n: int = 1, ref: date | None = None) -> date:
    return (ref or today()) - timedelta(days=7 * n)


def set_verified(series_id: str, verified: bool, path: Path | None = None) -> bool:
    """config/series.yaml에서 해당 series_id 항목의 verified 값을 주석을 보존한 채 갱신한다."""
    import re

    path = path or CONFIG_DIR / "series.yaml"
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        if re.search(rf"series_id:\s*{re.escape(series_id)}\b", line):
            start = i
            break
    if start is None:
        return False
    value = "true" if verified else "false"
    # 같은 줄(flow 스타일) 또는 다음 항목 시작 전까지의 블록에서 verified 찾기
    for j in range(start, len(lines)):
        if j > start and re.match(r"\s*-\s", lines[j]):
            break
        if "verified:" in lines[j]:
            lines[j] = re.sub(r"verified:\s*(true|false)", f"verified: {value}", lines[j])
            path.write_text("".join(lines), encoding="utf-8")
            return True
    return False


ASSET_CLASSES = ["국공채", "특수채", "금융채", "회사채", "해외채", "주식", "수익증권", "해외주식", "대출-부동산PF",
                 "대출-부동산담보", "대출-기업", "대출-신용/약관", "부동산", "대체-인프라", "대체-PE", "대체-사모대출",
                 "현금예금", "기타"]


def class_order(c: str) -> int:
    return ASSET_CLASSES.index(c) if c in ASSET_CLASSES else len(ASSET_CLASSES)
