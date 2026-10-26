# 매크로·포트폴리오 분석 에이전트 (macro-agent)

자산운용 직무용 개인 Claude Code 에이전트.

- **파이프라인 A (매크로)**: 16개 항목(환율, 유가, 한미 금리·국채·회사채, 한미 대체투자 8종)의 `현황 / 단기(3~6개월) / 장기(1~3년, Base·Bull·Bear + 확률)` 주간 브리프
- **파이프라인 B (포트폴리오)**: 금융회사(보험사·증권사·자산운용사·은행) 공시 PDF·엑셀 → 업종별 익스포저 추출 → 매크로 팩터 충격의 시나리오별 영향 계산 → 리밸런싱 방향 제안

> 결과물은 의사결정 보조 자료이며 투자 권유가 아닙니다.

---

## 1. 설치

Python 3.11 이상.

**macOS / Linux**
```bash
cd macro-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -c "import pdfplumber, fitz, pandas, jsonschema; print('ok')"
```

**Windows (PowerShell)**
```powershell
cd macro-agent
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1      # 실행 정책 오류 시: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt
python -c "import pdfplumber, fitz, pandas, jsonschema; print('ok')"
```

Claude Code는 **이 폴더(`macro-agent/`)에서** 실행합니다: `cd macro-agent && claude`. 그래야 `.claude/agents`, `.claude/skills`, `CLAUDE.md`가 적용됩니다.

## 2. API 키

`.env.example`을 `.env`로 복사한 뒤 값을 채웁니다 (`.env`는 git에 올라가지 않음).

```bash
cp .env.example .env          # Windows: copy .env.example .env
```

| 변수 | 발급처 | 비고 |
|---|---|---|
| `ECOS_API_KEY` | 한국은행 ECOS Open API — https://ecos.bok.or.kr/api/ → 인증키 신청 | 기준금리, 국고채·회사채·CD, 원/달러, CPI |
| `FRED_API_KEY` | FRED — https://fred.stlouisfed.org/docs/api/api_key.html (계정 생성 후 API Keys) | FFR, UST, BEI, IG/HY OAS, 유가, 달러지수 |
| `EIA_API_KEY` | EIA Open Data — https://www.eia.gov/opendata/ (Register) | 선택. 없으면 원유 재고 수집만 건너뜀 |
| `DART_API_KEY` | OpenDART — https://opendart.fss.or.kr/ → 인증키 신청 | 보험사 정기공시 목록·주요 재무계정 (PDF 다운로드는 안 함) |

키를 넣은 뒤 **코드 검증과 수집**을 한 번 실행합니다:
```bash
python scripts/fetch_ecos.py --verify   # StatisticItemList로 항목코드·이름·주기 확인 → series.yaml verified 갱신
python scripts/fetch_fred.py --verify
python scripts/fetch_all.py --print     # 전체 수집 + data/latest_snapshot.json + 주요 값 출력
```

### API 키가 없을 때: 수기 입력
ECOS 홈페이지 등에서 직접 확인한 값을 `data/manual/*.yaml`에 넣으면 스냅샷에 반영됩니다(예: `data/manual/ecos_homepage_20261025.yaml`, 원문은 같은 이름의 `_raw.txt`).
```yaml
points:
  - {series_id: ktb_3y, value: 3.803, as_of: 2026-10-23, period_label: "10.23 마감"}
  - series_id: kospi            # series.yaml에 없는 지표는 meta 필요
    value: 5550.30
    as_of: 2026-10-23
    meta: {name: KOSPI, unit: pt, cycle: D, chg_type: pct, topic_id: null}
```
ECOS **100대 통계지표 엑셀**은 `python scripts/import_ecos100.py <파일.xlsx> --date YYYY-MM-DD`로 바로 변환됩니다(원본 사본 보관, 주요 60개 지표에 series_id·topic 매핑, 나머지는 `ecos100_번호`로 이름 보존).
`python scripts/fetch_all.py --no-fetch --print`로 스냅샷을 다시 만듭니다. 수기 값은 `value_flag: 수기`로 표시되고, 나중에 API로 같은 날짜가 수집되면 API 값이 우선합니다(괴리 0.5% 초과 시 경고). 단일 시점 값이라 1주·1개월 변화는 API 수집 전까지 비어 있습니다.

