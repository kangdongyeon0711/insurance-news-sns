#!/usr/bin/env bash
# cron으로 수집 job을 1시간마다 실행할 때 사용하는 래퍼 스크립트.
#
# crontab -e 에 아래 줄 추가 (매시 정각 실행):
#   0 * * * * /path/to/insurance-news-sns/scripts/cron_run.sh >> /path/to/insurance-news-sns/data/cron.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."
python -m news_alert.jobs.collect_job
