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

### 환경변수 설정 방법: `.env` 파일 (권장)

`jobs/*.py`, `web/app.py`, `main.py` 등 모든 실행 진입점은 시작할 때
`utils/env.py`의 `load_env()`(`python-dotenv`)로 저장소 루트의 `.env` 파일을
자동으로 읽어 환경변수로 설정한다. 즉 **`.env` 파일에 값을 적어두기만 하면
되고, 매번 셸에서 `export`(bash)나 `$env:`(PowerShell)로 직접 설정할 필요가
없다.** 이미 셸에 설정된 값이 있으면 그게 우선한다(`.env`는 덮어쓰지 않음).

```bash
cp .env.example .env
# .env 파일을 열어 USE_MOCK, ANTHROPIC_API_KEY 등 값을 채운다
python -m news_alert.jobs.summarize_job   # 셸 환경변수 없이도 .env 값 그대로 사용됨
```

## Mock 모드 (API 키·네트워크 없이 전체 파이프라인 시연)

`.env`(또는 셸 환경변수)에서 `USE_MOCK=true`로 설정하면 수집기
(`NaverNewsRssCollector`, `PressRssCollector`)와 요약기(`LlmSummarizer`)가
실제 네트워크·Claude API를 전혀 호출하지 않고 미리 만들어둔 샘플 데이터를
반환한다. `ANTHROPIC_API_KEY`도 필요 없다 — 로컬 개발, 데모, 오프라인 환경에서
파이프라인 전체를 그대로 실행해볼 수 있다.

```bash
# .env에 USE_MOCK=true를 넣어뒀다면 그냥:
python -m news_alert.jobs.summarize_job   # 수집→필터→요약→저장 전부 mock
python scripts/run_web.py                 # 조회 웹페이지도 그대로 동작

# .env 대신 그 실행 1회에만 켜고 싶다면 (bash/macOS/Linux):
USE_MOCK=true python -m news_alert.jobs.summarize_job

# Windows PowerShell에서 셸 변수로 그 세션에만 켜고 싶다면:
$env:USE_MOCK = "true"
python -m news_alert.jobs.summarize_job
```

- 수집기는 `mocks/sample_data.py`에 정의된 6개 샘플 기사(추적 대상 보험사명 포함)를 반환한다.
- `LlmSummarizer`는 Claude를 호출하는 대신 **본문 앞 100자 + `...(요약 테스트)`**를
  요약으로 반환한다. `config/insurers.json` 목록과 대조해 실제로 언급된
  보험사명은 그대로 추출한다 (키워드는 `["mock", "샘플데이터"]` 고정값).
- 각 모듈은 mock 모드 진입 시 로그로 남긴다(`USE_MOCK=true — ... 샘플 데이터를 반환합니다`).
  운영 환경에서 실수로 켜져 있으면 로그에서 바로 드러난다.
- `USE_MOCK`이 없거나 `false`/`0`/`no`/`off`(대소문자 무관)이면 기존과 동일하게 실제 API/네트워크를 호출한다.
- **실전 전환**: `.env`에서 `USE_MOCK=false`로 바꾸고(또는 그 줄을 지우고)
  `ANTHROPIC_API_KEY=sk-ant-...`에 실제 키를 채우면 된다. 다음 실행부터
  실제 네이버/언론사 RSS와 Claude API를 호출한다 — 코드 수정은 필요 없다.

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
| `filters/insurer_filter.py` | `test_insurer_filter.py` | 28개 항목(보험사 22개 + 정유사 5개 + 증권사 1개) 매칭, 공백 표기 차이(`삼성생명`/`삼성 생명`) 흡수 |
| `summarizers/llm_summarizer.py` | `test_summarizers.py` | 시스템 프롬프트 전달, API 키 미설정 시 실패, 3줄 초과 요약 자르기 |
| `storage/article_store.py` | `test_article_store.py` | 요약 결과 저장, 최신순 정렬, 보험사 필터, upsert |
| `web/app.py` | `test_web_app.py` | `/`, `/api/articles`(정렬·필터), `/api/insurers`(카테고리 그룹화) |
| `pipeline.py` | `test_pipeline.py` | 4단계 순서대로 실행, 개별 기사 요약 실패 시에도 파이프라인 계속 진행 |
| `jobs/collect_job.py` | `test_collect_job.py` | 여러 수집기 결합, 중복 제거, "본 기사" 마킹 |
| `jobs/summarize_job.py` | `test_summarize_job.py` | 수집→중복제거→보험사필터→요약→저장 전체 흐름 |
| `jobs/backfill_job.py` | `test_backfill_job.py` | 요약 안 된 기사만 처리 기록 삭제, 이미 요약된 건 보존, DB 없을 때도 정상 처리 |
| `utils/config_loader.py` | `test_config_loader.py` | YAML 로딩 |
| `utils/logger.py` | `test_logger.py` | 로거 이름/레벨, 핸들러 중복 방지 |
| `utils/feed.py` | `test_feed_utils.py` | HTML 제거, 발행시각 파싱 |
| `utils/mock.py` | `test_mock_util.py` | `USE_MOCK` 값 파싱(true/1/yes/on 등, 대소문자·공백 무관) |
| `utils/env.py` | `test_env_loader.py` | `.env` 파일 자동 로드, 기존 셸 환경변수 미덮어쓰기, 파일 없을 때 무시 |
| `models/article.py` | `test_models.py` | `SummarizedArticle` 기본값(mutable default 공유 버그 가드) |

