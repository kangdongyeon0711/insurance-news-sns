---
name: ingest
description: inbox/의 증권사 리포트·보험사 공시 PDF를 텍스트·표로 추출해 processed/로 옮기고, 새 리포트마다 report-reader로 view_card를 만든다. 사용자가 /ingest를 입력하거나 inbox에 새 PDF를 넣었다고 할 때 사용.
---

# /ingest

CLAUDE.md의 원칙을 따른다. inbox 파일은 이동만 하고 절대 삭제하지 않는다.

## 절차
1. `python scripts/ingest_inbox.py` 실행. 출력 JSON에서 `new_reports`, `new_filings`, `pending_cards`, `low_quality`, `estimated_names`, `failed`, `duplicates`를 확인한다.
   - `failed`가 있으면 원인을 사용자에게 알린다 (파일은 inbox에 남아 있음).
   - `duplicates`는 "이미 처리된 파일과 내용이 같아 inbox에 그대로 두었다"고 알린다 (삭제 여부는 사용자가 결정).
2. `pending_cards`(카드가 없는 리포트)가 있으면 **report-reader** 서브에이전트를 실행한다.
   - 3개 이하: 1개 에이전트에 모두 전달.
   - 4개 이상: 2~3개씩 묶어 여러 report-reader를 **한 메시지에서 병렬로** 실행.
   - 프롬프트에 card_id 목록과 "CLAUDE.md 원칙을 따르고, 끝나면 validate_json.py로 검증하라"를 넣는다.
3. 모든 카드 검증: `python scripts/validate_json.py knowledge/view_cards/` — 오류가 있으면 해당 report-reader에 수정 요청(또는 직접 수정).
4. 새 공시(`new_filings`)가 있으면: "공시 N개가 처리되었습니다. `/portfolio-impact {회사}`로 분석할 수 있습니다."라고 안내한다.
5. 결과 요약을 사용자에게 보고한다 (표):
   - 리포트 N개 → 카드 N개 (매크로 무관 M개)
   - topic별 카드 수: `python scripts/recent_cards.py --days 3650` 출력 또는 카드 topics 집계
   - 파일명 추정 처리된 파일, 텍스트 품질 낮은 파일(스캔본 의심)
