#!/usr/bin/env python
"""1시간마다 뉴스 수집 job(run_collect_job)을 실행하는 APScheduler 스케줄러.

사용법:
    python scripts/scheduler.py

크론으로 대체하려면 scripts/cron_run.sh와 README의 크론탭 예시를 참고한다.
"""

from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from news_alert.jobs.collect_job import run_collect_job
from news_alert.utils.logger import get_logger

logger = get_logger(__name__)


def main() -> None:
    scheduler = BlockingScheduler(timezone=ZoneInfo("Asia/Seoul"))
    scheduler.add_job(
        run_collect_job,
        trigger=IntervalTrigger(hours=1),
        id="collect_news",
        max_instances=1,
        coalesce=True,
    )

    logger.info("scheduler starting: collect job will run every 1 hour")
    run_collect_job()  # 시작 시 1회 즉시 실행

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("scheduler stopped")


if __name__ == "__main__":
    main()