## 3. 주간 사용 루틴

1. 증권사 리서치센터에서 경제/외환, 채권, 크레딧, 대체자산 리포트 5~10개를 직접 다운로드해 파일명 규칙대로 `inbox/reports/`에 저장
2. Claude Code에서 `/macro-brief` → `reports/{YYYY-MM-DD}_macro_brief.md`
3. 공시 분석이 필요할 때 공시 PDF를 `inbox/filings/`에 넣고 `/portfolio-impact 현대해상` → `reports/{YYYY-MM-DD}_현대해상_portfolio_impact.md`

워드 요약본(16개 항목 한 장 요약 + 항목별 정리): `python scripts/export_summary_prep.py YYYY-MM-DD && node scripts/export_summary_docx.js YYYY-MM-DD` → `reports/{날짜}_매크로16개항목_요약.docx` (node `docx` 패키지 필요: `npm install -g docx`).

`/ingest`만 따로 실행해 리포트 → view_card 변환만 할 수도 있습니다.

운용수익률 제고 전략(배분 최적화): `/portfolio-impact` 이후
```bash
python scripts/optimize_allocation.py --portfolio knowledge/portfolios/현대해상/2026Q2.json --shocks reports/tmp/{날짜}_factor_shocks.json --date {날짜}
python scripts/opt_sensitivity.py --portfolio ... --shocks ... --date {날짜}      # 가정 민감도
python scripts/render_yield_strategy.py --company 현대해상 --date {날짜}            # 골격(표) 생성 → 서술 TODO 채움
```
재무제표 요약(손익·보험손익 분해·재무상태표·영업지표): `python scripts/extract_ir_financials.py --xlsx processed/filings/{회사}_{기간}_IR데이터.xlsx --company {회사} --period 1H26 --avg-assets {평균 운용자산}` → `knowledge/portfolios/{회사}/financials_{기간}.json` (현대해상 IR Factsheet 양식 기준, 다른 양식은 라벨 조정 필요).
가정은 `config/yield_assumptions.yaml`(신규 자금 기대수익·기대손실·K-ICS 계수 범위·연간 조정 한도·전략별 제약). 3년 경로는 `class_bounds_pp`를 3배로 한 사본을 `--assumptions`로 넘겨 계산합니다. 투자손익 분해는 `knowledge/portfolios/{회사}/income_{기간}.json`.

### 파일명 규칙
| 종류 | 형식 | 예 |
|---|---|---|
| 증권사 리포트 | `YYYYMMDD_하우스_리포트명.pdf` | `20261023_미래_MacroWeekAhead.pdf`, `20261022_신한_크레딧Weekly.pdf` |
| 보험사 공시 | `회사_YYYYQn_자료종류.pdf` 또는 `회사_YYYY_자료종류.pdf` | `현대해상_2026Q2_경영실적.pdf`, `현대해상_2025_정기경영공시.pdf` |

하우스 약칭(미래, 신한, 삼성, KB, NH, 한투, 키움, 하나, 메리츠, 대신 …)은 정식 명칭으로 바뀝니다 (`scripts/ingest_inbox.py`의 `HOUSES`).
규칙에 안 맞는 파일은 첫 페이지에서 날짜·하우스(회사·기간)를 추정하고 manifest에 `estimated: true`로 남깁니다.

