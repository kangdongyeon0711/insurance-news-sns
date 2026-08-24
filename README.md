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

## 뉴스 요약 (Claude API)

`LlmSummarizer`(`summarizers/llm_summarizer.py`)는 Claude API(`messages.parse` +
Pydantic 구조화 출력)로 기사 본문을 3줄 이내로 요약하고, 언급된 보험사명과 핵심
키워드를 함께 추출한다.

```python
from news_alert.summarizers.llm_summarizer import LlmSummarizer

summarizer = LlmSummarizer()  # 기본 모델: claude-opus-5
result = summarizer.summarize(article)

print(result.summary)    # 3줄 이내 요약 (줄바꿈으로 구분)
print(result.insurers)   # 예: ["삼성생명"]
print(result.keywords)   # 예: ["3분기 실적", "배당"]
```

**API 키는 반드시 `.env`의 `ANTHROPIC_API_KEY` 환경변수로 관리한다. 코드에
하드코딩하지 않는다.** `LlmSummarizer`는 이 환경변수가 비어 있으면 즉시
`RuntimeError`를 던져 하드코딩 없이도 설정 누락을 바로 알 수 있게 한다.

```bash
cp .env.example .env
# .env 파일을 열어 ANTHROPIC_API_KEY=sk-ant-... 값을 채운다
```

시스템 프롬프트는 "너는 보험업계 뉴스 요약 전문가야. 핵심 사실만 간결하게 3줄
이내로 요약해. ... 보험사명과 핵심 키워드를 함께 추출해" 형태로
`llm_summarizer.py`의 `SYSTEM_PROMPT`에 정의되어 있다.

## 스케줄러 (1시간마다 자동 실행)

**APScheduler로 실행 (프로세스를 계속 띄워두는 방식):**

```bash
python scripts/scheduler.py
```

**cron으로 실행 (매시 정각):**

```
0 * * * * /path/to/insurance-news-sns/scripts/cron_run.sh >> /path/to/insurance-news-sns/data/cron.log 2>&1
```
