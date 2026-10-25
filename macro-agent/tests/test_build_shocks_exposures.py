import copy
import json
from pathlib import Path

import pytest

import build_shocks
import validate_exposures as ve

FIX = Path(__file__).parent / "fixtures"


def _topic(tid, st, scen, probs=(0.5, 0.2, 0.3)):
    return {"topic_id": tid, "short_term_factor_shocks": st,
            "long_term": {"scenarios": [{"name": n, "prob": p, "factor_shocks": s}
                                        for n, p, s in zip(["Base", "Bull", "Bear"], probs, scen)]}}


def test_build_shocks_owner_and_expected(tmp_path):
    d = tmp_path / "2026-10-25"
    d.mkdir()
    # kr_govt_bond가 ktb_10y_bp의 주인. kr_rate도 ktb_10y_bp를 제시하지만 주인 값이 우선.
    (d / "kr_govt_bond.json").write_text(json.dumps(_topic("kr_govt_bond", {"ktb_10y_bp": -10},
        [{"ktb_10y_bp": -20}, {"ktb_10y_bp": -50}, {"ktb_10y_bp": 30}])), encoding="utf-8")
    (d / "kr_rate.json").write_text(json.dumps(_topic("kr_rate", {"ktb_10y_bp": -99, "kr_base_rate_bp": -25},
        [{"kr_base_rate_bp": -25}, {"kr_base_rate_bp": -50}, {"kr_base_rate_bp": 0}], (0.6, 0.2, 0.2))), encoding="utf-8")
    doc = build_shocks.build(d)
    sc = {s["name"]: s for s in doc["scenarios"]}
    assert sc["단기"]["shocks"]["ktb_10y_bp"] == -10 and doc["factor_sources"]["단기"]["ktb_10y_bp"] == "kr_govt_bond"
    assert sum(sc[f"장기-{n}"]["prob"] for n in ["Base", "Bull", "Bear"]) == pytest.approx(1.0)
    assert sc["장기-Base"]["prob"] == pytest.approx(0.55)
    # 기대값: ktb_10y = 0.5×−20 + 0.2×−50 + 0.3×30 = −11 ; base rate = 0.6×−25 + 0.2×−50 = −25
    assert sc["기대충격"]["shocks"]["ktb_10y_bp"] == pytest.approx(-11)
    assert sc["기대충격"]["shocks"]["kr_base_rate_bp"] == pytest.approx(-25)


def test_validate_exposures_total_and_shift(tmp_path, capsys):
    base = json.loads((FIX / "sample_exposures.json").read_text(encoding="utf-8"))
    p1 = copy.deepcopy(base)
    p1["period"] = "2022FY"
    p2 = copy.deepcopy(base)
    p2["period"] = "2023FY"
    p2["assets"][0]["mv_krw_bn"] = 23500   # 국공채 +7%p, 합계도 +7% 어긋남
    for i, p in enumerate((p1, p2)):
        (tmp_path / f"{p['period']}.json").write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
    rc = ve.main([str(tmp_path), "--trend"])
    out = capsys.readouterr().out
    assert rc == 1 and "자산 합계" in out and "급변" in out and "IFRS17" in out
    assert ve.period_key("2026Q2") > ve.period_key("2025FY") > ve.period_key("2025H1")
