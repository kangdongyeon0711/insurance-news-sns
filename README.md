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

## 테스트

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

모듈별 테스트는 외부 의존성(네트워크 요청, Claude API, 파일시스템)을 mock/tmp_path로
대체해 각 모듈이 독립적으로 정상 동작하는지 검증한다.

| 모듈 | 테스트 파일 | 확인 내용 |
|---|---|---|
| `collectors/naver_news_collector.py` | `test_naver_collector.py` | RSS 파싱, HTML 태그 제거, 키워드 간 중복 제거, 피드 실패 시 스킵 |
| `collectors/press_rss_collector.py` | `test_press_rss_collector.py` | CSV 로딩, 언론사명 태깅, 피드 하나 실패해도 나머지 계속 처리 |
| `filters/dedup_filter.py`, `storage/sqlite_store.py` | `test_dedup_filter_storage.py` | URL 기준 중복 제거, SQLite 저장/조회 |
| `filters/insurer_filter.py` | `test_insurer_filter.py` | 20개 보험사 매칭, 공백 표기 차이(`삼성생명`/`삼성 생명`) 흡수 |
| `summarizers/llm_summarizer.py` | `test_summarizers.py` | 시스템 프롬프트 전달, API 키 미설정 시 실패, 3줄 초과 요약 자르기 |
| `storage/article_store.py` | `test_article_store.py` | 요약 결과 저장, 최신순 정렬, 보험사 필터, upsert |
| `web/app.py` | `test_web_app.py` | `/`, `/api/articles`(정렬·필터), `/api/insurers` |
| `pipeline.py` | `test_pipeline.py` | 4단계 순서대로 실행, 개별 기사 요약 실패 시에도 파이프라인 계속 진행 |
| `jobs/collect_job.py` | `test_collect_job.py` | 여러 수집기 결합, 중복 제거, "본 기사" 마킹 |
| `jobs/summarize_job.py` | `test_summarize_job.py` | 수집→중복제거→보험사필터→요약→저장 전체 흐름 |
| `utils/config_loader.py` | `test_config_loader.py` | YAML 로딩 |
| `utils/logger.py` | `test_logger.py` | 로거 이름/레벨, 핸들러 중복 방지 |
| `utils/feed.py` | `test_feed_utils.py` | HTML 제거, 발행시각 파싱 |
| `models/article.py` | `test_models.py` | `SummarizedArticle` 기본값(mutable default 공유 버그 가드) |

`collectors/rss_collector.py`, `collectors/api_collector.py`, `filters/keyword_filter.py`,
`notifiers/*`는 아직 인터페이스만 정의된 미구현 스텁이라(실제 로직이 없어 검증할
동작이 없음) 테스트 대상에서 제외했다. 실제 구현을 채울 때 위 표와 같은 방식으로
테스트를 추가한다.

GitHub Actions(`.github/workflows/test.yml`)가 push/PR마다 `pytest tests/ -v`를
자동 실행해 회귀를 잡는다.

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

## 조회 웹페이지 (요약된 기사 최신순 + 보험사 필터)