### 지원 업종 (`config/entity_profiles.yaml`)
| 업종 | 회사명 예 | 추출·계산 포인트 | 리포트 추가 섹션 |
|---|---|---|---|
| 보험사 | ○○화재, ○○해상, ○○생명 | 운용자산, 부채 듀레이션, K-ICS, 공시 금리 민감도 대조 | 자본비율, 캘리브레이션, ALM |
| 증권사 | ○○증권, ○○투자증권 | 운용 유가증권(짧은 듀레이션), PF 대출 + **채무보증(우발채무)**, NCR | 자본비율, 우발채무, 조달·유동성 |
| 자산운용사 | ○○자산운용 | **AUM 유형별·보수율 → 연간 보수수익 영향**, 고유재산 | AUM·보수수익 영향 |
| 은행 | ○○은행 | 유가증권·대출, BIS | 자본비율 |
업종은 회사명으로 자동 추정하고(manifest `entity_type`), portfolio-analyst가 문서로 확인한다. 새 업종은 entity_profiles.yaml에 프로필을 추가한다.

공시 파일명: `회사_YYYYQn_자료종류.pdf|xlsx` (예: `현대해상_2026Q2_IR경영실적.pdf`, `현대해상_2026Q2_IR데이터.xlsx`). IR 엑셀 데이터 시트를 함께 넣으면 수치 정밀도가 올라갑니다.

### 보험사 자료 팁
- **IR 경영실적 자료**: 자산군별 운용자산 규모·비중·운용수익률이 분기마다 나옴 → 기본 익스포저
- **정기경영공시**: 듀레이션, 신용등급 분포, 대체투자 상세, 금리위험(ALM)·부채 듀레이션, K-ICS → 함께 넣으면 추정값이 크게 줄어듭니다
- **사업·분기·반기보고서**(DART): 유가증권 계정 분류, 대출채권 상세, 외화자산
- 여러 해(가능하면 10년) 자료를 넣으면 비중 추이와 운용 전략 변화를 분석합니다. 2023년 IFRS17·IFRS9 도입 전후는 계정 분류가 달라 비교 시 경고가 붙습니다.

## 4. 자동 실행 (선택)

비대화형 실행: `claude -p "/macro-brief"` (권한 확인 없이 돌리려면 `.claude/settings.json`에 필요한 도구를 허용해 두거나 `--permission-mode`를 지정).

**macOS / Linux (cron)** — 매주 월요일 07:30
```cron
30 7 * * 1 cd /path/to/macro-agent && . .venv/bin/activate && claude -p "/macro-brief" >> data/macro_brief.log 2>&1
```

**Windows (작업 스케줄러)**
```powershell
$action  = New-ScheduledTaskAction -Execute "powershell.exe" -Argument '-NoProfile -Command "cd C:\path\to\macro-agent; .\.venv\Scripts\Activate.ps1; claude -p ''/macro-brief'' *>> data\macro_brief.log"'
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 7:30am
Register-ScheduledTask -TaskName "MacroBrief" -Action $action -Trigger $trigger
```

리포트 수집은 자동화하지 않습니다(원칙 2). 자동 실행은 API 수집 + 웹 검색 + 이미 inbox에 있는 파일 처리까지만 합니다.

## 5. 구성

```
config/      series.yaml, factors.yaml, assumptions.yaml(가정), constraints.yaml(제약, 사용자 편집)
schemas/     view_card / macro_topic / exposures / factor_shocks JSON 스키마
scripts/     fetch_{ecos,fred,eia,dart,all}.py, ingest_inbox.py, validate_json.py, validate_exposures.py,
             build_shocks.py, calc_impact.py, render_brief.py, render_portfolio.py, check_report.py,
             snapshot_view.py, recent_cards.py, common.py
.claude/     agents/ (report-reader, fx-commodity, kr-/us-fixed-income, kr-/us-alternatives, portfolio-analyst, fact-checker)
             skills/ (ingest, macro-brief, portfolio-impact, impact-mapping + sensitivity_matrix.md)
inbox/ → processed/ → knowledge/ → reports/
tests/       pytest (calc_impact 손계산, ingest, 스냅샷, 스키마 검증, 리포트 대조) + fixtures(가상 데이터)
```

