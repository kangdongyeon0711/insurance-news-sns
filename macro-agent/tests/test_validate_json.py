import copy
import json
from pathlib import Path

import validate_json as vj

FIX = Path(__file__).parent / "fixtures"


def test_macro_topic_ok():
    assert vj.validate_file(FIX / "sample_macro_topic.json", "macro_topic", {"series": {}}) == []


def test_macro_topic_semantic_errors(tmp_path):
    doc = json.loads((FIX / "sample_macro_topic.json").read_text(encoding="utf-8"))
    bad = copy.deepcopy(doc)
    bad["long_term"]["scenarios"][0]["prob"] = 0.6
    bad["short_term_factor_shocks"] = {"not_a_factor": 1}
    bad["data_gaps"] = []
    p = tmp_path / "x.json"
    p.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    errs = " | ".join(vj.validate_file(p, "macro_topic", None))
    assert "확률 합" in errs and "not_a_factor" in errs and "하우스 뷰 부족" in errs


def test_snapshot_mismatch(tmp_path):
    doc = json.loads((FIX / "sample_macro_topic.json").read_text(encoding="utf-8"))
    doc["current"]["indicators"] = [{"series_id": "ktb_3y", "value": 2.9, "unit": "%", "as_of": "2026-10-24", "value_flag": "API"}]
    p = tmp_path / "x.json"
    p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    snap = {"series": {"ktb_3y": {"last_value": 2.95, "as_of": "2026-10-24"}}}
    assert any("≠ snapshot" in e for e in vj.validate_file(p, "macro_topic", snap))


def test_view_card(tmp_path):
    card = {"card_id": "20261023_샘플_Weekly", "house": "샘플", "report_title": "t", "published": "2026-10-23",
            "source_file": "processed/reports/20261023_샘플_Weekly.pdf", "topics": ["us_treasury"],
            "views": [{"topic_id": "us_treasury", "variable": "ust_10y", "direction": "하락", "horizon": "단기",
                       "target": None, "rationale": "r", "page_ref": "p.1", "conviction": "중간"},
                      {"topic_id": "oil", "variable": "brent", "direction": "상승", "horizon": "장기",
                       "target": None, "rationale": "r", "page_ref": "p.2", "conviction": "낮음"}],
            "key_risks": [], "notes": ""}
    p = tmp_path / "c.json"
    p.write_text(json.dumps(card, ensure_ascii=False), encoding="utf-8")
    errs = vj.validate_file(p, "view_card")
    assert len(errs) == 1 and "oil" in errs[0]
