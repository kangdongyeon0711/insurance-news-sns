"""ingest_inbox: 가상 PDF로 추출·분류·이동·manifest·중복 스킵 검증 (실제 리포트 아님)."""
import json
import shutil
import sys
from pathlib import Path

import ingest_inbox as ing

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
from make_sample_pdf import make  # noqa: E402


def _dirs(tmp_path):
    inbox, processed = tmp_path / "inbox", tmp_path / "processed"
    for d in (inbox / "reports", inbox / "filings"):
        d.mkdir(parents=True)
    return inbox, processed, processed / "manifest.json"


def test_report_ingest_and_dedup(tmp_path):
    inbox, processed, manifest = _dirs(tmp_path)
    pdf = make(inbox / "reports" / "20261023_미래_MacroWeekAhead.pdf")
    backup = tmp_path / "copy.pdf"
    shutil.copy(pdf, backup)
    r = ing.process("report", inbox=inbox, processed=processed, manifest_path=manifest)
    assert len(r["new"]) == 1
    e = r["new"][0]
    assert e["house"] == "미래에셋증권" and e["date"] == "2026-10-23" and e["estimated"] is False
    assert e["card_id"] == "20261023_미래_MacroWeekAhead" and e["pages"] == 2
    txt = (processed / "reports" / "20261023_미래_MacroWeekAhead.txt").read_text(encoding="utf-8")
    assert "=== p.1 ===" in txt and "=== p.2 ===" in txt
    assert not pdf.exists() and (processed / "reports" / f"{e['stem']}.pdf").exists()
    assert json.loads(manifest.read_text(encoding="utf-8"))["files"][0]["sha256"] == e["sha256"]
    # 같은 내용을 다른 이름으로 다시 넣으면 건너뛰고 inbox에 남긴다
    again = inbox / "reports" / "다른이름.pdf"
    shutil.copy(backup, again)
    r2 = ing.process("report", inbox=inbox, processed=processed, manifest_path=manifest)
    assert r2["new"] == [] and len(r2["duplicate"]) == 1 and again.exists()


def test_report_name_estimation(tmp_path):
    inbox, processed, manifest = _dirs(tmp_path)
    make(inbox / "reports" / "weekly macro.pdf")
    e = ing.process("report", inbox=inbox, processed=processed, manifest_path=manifest)["new"][0]
    assert e["estimated"] is True and e["date"] == "2026-10-23"
    assert e["stem"].startswith("20261023_")


def test_filing_ingest_tables(tmp_path):
    inbox, processed, manifest = _dirs(tmp_path)
    make(inbox / "filings" / "현대해상_2026Q2_경영실적.pdf", "filing")
    e = ing.process("filing", inbox=inbox, processed=processed, manifest_path=manifest)["new"][0]
    assert (e["company"], e["period"], e["doc_kind"]) == ("현대해상", "2026Q2", "경영실적")
    tables = json.loads((processed / "filings" / f"{e['stem']}_tables.json").read_text(encoding="utf-8"))
    assert tables["tables"] and tables["tables"][0]["page_ref"] == "p.1"


def test_house_guess():
    assert ing.guess_house("신한투자증권 리서치센터") == "신한투자증권"
    assert ing.guess_date("발간일 2026년 9월 3일") == "2026-09-03"
