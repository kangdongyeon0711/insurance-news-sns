# CLAUDE.md

이 파일은 이 저장소에서 작업하는 Claude Code(및 다른 기여자)를 위한 가이드입니다.

## 프로젝트 개요

**insurance-news-sns**는 보험사 관련 뉴스를 자동으로 수집·필터링·요약하여 지정된 채널(Slack/이메일/텔레그램 등)로
발송하는 서비스입니다. 파이프라인은 아래 4단계로 고정되어 있으며, 각 단계는 독립적으로 교체·테스트 가능해야 합니다.

```
[수집 Collect] → [필터링 Filter] → [요약 Summarize] → [발송 Notify]
```

- **수집(Collectors)**: RSS, 뉴스 API 등에서 원문 기사를 가져와 `Article` 모델로 정규화한다.
- **필터링(Filters)**: 보험사/키워드 관련성 판단, 중복 제거(이미 발송한 기사 재발송 방지)를 수행한다.
- **요약(Summarizers)**: LLM을 이용해 기사를 짧은 알림 문구로 요약한다.
- **발송(Notifiers)**: 요약된 결과를 Slack/이메일/텔레그램 등 채널로 전송한다.

각 단계는 `src/news_alert/<stage>/base.py`에 정의된 인터페이스(추상 클래스)를 구현하는 방식으로 확장한다.
새로운 소스나 채널을 추가할 때는 기존 클래스를 수정하지 말고 같은 디렉토리에 새 구현체를 추가한다.

## 폴더 구조

```
insurance-news-sns/
├── CLAUDE.md
├── README.md
├── pyproject.toml
├── .env.example
├── .github/workflows/
│   ├── test.yml              # push/PR마다 pytest 자동 실행
│   └── summarize.yml         # 1시간마다 summarize_job 자동 실행 (actions/cache로 data/ 유지)
├── deploy/systemd/            # 서버(AWS/개인서버) 배포용 systemd 유닛 예시
│   ├── news-alert-scheduler.service
│   └── news-alert-web.service
├── config/
│   ├── settings.yaml       # 전역 설정 (실행 주기, 요약 길이, 로그 레벨 등)
│   ├── sources.yaml         # 수집 대상 (RSS URL, API 엔드포인트 등)
│   └── keywords.yaml        # 필터링 키워드 (보험사명, 상품군, 제외어 등)
├── src/news_alert/
│   ├── main.py               # CLI entrypoint (파이프라인 실행)
│   ├── pipeline.py           # 4단계를 순서대로 실행하는 오케스트레이터
│   ├── collectors/           # 1. 수집 — RSS/API에서 원문 기사 가져오기
│   │   ├── base.py           #    BaseCollector 인터페이스
│   │   ├── rss_collector.py
│   │   └── api_collector.py
│   ├── filters/               # 2. 필터링 — 관련성 판단 및 중복 제거
│   │   ├── base.py           #    BaseFilter 인터페이스
│   │   ├── keyword_filter.py
│   │   └── dedup_filter.py
│   ├── summarizers/           # 3. 요약 — LLM 기반 요약 생성
│   │   ├── base.py           #    BaseSummarizer 인터페이스
│   │   └── llm_summarizer.py
│   ├── notifiers/              # 4. 발송 — 채널별 알림 전송
│   │   ├── base.py           #    BaseNotifier 인터페이스
│   │   ├── slack_notifier.py
│   │   ├── email_notifier.py
│   │   └── telegram_notifier.py
│   ├── models/
│   │   └── article.py        # Article, SummarizedArticle 등 공용 데이터 모델
│   ├── storage/
│   │   ├── sqlite_store.py   # 수집 중복 방지용 (seen_articles)
│   │   └── article_store.py  # 요약 결과 저장/조회용 (summarized_articles)
│   ├── jobs/                  # 여러 단계를 이어붙인 실행 단위
│   │   ├── collect_job.py    #    수집 -> 중복 제거
│   │   └── summarize_job.py  #    수집 -> 중복 제거 -> 보험사 필터 -> 요약 -> 저장
│   ├── web/                   # 요약된 기사 조회 웹페이지 (Flask, 파이프라인 밖의 뷰어)
│   │   ├── app.py            #    create_app(), /api/articles, /api/insurers
│   │   ├── templates/
│   │   └── static/
│   ├── mocks/
│   │   └── sample_data.py    # USE_MOCK=true일 때 수집기가 반환하는 샘플 기사
│   └── utils/
│       ├── config_loader.py  # YAML 설정 로더
│       ├── logger.py
│       ├── mock.py           # is_mock_mode() — USE_MOCK 환경변수 판정
│       └── env.py            # load_env() — .env 파일을 환경변수로 로드 (python-dotenv)
├── scripts/
│   ├── scheduler.py           # APScheduler로 summarize_job을 1시간마다 실행
│   ├── cron_run.sh            # cron으로 summarize_job을 실행하는 래퍼
│   ├── run_web.py             # 조회 웹페이지 로컬 실행 (Flask 개발 서버)
│   ├── serve_web_waitress.py  # 조회 웹페이지 무인 자동 실행용 (waitress, Windows 호환)
│   ├── validate_press_rss.py  # config/press_rss.csv의 모든 피드 URL을 한 번에 검증
│   └── windows/                # Windows 작업 스케줄러 등록/해제 스크립트
│       ├── register_web_task.ps1
│       └── unregister_web_task.ps1
├── tests/                      # 모듈별 테스트 (구성표는 README.md의 "테스트" 절 참고)
└── data/                      # 런타임 산출물 (sqlite db 등, git 추적 안 함)
```

