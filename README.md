# insurance-news-sns

보험사 관련 뉴스를 자동으로 수집·필터링·요약하여 Slack/이메일/텔레그램 등으로 알림을 발송하는 서비스입니다.

파이프라인: **수집 → 필터링 → 요약 → 발송**

아키텍처와 폴더 구조에 대한 자세한 설명은 [CLAUDE.md](./CLAUDE.md)를 참고하세요.

## 빠른 시작

```bash
pip install -e ".[dev]"
cp .env.example .env  # 값 채워넣기
python -m news_alert.main
```

## 뉴스 수집 (네이버 뉴스 검색 RSS + 언론사 RSS)

- `config/settings.yaml`의 `naver_news.keywords`에 검색 키워드를 등록하면
  `NaverNewsRssCollector`가 네이버 뉴스 검색 RSS에서 최신 기사를 가져온다.
  이 엔드포인트는 네이버가 공식 지원하지 않으므로 응답이 비정상이면
  `base_url`을 갱신해야 한다.
- `config/press_rss.csv`에 `name,url` 형식으로 언론사 RSS 피드를 등록하면
  `PressRssCollector`가 각 피드를 순회하며 기사를 가져온다. 예시 값을 실제
  언론사 RSS 주소로 교체해야 한다.
- 두 수집기 모두 이미 처리한 기사(URL 기준)는 `data/news_alert.db`(SQLite)에
  기록해 다음 실행부터 새 기사만 반환한다.

1회 수집 실행:

```bash
python -m news_alert.jobs.collect_job
```

## 보험사명 필터링

`config/insurers.json`에 생명보험사 10개, 손해보험사 10개(총 20개)의 정식 명칭이
카테고리별로 등록되어 있다. `InsurerFilter`(`filters/insurer_filter.py`)는 이 목록에
있는 보험사명이 기사 제목 또는 본문에 포함된 기사만 남긴다.

```python
from pathlib import Path
from news_alert.filters.insurer_filter import InsurerFilter

f = InsurerFilter(insurers_path=Path("config/insurers.json"))
matched = f.apply(articles)
```

매칭 전 문자열의 공백을 모두 제거하므로 `삼성생명`과 `삼성 생명`처럼 띄어쓰기가
다른 표기도 동일하게 인식한다. 단일 문자열에 대해 직접 검사하려면
`mentions_insurer(text, insurer_names)` 함수를 사용한다.

## 스케줄러 (1시간마다 자동 실행)

**APScheduler로 실행 (프로세스를 계속 띄워두는 방식):**

```bash
python scripts/scheduler.py
```

**cron으로 실행 (매시 정각):**

```
0 * * * * /path/to/insurance-news-sns/scripts/cron_run.sh >> /path/to/insurance-news-sns/data/cron.log 2>&1
```