테스트: `python -m pytest tests -q`

## 6. 설계 결정

명세에 없어 구축 시 정한 사항입니다.

1. **위치**: 기존 `insurance-news-sns` 저장소의 루트에 이미 CLAUDE.md·README·scripts·config가 있어, 덮어쓰지 않도록 `macro-agent/` 하위 폴더에 독립 프로젝트로 만들었습니다. 같은 이유로 `git init`은 하지 않고 기존 저장소에 Phase별로 커밋했습니다. 상위 CLAUDE.md는 이 프로젝트에 적용되지 않는다고 macro-agent/CLAUDE.md에 명시했습니다.
2. **변화량 단위**: snapshot의 `chg_*`는 금리·스프레드(`chg_type: diff`)는 **bp**, 레벨 지표(환율·유가·지수)는 **%** 입니다 (`chg_unit` 필드). 파생 스프레드는 `last_value`(%p)와 `last_value_bp`를 함께 둡니다.
3. **stale 기준**: 원칙 7의 7일은 일별 지표에 적용. 주별 10일, 월별(기준금리 722Y001 월별, CPI) 45일, 분기 120일 — 월별 지표는 발표 주기상 7일 기준이 항상 경고가 되기 때문입니다.
4. **달러 인덱스**: ICE DXY는 FRED에 없어 `DTWEXBGS`(Nominal Broad Dollar Index)를 대용으로 씁니다. factor 이름은 명세대로 `dxy_pct`.
5. **원/달러 교차검증**: ECOS 매매기준율과 FRED `DEXKOUS`의 같은 날짜 값 괴리가 1%를 넘으면 경고.
6. **DART**: 공시 목록과 주요 계정(자산총계 등)만 조회합니다. 공시 PDF 자동 다운로드는 원칙 2 취지에 따라 하지 않습니다.
7. **ingest**: 중복은 sha256으로 판정하고 중복 파일은 inbox에 그대로 둡니다(삭제 금지). 페이지당 평균 200자 미만이면 pymupdf로 재시도하고, 품질 플래그 `good/low/empty`(empty = 스캔본 의심)를 남깁니다. 표 추출은 리포트·공시 모두 수행합니다. 파일명이 규칙에 맞지 않으면 정규화된 이름(`YYYYMMDD_하우스_원래이름`)으로 저장해 card_id = 파일명이 되게 했습니다.
8. **macro_topic 스키마 보강**: indicator에 `value_flag`(API/웹확인/추정/미확인)·`source`·`stale`, 시나리오에 `shock_rationale`, 최상위에 `short_term_shock_rationale`을 추가했습니다(정성→숫자 번역 근거 한 줄). `validate_json.py`는 확률 합, Base/Bull/Bear, factor 이름, snapshot 수치·기준일 일치, "하우스 뷰 부족" 기록을 검사합니다.
9. **충격 결합(build_shocks.py)**: 팩터마다 factors.yaml의 주인 topic 값을 쓰고(없으면 제시한 topic 평균), 장기 시나리오는 같은 이름끼리 결합(topic 간 공동 단조 가정), 확률은 topic 평균을 합 1로 정규화합니다. "기대충격" 시나리오는 팩터별로 주인 topic의 확률로 가중한 기대 충격(을 넣었을 때의 영향)이고, calc_impact의 "확률가중" 열은 Base/Bull/Bear 영향 자체의 확률가중 평균(`prob_weighted`)입니다. 비선형·가정 차이로 두 값은 조금 다릅니다.
10. **영향 계산 기준**: 경제적 가치(공정가치) 기준. AC 분류 채권, 원가모형 부동산의 회계상 손익과 다를 수 있음을 리포트에 명시합니다. 컨벡시티는 기본 제외(`convexity_mode: none`), `approx`로 C≈D² 근사 가능. 시나리오에 없는 팩터는 0으로 보고 `missing_factors`에 기록합니다.
11. **자산군 규칙은 설정 파일**: `assumptions.yaml`의 `class_rules`가 자산군 → 계산 방법을 매핑합니다. 원화채는 3·10·30년, 해외채는 UST 2·10·30년 선형 보간. 비미국 해외채는 UST, 비달러 통화는 원/달러로 근사(추정 표시). 회사채 등급 미공시 시 AA, 해외채는 IG로 가정(추정 표시). 수익증권(구성 미공시)은 30%만 주식 노출로 가정.
12. **ALM**: 순자산 영향 = −(D_A·A − D_L·L)·Δy, Δy = `alm_rate_factor`(기본 ktb_10y_bp). D_A는 채권·대출(bond 규칙)·인프라 등 금리민감 자산만. `liabilities.pv_krw_bn`(금리민감 부채 규모)이 있어야 계산합니다 — 스키마에 이 필드를 추가했습니다.
13. **리포트 골격 렌더러**: 표와 수치는 `render_brief.py`/`render_portfolio.py`가 JSON에서 결정적으로 만들고, 서술 섹션만 LLM이 `<!-- TODO -->`를 채웁니다. `check_report.py`가 표의 수치를 원천과 기계적으로 대조해 fact-checker를 보조합니다. 남은 TODO는 오류로 잡습니다.
14. **헬퍼 스크립트 추가**: 서브에이전트가 snapshot·카드를 안정적으로 읽도록 `snapshot_view.py`, `recent_cards.py`를 추가했습니다.
15. **금액 단위**: 익스포저 입력은 십억원(`mv_krw_bn`), 영향 출력은 억원(`impact_100m`)과 운용자산 대비 bp.
16. **K-ICS**: 위험계수는 감독기준 확인 전까지 `assumptions.kics.risk_factors: null` — 정성 서술만 합니다.
17. **수기 입력값**: API 차단·키 미입력 시 사용자가 확인한 공식 홈페이지 값을 `data/manual/`에 원문과 함께 보관하고 스냅샷에 `source_type: manual`로 합칩니다. CSV(API 원본)는 덮어쓰지 않고 스냅샷 생성 시 메모리에서만 병합합니다. 같은 날짜는 API 우선. 원/달러 수기값(10.24 05:00)은 시각 기준이 매매기준율과 다를 수 있어 메모로 남겼습니다.
18. **해외 인프라 할인율 팩터 분리**: 명세의 `infra_discount_rate_bp`는 국내·해외 공통이었는데, build_shocks는 팩터당 주인 topic 1개 값만 남겨 해외 인프라 자산에도 국내 할인율이 적용되는 문제가 있었습니다. 그래서 `us_infra_discount_rate_bp`(주인 us_alt_infra)를 추가하고, calc_impact가 region ≠ KR 인프라 자산에 이 값을 쓰도록 했습니다(없으면 국내 값으로 근사하고 추정 표시).
19. **대표 지표·오래된 데이터 판정 일원화**: 브리프 한 장 요약과 워드 요약본은 `render_brief.PREF`의 항목별 대표 지표 순서를 공유합니다. 웹확인 값은 에이전트가 적은 stale 필드 대신 기준일로 판정하고(일자 7일, 월 45일), 정책금리는 결정일 기준이라 제외합니다.
20. **업종 범용화**: 보험사 전용이던 파이프라인 B를 entity_type(insurer/securities/asset_manager/bank/other)으로 일반화했습니다. 업종별 기본 듀레이션(`assumptions.duration_by_entity`), 제약(`constraints.entity_overrides`), 우발채무(`contingent`, 손익 포함), AUM 보수 영향(`aum`, 대차대조표 합계와 분리), 공시 금리 민감도 캘리브레이션(`rate_sensitivity_disclosed`)을 추가했습니다. 기존 보험사 익스포저는 entity_type이 없어도 insurer로 처리됩니다.
21. **배분 최적화(LP)**: `optimize_allocation.py`는 자산군별 기대 총수익(시장 base + 스프레드 − 기대손실 − 헤지비용 + 확률가중 평가변화 ÷ 2년)을 최대화합니다. 제약은 K-ICS 하한(위험계수 상단 × 분산효과, 요구자본은 공시 비율로 역산), 공시 듀레이션 갭, Bear 추가 손실, 대체 상한, 현금 하한, 자산군별 연간 조정 한도입니다. 한도가 없으면 해가 한 자산군에 몰리므로(코너 해), 만기 재투자·딜 파이프라인 속도를 한도로 둡니다. K-ICS 계수 중 주식·부동산만 웹확인, 나머지는 가정 범위입니다.

