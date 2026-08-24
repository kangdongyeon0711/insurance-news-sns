#!/usr/bin/env python
"""waitress로 조회 웹페이지를 서빙한다 (무인 자동 실행용).

scripts/run_web.py(Flask 개발 서버, debug=True + 리로더)는 사람이 직접 띄워두고
지켜보는 로컬 개발용이라 무인 자동 실행(Windows 작업 스케줄러, systemd 등)에는
적합하지 않다. 이 스크립트는 같은 Flask 앱을 waitress(WSGI 프로덕션 서버)로
서빙한다. waitress는 gunicorn과 달리 Windows에서도 정상 동작한다.

콘솔 창 없이(pythonw로) 실행되는 경우를 대비해, 로그를 콘솔뿐 아니라
data/web_server.log 파일에도 남긴다.

환경변수:
    WEB_HOST (기본 127.0.0.1), WEB_PORT (기본 5000)

사용법:
    python scripts/serve_web_waitress.py
"""

import logging
import os
from pathlib import Path

from waitress import serve

from news_alert.web.app import create_app

REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = REPO_ROOT / "data" / "web_server.log"


def _configure_file_logging() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


def main() -> None:
    _configure_file_logging()
    host = os.environ.get("WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("WEB_PORT", "5000"))

    logging.getLogger(__name__).info("serving web viewer on http://%s:%s (waitress)", host, port)
    serve(create_app(), host=host, port=port)


if __name__ == "__main__":
    main()
