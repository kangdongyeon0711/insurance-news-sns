# CLAUDE.md — 매크로·포트폴리오 분석 에이전트

자산운용 직무용 개인 에이전트. (A) 16개 매크로 항목의 현황/단기/장기 시나리오 주간 브리프,
(B) 금융회사(보험사·증권사·자산운용사·은행) 공시 PDF·엑셀 → 업종별 익스포저 → 매크로 충격 영향 계산 → 리밸런싱 방향 제안. 업종 관점은 `config/entity_profiles.yaml`.
상위 폴더의 CLAUDE.md(insurance-news-sns 뉴스 서비스)는 이 프로젝트에 적용되지 않는다. 이 폴더에서 `claude`를 실행한다.

## 반드시 지킬 원칙
1. **숫자는 코드와 API에서, 해석은 LLM이 맡는다.** 현황 수치는 `data/latest_snapshot.json`(API 수집값)에서만 인용하고 각 수치에 기준일(as_of)을 붙인다. 리포트에 나온 과거 수치를 현재값처럼 쓰지 않는다.
2. **증권사 리서치 사이트와 보험사 IR 사이트를 크롤링하지 않는다**(WebFetch 포함). 리포트·공시 PDF는 사용자가 직접 `inbox/`에 넣는다. 에이전트는 `inbox/`만 처리한다.
3. 리포트 내용은 개인 분석용으로만 요약한다. 원문을 길게 옮겨 적지 않고 페이지 번호(`p.N`)로 근거를 표시한다.
4. **사실 / 하우스 뷰 / 에이전트 자체 판단**을 항상 구분해 표기한다: `[사실]`, `[하우스]`, `[판단]`.
5. 장기 전망은 단일 포인트가 아니라 **Base / Bull / Bear 시나리오 + 확률**(합 = 1)로 낸다.
6. 확인하지 못한 것은 "미확인", 추정한 값은 "추정"으로 표시한다. 빈칸을 그럴듯한 숫자로 채우지 않는다.
7. 데이터가 7일 이상 오래되었으면 경고를 단다 (snapshot의 `stale`; 월별 지표는 45일 기준).
8. 모든 사용자 대상 출력은 한국어. 지표명은 영문 약어 병기 가능.
9. 결과물은 의사결정 보조 자료이며 투자 권유가 아님을 리포트 하단에 명시한다.

추가 규칙
- factor_shocks는 `config/factors.yaml`의 이름만 쓴다. 영향 금액은 `scripts/calc_impact.py` 출력에서만 인용한다.
- 파일을 지우거나 덮어쓰기 전에는 사용자에게 확인한다. inbox 파일은 이동만 하고 삭제하지 않는다.
- 모든 서브에이전트(`.claude/agents/`)는 이 원칙을 따른다.

## 폴더 역할
| 경로 | 역할 |
|---|---|
| `config/` | series(수집 시계열), factors(팩터 표준명), assumptions(계산 가정 — 전부 "가정"), constraints(리밸런싱 제약, 사용자 편집) |
| `schemas/` | view_card, macro_topic, exposures, factor_shocks JSON 스키마 |
| `scripts/` | 수집(fetch_*), ingest_inbox, 검증(validate_*, check_report), 계산(build_shocks, calc_impact), 렌더(render_*) |
| `inbox/reports`, `inbox/filings` | 사용자가 넣는 증권사 리포트 / 보험사 공시 PDF |
| `processed/` | 처리된 PDF + 추출 텍스트(`=== p.N ===`) + 표(`_tables.json`) + `manifest.json` |
| `data/` | API 원본(raw/), 시계열 CSV(series/), `latest_snapshot.json` |
| `knowledge/view_cards/` | 리포트 1개 = 카드 1개 |
| `knowledge/macro_topics/{날짜}/` | topic별 주간 분석 16개 |
| `knowledge/portfolios/{회사}/{기간}.json` | 익스포저 |
| `reports/` | 최종 Markdown 산출물 (`reports/tmp/`는 계산 중간물) |

## 명령
- `/ingest` — inbox PDF 처리 → report-reader로 view_card 생성
- `/macro-brief` — 수집 → ingest → 매크로 서브에이전트 5개 병렬 → 검증 → 브리프 → fact-checker
- `/portfolio-impact [회사]` — 업종 확인 → 공시 처리 → 익스포저 추출 → 공시 민감도 캘리브레이션 → 충격 결합 → calc_impact → 제안 → fact-checker

자주 쓰는 스크립트
```bash
python scripts/fetch_all.py --print                      # 수집 + 스냅샷
python scripts/snapshot_view.py --topics kr_govt_bond     # topic별 현황 수치
python scripts/recent_cards.py --topics us_rate --days 30 # 최근 하우스 뷰
python scripts/validate_json.py knowledge/macro_topics/2026-10-25/ --expect-all-topics
python scripts/build_shocks.py && python scripts/calc_impact.py --portfolio ... --shocks ...
python -m pytest tests -q
```

## 출력 스타일
- 한국어, 표 우선. 모든 수치에 단위와 기준일. 금액은 억원(계산 입력은 십억원), 금리 변화는 bp.
- 문장 앞에 `[사실]`/`[하우스]`(card_id 병기)/`[판단]` 태그.
- 추정·가정값은 "추정" 또는 `*` 표시. 확인 못 한 값은 "미확인".
- 리포트 하단에 면책 문구 (render_brief/render_portfolio가 자동 삽입).