`jobs/summarize_job.py`가 저장한 요약 결과를 최신순으로 보여주고 보험사별로
필터링하는 Flask 웹페이지다. 파이프라인의 5번째 단계가 아니라 저장된 결과를
읽기만 하는 별도 뷰어이며, 자세한 설명은 [CLAUDE.md](./CLAUDE.md#조회-웹페이지-파이프라인-외부)를 참고한다.

```bash
python scripts/run_web.py
# 또는
flask --app news_alert.web.app run
```

`http://127.0.0.1:5000`에 접속하면:
- 기사 목록이 `published_at` 최신순으로 정렬되어 카드 형태로 표시된다.
- 상단 드롭다운으로 `config/insurers.json`에 등록된 20개 보험사 중 하나를
  선택해 필터링할 수 있다 ("전체" 선택 시 전체 표시).
- 각 카드는 제목(원문 링크), 언론사·발행시각, 3줄 요약, 보험사/키워드 태그를 보여준다.

REST API만 필요하면 `GET /api/articles?insurer=삼성생명&limit=50`,
`GET /api/insurers`를 직접 호출해도 된다.

## 전체 파이프라인 실행 (수집 → 필터 → 요약 → 저장)

`jobs/summarize_job.py`는 수집(네이버 뉴스 검색 RSS + 언론사 RSS) → 중복 제거 →
보험사명 필터링(`insurers.json`) → Claude 3줄 요약 → `ArticleStore` 저장까지
한 번에 수행한다. `ANTHROPIC_API_KEY`가 `.env`에 설정되어 있어야 한다.

```bash
python -m news_alert.jobs.summarize_job
```

## 배포 (1시간마다 자동 실행)

`summarize_job`을 1시간마다 자동 실행해 조회 웹페이지의 데이터를 최신 상태로
유지하는 방법은 두 가지다. **둘 다 "수집·요약 job을 자동 실행"하는 것이지,
웹페이지 자체를 호스팅해 주지는 않는다** — 웹페이지(`web/app.py`)를 다른 사람도
접속 가능하게 하려면 결국 상시 실행되는 서버가 필요하다.

### 옵션 A: 서버(AWS EC2 등 / 개인서버) + cron 또는 systemd

가장 단순한 구성: 서버 하나에서 (1) job을 주기 실행하고 (2) 웹페이지를 계속
띄워둔다. 둘 다 같은 `data/news_alert.db`를 보므로 별도 동기화가 필요 없다.

```bash
# 서버에서 최초 1회
git clone <repo-url> /opt/insurance-news-sns && cd /opt/insurance-news-sns
python -m venv .venv && .venv/bin/pip install -e ".[prod]"
cp .env.example .env   # ANTHROPIC_API_KEY 등 채우기
```

**job 실행 — cron 또는 systemd 중 택1:**

- cron: `crontab -e`에 아래 한 줄 추가 (매시 정각)
  ```
  0 * * * * /opt/insurance-news-sns/scripts/cron_run.sh >> /opt/insurance-news-sns/data/cron.log 2>&1
  ```
- systemd: `deploy/systemd/news-alert-scheduler.service`를
  `/etc/systemd/system/`에 복사(경로/`User=` 수정 후) →
  `systemctl enable --now news-alert-scheduler`
  (내부적으로 `scripts/scheduler.py`의 APScheduler가 1시간 간격을 관리한다)

**웹페이지 실행 — 프로덕션 WSGI 서버(gunicorn)로:**

```bash
pip install -e ".[prod]"
gunicorn --bind 0.0.0.0:8000 "news_alert.web.app:create_app()"
```

또는 `deploy/systemd/news-alert-web.service`를 등록해 상시 실행하고, 앞단에
nginx 등 리버스 프록시를 붙여 도메인/HTTPS를 연결한다.

### 옵션 B: GitHub Actions 스케줄

`.github/workflows/summarize.yml`이 **매시 정각(UTC)** `summarize_job`을 자동
실행한다. 웹페이지를 굳이 상시 호스팅할 필요 없이 "요약 결과가 계속 쌓이게만"
하고 싶을 때 적합하다.

- 저장소 Settings → Secrets and variables → Actions에 `ANTHROPIC_API_KEY`를 등록해야 한다.
- GitHub Actions 러너는 매 실행마다 새로 초기화되므로, 중복 방지 DB와 요약
  결과(`data/news_alert.db`)가 사라지지 않도록 `actions/cache`로 실행 간에
  이어받는다 (워크플로 안에 이미 구성되어 있다).
- 수동 실행은 GitHub 저장소 Actions 탭 → "Summarize Insurance News" →
  "Run workflow"(`workflow_dispatch`)로 가능하다.
- **주의**: Actions 캐시는 웹페이지가 직접 읽을 수 있는 위치가 아니다. 이
  방식만으로는 웹페이지를 서비스할 수 없고, 요약 데이터를 계속 쌓아두는
  용도(추후 다른 곳에서 조회)로만 쓴다. 실제로 웹페이지까지 띄우려면
  옵션 A(서버)를 병행해야 한다.