## 데이터 흐름 (핵심 계약)

- `Article` (`models/article.py`): 수집 직후의 원본 표현. `source`, `title`, `url`, `published_at`, `content` 필수.
- `Article` 리스트가 필터를 통과하며 걸러지고, 통과한 것만 다음 단계로 전달된다.
- 요약 단계는 `Article` → `SummarizedArticle`(원본 + `summary`/`insurers`/`keywords` 필드) 변환을 수행한다.
- 발송 단계는 `SummarizedArticle` 리스트를 받아 채널별 포맷으로 변환 후 전송하고, 성공한 기사의 URL을 `storage`에 기록한다.
- 각 단계 간 데이터는 파이썬 객체(dataclass/pydantic)로만 주고받는다. 단계 사이에 직접 파일 I/O나 전역 상태를 두지 않는다.

## 조회 웹페이지 (파이프라인 외부)

`web/app.py`(Flask)는 파이프라인의 5번째 단계가 아니라, `jobs/summarize_job.py`가
`storage/article_store.py`에 저장해 둔 요약 결과를 최신순으로 보여주고 보험사별로
필터링하는 **읽기 전용 뷰어**다. 파이프라인은 여전히 4단계(수집→필터링→요약→발송)로
고정이며, 이 웹페이지는 그 산출물을 조회하는 별도 소비자일 뿐이다. `python
scripts/run_web.py`로 로컬에서 띄운다.

## 설계 원칙

- **단계 간 느슨한 결합**: `pipeline.py`는 각 단계의 구체 구현을 모른 채 인터페이스(`BaseCollector`, `BaseFilter`, `BaseSummarizer`, `BaseNotifier`)만 참조한다. 구현체는 `config/settings.yaml`에서 지정한 이름으로 동적 로딩한다.
- **중복 발송 방지는 필터 단계 책임**: 요약/발송 단계는 "새 기사인지"를 신경 쓰지 않는다. `dedup_filter.py`가 `storage/sqlite_store.py`를 참조해 이미 처리한 URL을 걸러낸다.
- **설정과 코드 분리**: 보험사명, 키워드, RSS 소스 목록은 코드에 하드코딩하지 않고 `config/*.yaml`에 둔다.
- **비밀값은 `.env`로 관리**: Slack Webhook, 이메일 SMTP 자격, LLM API 키 등은 `.env`에서 읽는다. `.env.example`을 최신 상태로 유지한다. 각 실행 진입점(`jobs/*.py`, `web/app.py`, `main.py`)은 모듈 상단에서 `utils/env.py`의 `load_env()`를 호출해 `.env`를 환경변수로 자동 로드한다 — 셸에 직접 `export`/`$env:`로 설정할 필요 없이 `.env` 파일에 값만 적어두면 된다(이미 셸에 설정된 값은 덮어쓰지 않는다).
- **각 단계는 실패해도 파이프라인 전체를 죽이지 않는다**: 개별 기사 처리 실패는 로깅 후 스킵, 파이프라인은 계속 진행한다.
- **외부 API/네트워크를 호출하는 모듈은 mock 모드를 지원한다**: `utils/mock.py`의 `is_mock_mode()`(`USE_MOCK` 환경변수)로 판단하며, mock일 때는 `mocks/sample_data.py`의 샘플 데이터를 반환하고 실제 호출은 절대 하지 않는다. 새 Collector/Summarizer/Notifier를 추가할 때도 이 패턴을 따른다.

## 실행 방법

```bash
# 의존성 설치 (uv 또는 pip)
pip install -e ".[dev]"

# 전체 파이프라인 1회 실행
python -m news_alert.main

# 또는 스케줄러(cron 등)에서
python scripts/run_pipeline.py
```

## 테스트

```bash
pytest tests/
```

- 각 단계(수집/필터/요약/발송)는 외부 의존성(네트워크, LLM API, Slack 등)을 mock으로 대체해 단위 테스트한다.
- 새 Collector/Filter/Summarizer/Notifier를 추가하면 대응하는 테스트 파일에 최소 1개 이상의 테스트를 추가한다.

## 코딩 컨벤션

- Python 3.11+, 타입 힌트 필수.
- 각 단계의 구현체는 반드시 해당 디렉토리의 `base.py` 인터페이스를 상속한다.
- 새 뉴스 소스/채널 추가 시 기존 파일을 수정하지 말고 새 파일로 추가 후 `config/settings.yaml`에 등록한다.
- 로깅은 `print` 대신 `utils/logger.py`의 로거를 사용한다.