mock 모드(`USE_MOCK=true`) 동작은 `test_naver_collector.py`,
`test_press_rss_collector.py`, `test_summarizers.py`에 각각 "실제 API/네트워크를
호출하지 않고 샘플 데이터를 반환하는지" 검증하는 테스트가 추가되어 있다.

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
  `base_url`을 갱신해야 한다. 개별 보험사명 외에 `생명보험사`/`손해보험사`/`정유사`
  같은 업종 통칭 키워드도 등록해두면, 특정 회사명이 기사에 없어도 업계 전반을
  다루는 기사를 놓치지 않는다.
- `config/press_rss.csv`에 `name,url` 형식으로 언론사 RSS 피드를 등록하면
  `PressRssCollector`가 각 피드를 순회하며 기사를 가져온다.
- 두 수집기 모두 이미 처리한 기사(URL 기준)는 `data/news_alert.db`(SQLite)에
  기록해 다음 실행부터 새 기사만 반환한다.

### 언론사 RSS 추가하기

`config/press_rss.csv`에 `이름,URL` 한 줄을 추가하면 된다. 한국 언론사 RSS
주소는 사이트마다 다르고 자주 바뀌므로, 추가한 뒤에는 반드시 검증 스크립트로
확인한다 (전체 파이프라인을 안 돌려도 URL만 빠르게 검사):

```bash
python scripts/validate_press_rss.py
```

각 줄마다 `OK [N건] 이름 — URL` 또는 `FAIL 이름 — URL`로 결과가 나오고,
실패한 항목은 마지막에 목록으로 다시 정리해서 보여준다. 실패한 줄은
`config/press_rss.csv`에서 지우거나 올바른 URL로 고친다 — `PressRssCollector`는
피드 하나가 실패해도 나머지는 계속 수집하므로 당장 지우지 않아도 파이프라인
자체는 죽지 않지만, 매 실행마다 불필요한 에러 로그만 쌓인다.

1회 수집 실행:

```bash
python -m news_alert.jobs.collect_job
```

## 보험사명 필터링

`config/insurers.json`에 생명보험사 10개, 손해보험사 10개(`life`/`non_life`,
총 20개)의 정식 명칭이 카테고리별로 등록되어 있고, `정유사` 카테고리에는
보험사는 아니지만 추적하고 싶은 회사(SK에너지, GS칼텍스, S-OIL, HD현대오일뱅크)
4개를 추가로 넣어둔다. 각 카테고리에는 특정 회사명이 아니라 업종을 통칭하는
문자열도 함께 등록해둔다 — `life`에 `생명보험사`, `non_life`에 `손해보험사`,
`정유사`에 `정유사`를 추가해, 특정 회사명 없이 "생명보험사들 실적 발표"처럼
업종 전체를 다루는 기사도 해당 카테고리로 걸러지도록 한다. `증권사` 카테고리에는
`키움증권`을 등록해둔다. `InsurerFilter`는
카테고리 이름과 무관하게 등록된 모든 이름을 합쳐서 매칭하므로 새 카테고리를
추가해도 그대로 동작한다.
`InsurerFilter`(`filters/insurer_filter.py`)는
이 목록에 있는 이름이 기사 제목 또는 본문에 포함된 기사만 남긴다.

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
- 상단에 **"보험사"**(생명+손해 22개, 업종 통칭 포함), **"정유사"**(5개, 업종 통칭 포함),
  **"증권사"**(1개) 드롭다운이 각각 따로 뜬다. 하나를 선택하면 다른 쪽은 자동으로
  "전체"로 초기화된다(한 번에 하나만 필터링).
- 각 카드는 제목(원문 링크), 언론사·발행시각, 3줄 요약, 보험사/키워드 태그를 보여준다.

