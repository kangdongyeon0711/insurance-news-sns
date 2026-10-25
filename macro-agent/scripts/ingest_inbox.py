"""inbox/ PDF → 텍스트·표 추출 + 분류 + processed/로 이동 + manifest 기록.

사용:
  python scripts/ingest_inbox.py            # inbox/reports, inbox/filings 처리
  python scripts/ingest_inbox.py --dry-run  # 이동 없이 무엇을 처리할지 출력

- 텍스트: pdfplumber → 실패/빈약하면 pymupdf 재시도. 페이지 구분자 '=== p.N ==='.
- 표: pdfplumber extract_tables → {stem}_tables.json (페이지 번호 포함).
- 이미 처리한 파일(sha256 동일)은 건너뛴다. 사용자 파일은 삭제하지 않고 이동만 한다
  (중복 파일은 inbox에 그대로 두고 알린다).
- 파일명 규칙: 리포트 YYYYMMDD_하우스_리포트명.pdf / 공시 회사_YYYYQn_자료종류.pdf (또는 회사_YYYY_자료종류.pdf)
  규칙에 안 맞으면 첫 페이지에서 날짜·하우스(회사)를 추정하고 manifest에 estimated: true로 기록한다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

from common import INBOX_DIR, MANIFEST_PATH, PROCESSED_DIR, get_logger, load_json, save_json, save_text

log = get_logger("ingest")

# 약칭 → 정식 하우스명 (파일명 하우스 토큰과 첫 페이지 추정에 사용)
HOUSES = {
    "미래": "미래에셋증권", "미래에셋": "미래에셋증권", "신한": "신한투자증권", "삼성": "삼성증권",
    "KB": "KB증권", "NH": "NH투자증권", "한투": "한국투자증권", "한국투자": "한국투자증권", "키움": "키움증권",
    "하나": "하나증권", "메리츠": "메리츠증권", "대신": "대신증권", "유안타": "유안타증권", "교보": "교보증권",
    "하이": "하이투자증권", "iM": "iM증권", "IBK": "IBK투자증권", "신영": "신영증권", "한화": "한화투자증권",
    "DB": "DB금융투자", "현대차": "현대차증권", "LS": "LS증권", "이베스트": "LS증권", "SK": "SK증권",
    "유진": "유진투자증권", "다올": "다올투자증권", "BNK": "BNK투자증권", "부국": "부국증권",
    "상상인": "상상인증권", "샘플": "샘플(가상)", "케이프": "케이프투자증권", "한양": "한양증권", "흥국": "흥국증권",
}
INSURERS = ["현대해상", "삼성화재", "DB손해보험", "DB손보", "KB손해보험", "KB손보", "메리츠화재", "한화손해보험",
            "롯데손해보험", "흥국화재", "삼성생명", "한화생명", "교보생명", "신한라이프", "NH농협생명",
            "동양생명", "미래에셋생명", "ABL생명", "KB라이프", "흥국생명", "DB생명"]
DOC_KINDS = ["경영실적", "정기경영공시", "사업보고서", "분기보고서", "반기보고서", "IR", "실적발표"]

REPORT_RE = re.compile(r"^(?P<date>\d{8})_(?P<house>[^_]+)_(?P<title>.+)$")
FILING_RE = re.compile(r"^(?P<company>[^_]+)_(?P<period>\d{4}(?:Q[1-4]|H[12])?)_(?P<kind>.+)$")
DATE_RES = [
    re.compile(r"(20\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})"),
]
MIN_CHARS_PER_PAGE = 200


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_text(path: Path) -> tuple[list[str], str]:
    """페이지별 텍스트와 사용 엔진을 반환. pdfplumber 결과가 빈약하면 pymupdf로 재시도."""
    pages: list[str] = []
    try:
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            pages = [(p.extract_text() or "") for p in pdf.pages]
    except Exception as e:  # noqa: BLE001
        log.warning("%s: pdfplumber 실패 (%s) → pymupdf 재시도", path.name, e)
    if pages and _avg_chars(pages) >= MIN_CHARS_PER_PAGE:
        return pages, "pdfplumber"
    try:
        import pymupdf

        with pymupdf.open(path) as doc:
            alt = [p.get_text() or "" for p in doc]
        if _avg_chars(alt) > _avg_chars(pages):
            return alt, "pymupdf"
    except Exception as e:  # noqa: BLE001
        log.warning("%s: pymupdf도 실패 (%s)", path.name, e)
    return pages, "pdfplumber"


def extract_tables(path: Path) -> list[dict]:
    out = []
    try:
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                for j, tbl in enumerate(page.extract_tables() or [], start=1):
                    if tbl and any(any(c for c in row if c) for row in tbl):
                        out.append({"page": i, "page_ref": f"p.{i}", "index": j, "rows": tbl})
    except Exception as e:  # noqa: BLE001
        log.warning("%s: 표 추출 실패 (%s)", path.name, e)
    return out


def _avg_chars(pages: list[str]) -> float:
    return sum(len(p.strip()) for p in pages) / len(pages) if pages else 0.0


def quality_flag(pages: list[str]) -> str:
    avg = _avg_chars(pages)
    if avg == 0:
        return "empty"   # 스캔본 가능성 — OCR 필요
    if avg < MIN_CHARS_PER_PAGE:
        return "low"
    return "good"


def guess_date(text: str) -> str | None:
    for rx in DATE_RES:
        for m in rx.finditer(text):
            y, mo, d = map(int, m.groups())
            try:
                return datetime(y, mo, d).strftime("%Y-%m-%d")
            except ValueError:
                continue
    return None


def guess_house(text: str) -> str | None:
    full = sorted(set(HOUSES.values()), key=len, reverse=True)
    for name in full:
        if name in text:
            return name
    for short in sorted(HOUSES, key=len, reverse=True):
        if re.search(rf"(?<![A-Za-z가-힣]){re.escape(short)}(?![A-Za-z])", text):
            return HOUSES[short]
    return None


def classify_report(path: Path, first_page: str) -> dict:
    m = REPORT_RE.match(path.stem)
    if m:
        d = m["date"]
        house = HOUSES.get(m["house"], m["house"])
        return {"date": f"{d[:4]}-{d[4:6]}-{d[6:]}", "house": house, "house_token": m["house"],
                "title": m["title"], "stem": path.stem, "estimated": False}
    date = guess_date(first_page)
    house = guess_house(first_page)
    stem = f"{(date or '00000000').replace('-', '')}_{_house_token(house)}_{_safe(path.stem)}"
    return {"date": date, "house": house or "미확인", "house_token": _house_token(house), "title": path.stem,
            "stem": stem, "estimated": True,
            "estimate_note": f"파일명 규칙 불일치 — 첫 페이지에서 날짜({date or '미확인'})·하우스({house or '미확인'}) 추정"}


COMPANY_RE = re.compile(r"([가-힣A-Za-z]{1,12}(?:화재|손해보험|생명보험|생명|증권|투자증권|금융투자|자산운용|은행))")


def detect_entity_type(company: str | None, text: str = "") -> str:
    """config/entity_profiles.yaml의 detect 규칙으로 업종 추정 (회사명 우선, 없으면 본문)."""
    from common import CONFIG_DIR, load_yaml

    rules = load_yaml(CONFIG_DIR / "entity_profiles.yaml").get("detect", [])
    for target in (company or "", text[:3000]):
        for r in rules:
            if any(p in target for p in r["name_patterns"]):
                return r["entity_type"]
    return "other"


def classify_filing(path: Path, first_page: str) -> dict:
    m = FILING_RE.match(path.stem)
    if m:
        company = _norm_company(m["company"])
        return {"company": company, "period": m["period"], "doc_kind": m["kind"], "stem": path.stem,
                "estimated": False, "entity_type": detect_entity_type(company, first_page)}
    company = next((c for c in INSURERS if c in first_page or c in path.stem), None)
    if not company:   # 목록에 없는 보험사·증권사·운용사·은행: 이름 패턴으로
        mm = COMPANY_RE.search(path.stem) or COMPANY_RE.search(first_page)
        company = mm.group(1) if mm else None
    company = _norm_company(company) if company else None
    pm = re.search(r"(20\d{2})\s*년?\s*(?:([1-4])\s*(?:분기|Q))", first_page + " " + path.stem)
    if pm:
        period = f"{pm[1]}Q{pm[2]}"
    else:
        y = re.search(r"(20\d{2})", first_page + " " + path.stem)
        period = y[1] if y else "0000"
    kind = next((k for k in DOC_KINDS if k in first_page or k in path.stem), "미확인")
    stem = f"{company or '미확인'}_{period}_{_safe(kind)}_{_safe(path.stem)}"
    return {"company": company or "미확인", "period": period, "doc_kind": kind, "stem": stem, "estimated": True,
            "entity_type": detect_entity_type(company, first_page),
            "estimate_note": f"파일명 규칙 불일치 — 첫 페이지/파일명에서 회사({company or '미확인'})·기간({period}) 추정"}


def _norm_company(name: str) -> str:
    return {"DB손보": "DB손해보험", "KB손보": "KB손해보험"}.get(name, name)


def _house_token(house: str | None) -> str:
    if not house:
        return "미확인"
    for k, v in HOUSES.items():
        if v == house:
            return k
    return house


def _safe(s: str) -> str:
    return re.sub(r"[\\/:*?\"<>|\s]+", "", s)[:60] or "untitled"


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return load_json(MANIFEST_PATH)
    return {"files": []}


def _num(x: float) -> str:
    """재무 데이터 정밀도 보존: 최단 왕복 표현(repr), 지수 표기일 때만 고정소수로."""
    s = repr(float(x))
    if "e" in s or "E" in s:
        s = f"{x:.12f}".rstrip("0").rstrip(".")
    return s[:-2] if s.endswith(".0") else s


def extract_xlsx(path: Path) -> tuple[list[str], list[dict]]:
    """엑셀(IR 데이터 시트 등) → 시트별 텍스트(행은 ' | ' 구분)와 표 목록. 시트를 '페이지'로 취급(=== p.N === 대신 시트명 병기)."""
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    pages, tables = [], []
    for i, ws in enumerate(wb.worksheets, start=1):
        rows = []
        for r in ws.iter_rows(values_only=True):
            if any(c not in (None, "") for c in r):
                rows.append(["" if c is None else (_num(c) if isinstance(c, float) else str(c)) for c in r])
        pages.append(f"[시트: {ws.title}]\n" + "\n".join(" | ".join(r) for r in rows))
        tables.append({"page": i, "page_ref": f"sheet:{ws.title}", "index": 1, "rows": rows})
    return pages, tables


ACCEPT = {"report": {".pdf"}, "filing": {".pdf", ".xlsx", ".xlsm"}}


def _unique_dest(directory: Path, stem: str, ext: str = ".pdf") -> str:
    candidate, n = stem, 2
    while (directory / f"{candidate}{ext}").exists():
        candidate = f"{stem}_{n}"
        n += 1
    return candidate


def process(kind: str, dry_run: bool = False, inbox: Path = INBOX_DIR, processed: Path = PROCESSED_DIR,
            manifest_path: Path = MANIFEST_PATH) -> dict:
    sub = "reports" if kind == "report" else "filings"
    src_dir, dst_dir = inbox / sub, processed / sub
    manifest = load_json(manifest_path) if manifest_path.exists() else {"files": []}
    seen = {e["sha256"]: e for e in manifest["files"]}
    result = {"new": [], "duplicate": [], "failed": [], "ignored": []}
    for path in sorted(src_dir.iterdir()) if src_dir.exists() else []:
        if path.name.startswith(".") or path.is_dir():
            continue
        ext = path.suffix.lower()
        if ext not in ACCEPT[kind]:
            result["ignored"].append(path.name)
            log.warning("지원하지 않는 형식이라 건너뜀(%s): %s", "/".join(sorted(ACCEPT[kind])), path.name)
            continue
        digest = sha256(path)
        if digest in seen:
            result["duplicate"].append({"file": path.name, "already_as": seen[digest]["stem"]})
            log.info("이미 처리됨(해시 동일), inbox에 그대로 둠: %s → %s", path.name, seen[digest]["stem"])
            continue
        try:
            if ext == ".pdf":
                pages, engine = extract_text(path)
            else:
                pages, xl_tables = extract_xlsx(path)
                engine = "openpyxl"
            first = pages[0] if pages else ""
            meta = classify_report(path, first) if kind == "report" else classify_filing(path, first)
            meta["stem"] = _unique_dest(dst_dir, meta["stem"], ext)
            if dry_run:
                result["new"].append({"file": path.name, **meta})
                continue
            stem = meta["stem"]
            text = "\n".join(f"=== p.{i} ===\n{t}" for i, t in enumerate(pages, start=1))
            save_text(dst_dir / f"{stem}.txt", text)
            tables = extract_tables(path) if ext == ".pdf" else xl_tables
            save_json(dst_dir / f"{stem}_tables.json", {"source": f"processed/{sub}/{stem}{ext}", "tables": tables})
            dst_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), dst_dir / f"{stem}{ext}")
            entry = {
                "original_name": path.name, "stem": stem, "type": kind, "sha256": digest, "format": ext.lstrip("."),
                "pdf": f"processed/{sub}/{stem}{ext}", "text": f"processed/{sub}/{stem}.txt",
                "tables": f"processed/{sub}/{stem}_tables.json", "n_tables": len(tables),
                "pages": len(pages), "text_engine": engine, "text_quality": quality_flag(pages),
                "processed_at": datetime.now().isoformat(timespec="seconds"),
                **{k: v for k, v in meta.items() if k != "stem"},
            }
            if kind == "report":
                entry["card_id"] = stem
            manifest["files"].append(entry)
            seen[digest] = entry
            save_json(manifest_path, manifest)
            result["new"].append(entry)
            log.info("처리: %s → %s (%d쪽, 표 %d개, 품질 %s%s)", path.name, stem, len(pages), len(tables),
                     entry["text_quality"], ", 추정" if meta["estimated"] else "")
        except Exception as e:  # noqa: BLE001 — 한 파일 실패가 전체를 막지 않음
            result["failed"].append({"file": path.name, "error": str(e)})
            log.error("처리 실패: %s (%s) — inbox에 그대로 둠", path.name, e)
    return result


def pending_cards(manifest_path: Path = MANIFEST_PATH, cards_dir: Path | None = None) -> list[dict]:
    """manifest의 리포트 중 view_card가 아직 없는 것."""
    from common import KNOWLEDGE_DIR

    cards_dir = cards_dir or KNOWLEDGE_DIR / "view_cards"
    if not manifest_path.exists():
        return []
    files = load_json(manifest_path)["files"]
    return [e for e in files if e["type"] == "report" and not (cards_dir / f"{e['card_id']}.json").exists()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pending", action="store_true", help="카드가 없는 리포트 목록만 출력")
    args = ap.parse_args(argv)
    if args.pending:
        print(json.dumps([{k: e[k] for k in ("card_id", "text", "pdf", "house", "date", "pages", "text_quality")}
                          for e in pending_cards()], ensure_ascii=False, indent=2))
        return 0
    rep, fil = process("report", args.dry_run), process("filing", args.dry_run)
    summary = {
        "reports": {k: len(v) for k, v in rep.items()},
        "filings": {k: len(v) for k, v in fil.items()},
        "new_reports": [e.get("stem") for e in rep["new"]],
        "new_filings": [e.get("stem") for e in fil["new"]],
        "low_quality": [e["stem"] for e in rep["new"] + fil["new"] if e.get("text_quality") in ("low", "empty")],
        "estimated_names": [e["stem"] for e in rep["new"] + fil["new"] if e.get("estimated")],
        "failed": rep["failed"] + fil["failed"],
        "duplicates": rep["duplicate"] + fil["duplicate"],
        "pending_cards": [e["card_id"] for e in pending_cards()] if not args.dry_run else [],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