## 7. 미검증 시리즈 코드

구축 환경에서 ecos.bok.or.kr, api.stlouisfed.org, api.eia.gov, opendart.fss.or.kr 접속이 네트워크 정책으로 차단되어 메타데이터 조회를 하지 못했습니다. 웹 검색으로도 항목코드를 확정할 수 없어 **모든 코드가 `verified: false`** 입니다. 키 입력 후 `--verify`를 실행하면 자동 갱신됩니다.

| series_id | 소스 | 통계표 / 코드 | 항목코드 | 주기 | 확인할 점 |
|---|---|---|---|---|---|
| kr_base_rate | ECOS | 722Y001 | 0101000 | M | 일별(D) 제공 여부 |
| kr_call_1d | ECOS | 817Y002 | 010101000 | D | |
| kr_cd_91d | ECOS | 817Y002 | 010502000 | D | |
| ktb_3y / ktb_10y / ktb_30y | ECOS | 817Y002 | 010200000 / 010210000 / 010230000 | D | |
| kr_corp_aa_3y / kr_corp_bbb_3y | ECOS | 817Y002 | 010300000 / 010320000 | D | |
| krw_usd | ECOS | 731Y001 | 0000001 | D | 매매기준율 항목 |
| kr_cpi | ECOS | 901Y009 | 0 | M | 총지수 |
| us_ffr_upper/lower, us_eff_ffr | FRED | DFEDTARU, DFEDTARL, DFF | | D | |
| ust_2y/10y/30y, ust_10y_2y_fred, us_bei_10y | FRED | DGS2, DGS10, DGS30, T10Y2Y, T10YIE | | D | |
| us_ig_oas, us_hy_oas | FRED | BAMLC0A0CM, BAMLH0A0HYM2 | | D | |
| wti, brent | FRED | DCOILWTICO, DCOILBRENTEU | | D | |
| usd_broad_index, krw_usd_fred | FRED | DTWEXBGS, DEXKOUS | | D | |
| us_crude_stocks | EIA | PET.WCESTUS1.W | | W | v2 seriesid 경로 |

`--verify`가 불일치를 보고하면 같은 이름의 후보 코드를 함께 출력하니 그 코드로 `config/series.yaml`을 고친 뒤 다시 실행하세요.

## 8. 한계와 면책

- 현황 수치는 API 수집값이 있을 때만 채워집니다. 키가 없거나 수집에 실패하면 "미확인"으로 표시됩니다.
- 대체투자(특히 한국)는 공개 시계열이 거의 없어 웹 검색과 하우스 뷰에 크게 의존하며 확신도가 낮습니다.
- 팩터 충격은 정성 전망을 숫자로 옮긴 것이라 정밀하지 않고, 영향 계산은 선형(1·2차) 근사입니다. 상관·2차 효과, IFRS17 부채 할인율(유동성 프리미엄·LTFR), CSM 흡수, K-ICS 요구자본은 계산하지 않습니다.
- 공시에서 확인하지 못한 듀레이션·헤지비율·등급은 가정값을 쓰며 결과에 `*`/"추정"으로 표시됩니다.
- 증권사 리포트는 개인 분석용으로만 요약하며 원문의 저작권은 각 발행사에 있습니다.
- **본 결과물은 의사결정 보조 자료이며 투자 권유가 아닙니다.**