드롭다운 그룹은 `web/app.py`의 `FILTER_GROUPS`에서 `config/insurers.json`의
카테고리를 어떻게 묶을지 정의한다(`life`+`non_life` → "보험사", `정유사` →
"정유사", `증권사` → "증권사"). `insurers.json`에 새 카테고리를 추가하면 `FILTER_GROUPS`에도
등록해야 그 카테고리가 자기 드롭다운으로 나타난다(등록하지 않으면 어느
드롭다운에도 나타나지 않는다).

REST API만 필요하면 `GET /api/articles?insurer=삼성생명&limit=50`,
`GET /api/insurers`를 직접 호출해도 된다.

## 전체 파이프라인 실행 (수집 → 필터 → 요약 → 저장)

`jobs/summarize_job.py`는 수집(네이버 뉴스 검색 RSS + 언론사 RSS) → 중복 제거 →
보험사명 필터링(`insurers.json`) → Claude 3줄 요약 → `ArticleStore` 저장까지
한 번에 수행한다. `ANTHROPIC_API_KEY`가 `.env`에 설정되어 있어야 한다.

```bash
python -m news_alert.jobs.summarize_job
```

## 놓친 기사 백필 (`jobs/backfill_job.py`)

**중요한 한계**: RSS는 "최신 N개 기사"만 보여주는 실시간 피드이고, 날짜
범위를 지정해 과거 기사를 조회하는 기능이 없다. 그래서 "2주 전부터 지금까지"처럼
특정 기간의 기사를 정확히 다 가져오는 건 이 프로젝트의 RSS 기반 수집기로는
불가능하다 — 각 RSS 피드가 지금 이 순간 보여주는 만큼만 가져올 수 있다.

다만 API 키가 없어서(또는 다른 이유로) 요약이 실패했던 기사들은 구제할 수
있다. `summarize_job`은 수집한 기사를 일단 "이미 본 기록"(`seen_articles`)에
남기고 나서 요약을 시도하므로, 요약이 실패해도 그 기사는 "이미 본 것"으로
남아 다음 실행에서 다시 수집되지 않는다 — RSS 피드에서 그 기사가 아직
사라지지 않았어도 마찬가지다. `backfill_job`은 이렇게 **"이미 본 기록은
있지만 실제로 요약·저장되지 못한" 기사만 골라 처리 기록을 지우고 다시
수집·요약한다** (이미 요약에 성공한 기사는 건드리지 않아 불필요한 API
재호출이 없다):

```bash
python -m news_alert.jobs.backfill_job
```

로그에 `N개 기사의 처리 기록을 지웠습니다`가 뜬 뒤 평소 `summarize_job`과
같은 수집→필터→요약→저장 과정이 이어진다. 얼마나 과거까지 커버되는지는
각 RSS 피드에 지금 얼마나 남아있는지에 달려 있다 — 실행 후 웹페이지에서
가장 오래된 기사의 발행일을 확인해 원하는 기간(예: 8/24)까지 커버되는지
직접 확인해야 한다. 부족하면 이 방식(RSS)의 한계이니, 기간 지정 검색이
되는 뉴스 API/서비스를 새로 연동하는 방안을 검토해야 한다.

### 절전모드 이후에도 자동으로 따라잡기

`scripts/scheduler.py`(1시간마다 자동 실행하는 스케줄러)는 `summarize_job`이
아니라 **`backfill_job`을 매 실행마다** 돌린다. 컴퓨터가 절전모드로 잠들어
있는 동안엔 스케줄러 프로세스도 같이 멈추므로 그 사이의 예정된 실행은
당연히 못 하는데, 여기에 더해 APScheduler는 기본적으로 예정 시각을 조금이라도
놓치면("misfire") 그 실행을 아예 건너뛰고 다음 정각까지 기다린다 — 그래서
절전모드에서 깨어나도 한동안 아무 일도 안 일어나는 것처럼 보일 수 있었다.

이를 `misfire_grace_time=None`으로 바꿔, 아무리 늦었어도(예: 몇 시간 동안
절전모드였어도) 컴퓨터가 켜지는 즉시 놓친 실행을 수행하도록 했다
(`coalesce=True`라 그 사이 여러 번 놓쳤어도 한 번만 실행). 여기에 `backfill_job`을
쓰므로, 그 즉시 실행에서 그동안 놓친(수집은 됐지만 요약에 실패했던) 기사까지
자동으로 함께 채워진다 — 절전모드에서 깨어난 뒤 따로 `backfill_job`을 수동
실행할 필요가 없다.

## 배포 (자동 실행)

"자동 실행"은 사실 두 가지로 나뉜다 — ① `summarize_job`을 주기적으로 돌려
데이터를 계속 채우는 것, ② 조회 웹페이지(`web/app.py`)를 상시 띄워두는 것.
아래 옵션들은 이 둘 중 무엇을 자동화하는지가 다르니 표로 정리한다.

