from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = REPO_ROOT / ".env"


def load_env() -> None:
    """.env 파일을 환경변수로 로드한다.

    이미 셸에 설정되어 있는 환경변수는 덮어쓰지 않는다(python-dotenv 기본
    동작). 각 실행 진입점(jobs/*.py, web/app.py, main.py) 모듈 상단에서
    호출해, ANTHROPIC_API_KEY/USE_MOCK 등을 읽는 코드보다 먼저 실행되도록 한다.
    """
    load_dotenv(dotenv_path=ENV_PATH)
