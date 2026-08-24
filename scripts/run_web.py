#!/usr/bin/env python
"""요약된 기사를 최신순으로 보여주는 웹 조회 페이지를 로컬에서 띄운다.

사용법:
    python scripts/run_web.py
"""

from news_alert.web.app import create_app

if __name__ == "__main__":
    create_app().run(debug=True, host="127.0.0.1", port=5000)
