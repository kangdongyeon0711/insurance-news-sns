---
name: macro-brief
description: 16개 매크로 항목(환율·유가·한미 금리/국채/회사채·한미 대체투자)의 현황/단기/장기 시나리오를 정리한 주간 매크로 브리프를 만든다. 사용자가 /macro-brief를 입력하거나 주간 매크로 브리프를 요청할 때 사용.
---

# /macro-brief

CLAUDE.md의 원칙 9개를 따른다. 기준일 `AS_OF` = 오늘(YYYY-MM-DD).

## 절차
1. **데이터 수집**: `python scripts/fetch_all.py --print`
   - `fetch_status`에 `no_key`/`failed`가 있으면 기존 snapshot을 그대로 쓰고, 브리프 맨 앞에 "⚠ API 수집 실패/키 미입력 — 기준일 X의 기존 데이터 사용" 경고를 단다. snapshot이 비어 있으면 현황 수치는 전부 "미확인".
2. **리포트 반영**: inbox에 PDF가 있으면 `/ingest` 절차(.claude/skills/ingest/SKILL.md)를 먼저 수행한다. 없어도 `python scripts/ingest_inbox.py --pending`으로 카드 없는 리포트가 있는지 확인한다.
3. **매크로 서브에이전트 5개를 한 메시지에서 병렬로 실행**: fx-commodity, kr-fixed-income, us-fixed-income, kr-alternatives, us-alternatives.
   각 프롬프트: "AS_OF={AS_OF}. 담당 topic의 macro_topic JSON을 knowledge/macro_topics/{AS_OF}/에 저장하고 validate_json.py로 검증하라. CLAUDE.md 원칙을 따르라."
4. **검증**: `python scripts/validate_json.py knowledge/macro_topics/{AS_OF}/ --expect-all-topics` — 16개 모두 오류 0이어야 한다. 오류가 있으면 담당 에이전트에 재요청하거나 직접 고친다.
5. **브리프 초안 생성**: `python scripts/render_brief.py --date {AS_OF}` → `reports/{AS_OF}_macro_brief.md`
   (한 장 요약 표, 항목별 상세, 팩터 충격 표, 부록을 JSON에서 결정적으로 만든다.) 그 다음 메인 에이전트가 직접 아래 서술 섹션을 채운다:
   - "이번 주 핵심 변화 3가지" (snapshot의 chg_1w·chg_1m이 큰 지표와 신규 하우스 뷰 기준)
   - "하우스 간 이견이 큰 항목"
   - "크로스에셋 시사점" (예: 한미 금리차 → 환율 → 해외채 헤지비용, 유가 → 물가 → 금리, 금리 → 캡레이트 → 부동산/인프라 평가)
   렌더러가 남긴 `<!-- TODO: ... -->` 자리를 채우고 TODO 주석은 지운다.
6. **팩트체크**: fact-checker 서브에이전트에 브리프 경로만 전달 → 불일치 목록을 받아 수정 → 수정 후 `python scripts/check_report.py reports/{AS_OF}_macro_brief.md --kind macro`로 재확인.
7. **사용자 보고**: 핵심 요약 5줄 + 파일 경로 + 데이터 공백/경고.

## 브리프 구성 (render_brief.py가 골격을 만든다)
- 맨 앞: 한 장 요약 — 16개 항목 표 (항목 | 현황 핵심 수치(기준일) | 단기 방향 | 장기 Base | 확신도)
- 이번 주 핵심 변화 3가지, 하우스 간 이견이 큰 항목
- 항목별 상세 (1~16): 현황 지표 표 → 단기 → 장기 시나리오 표 → 하우스 뷰 컨센서스/이견 → 팩터 충격 → 데이터 공백
- 크로스에셋 시사점
- 부록: 사용한 view_card 목록, 데이터 기준일 표, 면책 문구
