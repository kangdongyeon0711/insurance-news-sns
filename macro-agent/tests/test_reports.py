"""render_brief / render_portfolio / check_report — 가상 데이터로 표 수치 대조 검증."""
import copy
import json
from pathlib import Path

import calc_impact as ci
import check_report as cr
import render_brief as rb
import render_portfolio as rp
from common import TOPIC_IDS

FIX = Path(__file__).parent / "fixtures"


def _setup(tmp_path, monkeypatch):
    snap = {"generated_at": "x", "ref_date": "2026-10-25", "fetch_status": {"ecos": "ok"}, "warnings": [],
            "series": {"ktb_3y": {"series_id": "ktb_3y", "name": "국고채 3년", "topic_id": "kr_govt_bond", "unit": "%",
                                  "chg_unit": "bp", "last_value": 2.95, "as_of": "2026-10-24", "chg_1w": 3.0,
                                  "chg_1m": -5.0, "stale": False, "verified": False, "age_days": 1}}}
    sp = tmp_path / "snap.json"
    sp.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    kd = tmp_path / "knowledge"
    td = kd / "macro_topics" / "2026-10-25"
    td.mkdir(parents=True)
    base = json.loads((FIX / "sample_macro_topic.json").read_text(encoding="utf-8"))
    for t in TOPIC_IDS:
        d = copy.deepcopy(base)
        d["topic_id"] = t
        if t == "kr_govt_bond":
            d["current"]["indicators"] = [{"series_id": "ktb_3y", "name": "국고채 3년", "value": 2.95, "unit": "%",
                                           "as_of": "2026-10-24", "chg_1m": -5.0, "chg_unit": "bp", "value_flag": "API"}]
        (td / f"{t}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(rb, "SNAPSHOT_PATH", sp)
    monkeypatch.setattr(rb, "KNOWLEDGE_DIR", kd)
    return snap


def test_brief_render_and_check(tmp_path, monkeypatch):
    snap = _setup(tmp_path, monkeypatch)
    md = rb.render("2026-10-25")
    assert "## 한 장 요약" in md and md.count("### ") >= 16 + 2 and "투자 권유가 아" in md
    errs, _ = cr.check_macro(md, snap)
    assert errs == []
    bad = md.replace("| 2.95 % | 2026-10-24 |", "| 3.05 % | 2026-10-24 |")
    errs, _ = cr.check_macro(bad, snap)
    assert any("ktb_3y" in e and "≠ snapshot" in e for e in errs)
    errs, _ = cr.common_checks(md + "\n`made_up_bp`")
    assert any("made_up_bp" in e for e in errs) and any("TODO" in e for e in errs)


def test_portfolio_render_and_check():
    pf = json.loads((FIX / "sample_exposures.json").read_text(encoding="utf-8"))
    sh = json.loads((FIX / "sample_shocks.json").read_text(encoding="utf-8"))
    impact = ci.run(pf, sh)
    md = rp.render(impact, [pf], "2026-10-25")
    assert "가상 샘플" in md
    errs, _ = cr.check_portfolio(md, impact)
    assert errs == []
    tampered = md.replace("| 국공채 | 20,000 | -12,000*", "| 국공채 | 20,000 | -11,000*")
    errs, _ = cr.check_portfolio(tampered, impact)
    assert any("국공채/스트레스" in e for e in errs)
    nostar = md.replace("| 국공채 | 20,000 | -12,000*", "| 국공채 | 20,000 | -12,000")
    assert any("'*'" in e for e in cr.check_portfolio(nostar, impact)[0])


def test_sentences_never_cut_mid_sentence():
    from render_brief import sentences, scenario_line
    text = "[판단] 첫 문장은 3.50%에서 정점. 두 번째 문장은 조금 더 길게 이어진다. 세 번째."
    assert sentences(text, 10) == "[판단] 첫 문장은 3.50%에서 정점."  # 한도보다 길어도 첫 문장은 통째로
    assert sentences(text, 200) == text
    assert "…" not in sentences(text, 30)
    assert scenario_line({"headline": "한 문장 요약.", "narrative": text}) == "한 문장 요약."
    assert scenario_line({"narrative": text}) == "[판단] 첫 문장은 3.50%에서 정점."
