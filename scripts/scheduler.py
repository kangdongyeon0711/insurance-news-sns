#!/usr/bin/env python
"""1시간마다 뉴스 수집+요약 job(run_summarize_job)을 실행하는 APScheduler 스케줄러.

수집 -> 중복 제거 -> 보험사 관련 필터링 -> Claude 요약 -> 저장까지 수행하며,
저장된 결과는 웹 조회 페이지(news_alert.web.app)가 그대로 읽어 보여준다.
ANTHROPIC_API_KEY 환경변수(.env)가 설정되어 있어야 한다.

콘솔 창 없이(pythonw로, 예: Windows 작업 스케줄러) 실행되는 경우를 대비해
로그를 콘솔뿐 아니라 data/scheduler.log 파일에도 남긴다.

사용법:
    python scripts/scheduler.py

크론으로 대체하려면 scripts/cron_run.sh와 README의 크론탭 예시를 참고한다.
Windows에서 로그온 시 자동 시작하려면 scripts/windows/register_scheduler_task.ps1을
참고한다.
"""

import logging
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from news_alert.jobs.summarize_job import run_summarize_job
from news_alert.utils.logger import get_logger

logger = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = REPO_ROOT / "data" / "scheduler.log"


def _configure_file_logging() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


def main() -> None:
    _configure_file_logging()
    scheduler = BlockingScheduler(timezone=ZoneInfo("Asia/Seoul"))
    scheduler.add_job(
        run_summarize_job,
        trigger=IntervalTrigger(hours=1),
        id="summarize_news",
        max_instances=1,
        coalesce=True,
    )

    logger.info("scheduler starting: summarize job will run every 1 hour")
    run_summarize_job()  # 시작 시 1회 즉시 실행

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("scheduler stopped")


if __name__ == "__main__":
    main()
