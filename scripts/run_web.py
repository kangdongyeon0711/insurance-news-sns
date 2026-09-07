#!/usr/bin/env python
"""요약된 기사를 최신순으로 보여주는 웹 조회 페이지를 로컬에서 띄운다.

사용법:
    python scripts/run_web.py

일부 Windows + 최신 Python 조합에서는 Flask 개발 서버의 자동 재시작
기능(리로더)이 별도 프로세스를 띄우는 과정에서 OSError([WinError 10014]
잘못된 포인터 주소)로 죽는 사례가 있다. 그런 경우 use_reloader=False로
리로더만 끄면 우회되는 경우가 많다(코드를 고쳐도 자동 재시작만 안 될 뿐,
서버 자체는 정상 동작한다 — 코드 변경 후에는 이 창에서 직접 재실행해야 함).
"""

from news_alert.web.app import create_app

if __name__ == "__main__":
    create_app().run(debug=True, use_reloader=False, host="127.0.0.1", port=5000)
