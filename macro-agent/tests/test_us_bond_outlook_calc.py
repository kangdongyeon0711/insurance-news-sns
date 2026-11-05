"""us_bond_outlook_calc 손익 산식 검증(캐리 − 듀레이션×금리 변화 − 스프레드 듀레이션×스프레드 변화 − 기대손실)."""
import json

import pytest

import us_bond_outlook_calc as uc


def test_pnl_formula():
    # 5% 캐리, 듀레이션 8, 금리 +50bp, 1년 → 5 − 4 = +1%
    assert uc.pnl(5.0, 8.0, 50, 1.0) == pytest.approx(1.0)
    # 스프레드 듀레이션 6.8, 스프레드 +10bp, 기대손실 0.1% → 추가 −0.68 − 0.1
    assert uc.pnl(5.86, 6.8, -25, 1.0, 6.8, 10, 0.1) == pytest.approx(5.86 + 1.7 - 0.68 - 0.1)


def test_outputs_consistent(tmp_path):
    out = tmp_path / "us.json"
    assert uc.main(["--date", "2026-11-05", "--out", str(out)]) == 0
    d = json.loads(out.read_text())
    ig = d["rows"]["IG"]
    oas = d["levels"]["us_ig_oas"]["value"]
    # 국채 대비 초과수익 = OAS − SD × ΔOAS − EL
    for n in ("Base", "Bull", "Bear"):
        exp = oas - uc.DUR["IG"] * ig[n]["spread_bp"] / 100 - uc.EL["IG"][n]
        assert ig["excess_vs_ust_pct"][n] == pytest.approx(exp, abs=0.011)
    # 손익분기 스프레드 확대 = (OAS − EL_Base) / SD
    assert ig["breakeven_1y_bp"]["spread_vs_ust"] == pytest.approx((oas - uc.EL["IG"]["Base"]) / uc.DUR["IG"] * 100, abs=0.06)
