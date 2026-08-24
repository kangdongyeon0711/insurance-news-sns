#!/usr/bin/env python
"""1시간마다 뉴스 수집+요약 job(run_summarize_job)을 실행하는 APScheduler 스케줄러.

수집 -> 중복 제거 -> 보험사 관련 필터링 -> Claude 요약 -> 저장까지 수행하며,
저장된 결과는 웹 조회 페이지(news_alert.web.app)가 그대로 읽어 보여준다.
ANTHROPIC_API_KEY 환경변수(.env)가 설정되어 있어야 한다.

사용법:
    python scripts/scheduler.py

크론으로 대체하려면 scripts/cron_run.sh와 README의 크론탭 예시를 참고한다.
"""

from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from news_alert.jobs.summarize_job import run_summarize_job
from news_alert.utils.logger import get_logger

logger = get_logger(__name__)


def main() -> None:
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
