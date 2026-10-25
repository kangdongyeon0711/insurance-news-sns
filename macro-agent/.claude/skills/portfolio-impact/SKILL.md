---
name: portfolio-impact
description: 금융회사(보험사·증권사·자산운용사·은행) 공시 PDF·엑셀에서 업종에 맞는 익스포저를 추출하고, 최신 매크로 전망(factor_shocks)이 포트폴리오에 미칠 영향을 시나리오별로 계산해 리밸런싱 방향을 제안하는 리포트를 만든다. 사용자가 /portfolio-impact [회사명]을 입력할 때 사용.
argument-hint: "[회사명] (예: 현대해상)"
---

# /portfolio-impact [회사]

CLAUDE.md의 원칙 9개를 따른다. 기준일 `AS_OF` = 오늘. 회사 = 인자(없으면 manifest의 filing 회사 목록을 보여주고 묻는다).

## 절차
0. **업종 확인**: manifest의 `entity_type`(회사명으로 추정)과 `config/entity_profiles.yaml`의 프로필을 확인한다. 업종에 따라 추출 대상·리포트 섹션이 달라진다(보험사: ALM·K-ICS / 증권사: PF 우발채무·NCR·조달 / 자산운용사: AUM·보수수익).
1. **공시 처리**: `/ingest` 절차로 inbox/filings를 처리한다(PDF·엑셀 xlsx 모두 지원).
2. **익스포저 추출**: **portfolio-analyst** 서브에이전트에 회사명을 전달해 모든 기간의 `knowledge/portfolios/{회사}/{기간}.json`을 만들게 한다 (이미 있는 기간은 새 공시가 추가된 경우에만 갱신, 덮어쓰기 전 사용자 확인).
   검증: `python scripts/validate_json.py knowledge/portfolios/{회사}/` + `python scripts/validate_exposures.py knowledge/portfolios/{회사}/ --trend`
3. **매크로 전망 확인**: `ls knowledge/macro_topics/` 에서 가장 최근 날짜 폴더. AS_OF보다 7일 넘게 오래되었거나 없으면 **사용자에게 `/macro-brief`를 먼저 실행할지 묻는다** (AskUserQuestion). 사용자가 거절하면 오래된 전망임을 리포트에 경고하고 진행.
4. **시나리오 세트 생성**: `python scripts/build_shocks.py --date {macro_date}` → `reports/tmp/{macro_date}_factor_shocks.json`
   (단기, 장기-Base, 장기-Bull, 장기-Bear, 기대충격(확률가중 기대 충격). calc_impact는 장기 3개 시나리오 영향의 확률가중 기대값도 따로 낸다. 결합 규칙은 build_shocks.py docstring.)
4-1. **캘리브레이션**: 익스포저에 `rate_sensitivity_disclosed`가 있으면 calc_impact 출력의 `calibration`(엔진 vs 공시 금리 민감도)을 확인한다. 엔진/공시 비율이 0.8~1.2를 벗어나면 portfolio-analyst에 듀레이션 가정·분류 재점검을 요청하고, 조정 내역을 notes에 남긴 뒤 다시 계산한다.
5. **영향 계산**: `python scripts/calc_impact.py --portfolio knowledge/portfolios/{회사}/{최신기간}.json --shocks reports/tmp/{macro_date}_factor_shocks.json --out reports/tmp/{AS_OF}_{회사}_impact`
   → `_impact.json`, `_impact.csv`, 콘솔 표. 숫자는 이 출력에서만 인용한다.
6. **정성 보완**: `.claude/skills/impact-mapping/SKILL.md`와 `sensitivity_matrix.md`를 읽고, 계산이 단순화한 경로(PF 충당금, 대체투자 평가 지연, 부채 할인율, K-ICS)를 서술로 보완한다.
7. **리밸런싱 제안**: `config/constraints.yaml`을 읽어 자산군별 방향(확대/축소/유지)과 폭(%p 범위)을 제안하고, 제약 충족 여부를 점검한다: `python scripts/calc_impact.py ... --check-constraints` 출력 활용.
8. **리포트 작성**: `python scripts/render_portfolio.py --impact reports/tmp/{AS_OF}_{회사}_impact.json --portfolio-dir knowledge/portfolios/{회사}/` 로 골격(`reports/{AS_OF}_{회사}_portfolio_impact.md`)을 만들고, `<!-- TODO -->` 섹션(운용 전략 해석, 영향 경로 설명, 리밸런싱 제안 근거·리스크)을 직접 채운다.
9. **팩트체크**: fact-checker에 리포트 경로 전달 → 불일치 수정 → `python scripts/check_report.py reports/{AS_OF}_{회사}_portfolio_impact.md --kind portfolio --impact reports/tmp/{AS_OF}_{회사}_impact.json` 재확인.
10. 사용자에게 요약(시나리오별 손익 합계, 취약 자산군 3개, 핵심 제안 3개)과 경로 보고.

## 리포트 구성 (업종별 섹션은 render_portfolio.py가 자동 추가)
- 공통 외 보험사: 자본비율(K-ICS)·공시 민감도 대조·ALM / 증권사: 우발채무('우발:' 행)·자본비율(NCR)·조달·유동성 / 자산운용사: AUM·보수수익 영향·자금흐름(정성)
- 요약: 시나리오별 운용자산 평가손익 합계, 가장 취약한 자산군 3개, 핵심 제안 3개
- 포트폴리오 현황: 자산군별 비중 표, 10년(또는 가용 기간) 비중 추이, 운용 전략 해석
- 매크로 → 포트폴리오 영향: 시나리오 × 자산군 영향 표 (억원, 운용자산 대비 bp), 영향 경로 설명
- ALM 관점: 부채 듀레이션이 있으면 금리 충격에 대한 순자산 영향 (자산·부채 듀레이션 갭)
- 리밸런싱 제안: 자산군별 방향과 폭(%p 범위), 근거, 실행 시 리스크, 제약 충족 여부
- 한계와 가정: 추정값 목록, 데이터 공백, 면책 문구