| 옵션 | ① summarize_job 자동 실행 | ② 웹페이지 상시 실행 |
|---|---|---|
| A. 서버(AWS/개인서버) + cron/systemd | ✅ | ✅ |
| B. GitHub Actions 스케줄 | ✅ (매시 정각) | ❌ (Actions는 웹서버 호스팅용이 아님) |
| C. 개인 Windows PC + 작업 스케줄러 | 별도 등록 필요(옵션 A의 scheduler.py 참고) | ✅ (로그온 시 자동) |

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

### 옵션 C: 개인 Windows PC + 작업 스케줄러 (컴퓨터 켤 때 웹페이지 자동 실행)

서버 없이 내 Windows PC에서 로그온할 때마다 조회 웹페이지가 자동으로 뜨게
하는 방법이다. `scripts/run_web.py`(Flask 개발 서버, `debug=True` + 리로더)는
사람이 지켜보는 로컬 개발용이라 무인 자동 실행에는 적합하지 않으므로, 대신
`scripts/serve_web_waitress.py`로 [waitress](https://github.com/Pylons/waitress)
(Windows에서도 동작하는 프로덕션 WSGI 서버 — `gunicorn`은 Windows 미지원)를
사용한다.

PowerShell에서 저장소 루트로 이동한 뒤:

```powershell
pip install -e ".[windows]"

# 작업 스케줄러에 등록 — 다음 로그온부터 자동 실행됨 (관리자 권한 보통 불필요)
powershell -ExecutionPolicy Bypass -File scripts\windows\register_web_task.ps1

# 지금 바로 실행해서 확인하고 싶다면
Start-ScheduledTask -TaskName "InsuranceNewsWebViewer"
```

- 기본적으로 콘솔 창 없이(`pythonw`) 백그라운드에서 실행된다. 문제를
  디버깅하려면 콘솔 창이 보이도록 `-PythonExe python` 옵션을 붙여 다시
  등록한다.
- 콘솔 창이 없어도 로그는 `data\web_server.log`에 남는다:
  `Get-Content data\web_server.log -Tail 20`
- 프로세스가 죽으면 1분 간격으로 최대 3회 자동 재시작하도록 설정되어 있다.
- 데이터를 계속 채우려면(mock이 아닌 실제 운영이라면) 이 작업과 별개로
  `summarize_job`도 주기 실행해야 한다 — 바로 아래 스케줄러 등록도 함께 한다.
- 제거하려면: `powershell -ExecutionPolicy Bypass -File scripts\windows\unregister_web_task.ps1`
- PowerShell 스크립트 실행이 막히는 경우("실행할 수 없습니다" 등)는 시스템
  전체 실행 정책을 바꾸는 대신, 위처럼 `-ExecutionPolicy Bypass`를 그 실행
  1회에만 적용한다.

**GUI로 직접 설정하고 싶다면** (스크립트 대신): 시작 메뉴에서 "작업 스케줄러" 실행 →
"작업 만들기" → 트리거: "로그온할 때" → 동작: "프로그램 시작", 프로그램/스크립트에
`pythonw`, 인수 추가에 `scripts\serve_web_waitress.py`의 전체 경로, 시작 위치에
저장소 루트 경로를 입력한다.

#### 1시간 요약 스케줄러도 로그온 시 자동 시작

웹페이지와 별개로, `scripts/scheduler.py`(1시간마다 `backfill_job` 반복 실행 —
놓친 기사도 함께 채운다. 아래 "절전모드 이후에도 자동으로 따라잡기" 참고)도
같은 방식으로 로그온 시 자동 시작되게 등록할 수 있다:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\register_scheduler_task.ps1

# 지금 바로 실행해서 확인하고 싶다면
Start-ScheduledTask -TaskName "InsuranceNewsScheduler"
```

- 마찬가지로 기본은 콘솔 창 없이(`pythonw`) 실행되고, 로그는
  `data\scheduler.log`에 남는다: `Get-Content data\scheduler.log -Tail 20`
- 죽으면 1분 간격 최대 3회 자동 재시작.
- 제거: `powershell -ExecutionPolicy Bypass -File scripts\windows\unregister_scheduler_task.ps1`

이 둘(`register_web_task.ps1`, `register_scheduler_task.ps1`)을 모두 등록해두면,
컴퓨터를 켜고 로그인하는 것만으로 웹페이지와 1시간 요약 자동화가 둘 다
시작된다 — 매번 PowerShell 창을 직접 열어 실행할 필요가 없다.
