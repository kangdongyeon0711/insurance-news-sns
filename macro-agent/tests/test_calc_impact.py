"""calc_impact 손계산 검증. 포트폴리오·충격은 가상 데이터(실제 회사 아님)."""
import json
from pathlib import Path

import pytest

import calc_impact as ci
from common import CONFIG_DIR, load_yaml

FIX = Path(__file__).parent / "fixtures"


def _pf(*assets, total=None, liabilities=None):
    total = total or sum(a["mv_krw_bn"] for a in assets)
    return {"company": "테스트", "period": "2026Q2", "total_invested_assets_krw_bn": total,
            "assets": [{"region": "KR", "currency": "KRW", "value_flag": "공시", "page_ref": "p.1",
                        "weight": a["mv_krw_bn"] / total, **a} for a in assets],
            "liabilities": liabilities or {"duration": None, "value_flag": "미확인", "page_ref": None}}


def _one(pf, shocks, **kw):
    return ci.run(pf, {"as_of": "2026-10-25", "scenarios": [{"name": "s", "shocks": shocks}]}, ci.Engine(**kw))["scenarios"][0]


def test_duration5_bond_100bp():
    """듀레이션 5년 국공채 1,000억(=100십억)에 +100bp → 약 −50억 (컨벡시티 제외)."""
    s = _one(_pf({"class": "국공채", "mv_krw_bn": 100, "mod_duration": 5.0}),
             {"ktb_3y_bp": 100, "ktb_10y_bp": 100, "ktb_30y_bp": 100})
    assert s["rows"][0]["impact_100m"] == pytest.approx(-50.0)
    assert s["total_bp"] == pytest.approx(-500.0)
    assert s["rows"][0]["estimated"] is False


def test_convexity_approx_reduces_loss():
    a = load_yaml(CONFIG_DIR / "assumptions.yaml")
    a["convexity_mode"] = "approx"
    s = _one(_pf({"class": "국공채", "mv_krw_bn": 100, "mod_duration": 5.0}),
             {"ktb_3y_bp": 100, "ktb_10y_bp": 100, "ktb_30y_bp": 100}, assumptions=a)
    # −5% + ½·25·0.0001 = −4.875% → −48.75억
    assert s["rows"][0]["impact_100m"] == pytest.approx(-48.75)


def test_curve_interpolation():
    """D=6.5 → 3Y(+10)과 10Y(+80) 사이 선형보간 = +45bp."""
    s = _one(_pf({"class": "국공채", "mv_krw_bn": 1000, "mod_duration": 6.5}),
             {"ktb_3y_bp": 10, "ktb_10y_bp": 80, "ktb_30y_bp": 100})
    assert s["rows"][0]["impact_100m"] == pytest.approx(-1000 * 6.5 * 0.0045 * 10)


def test_corp_bond_spread_and_grade():
    shocks = {"ktb_3y_bp": 0, "ktb_10y_bp": 0, "ktb_30y_bp": 0, "kr_aa_spread_bp": 20, "kr_bbb_spread_bp": 100}
    aa = _one(_pf({"class": "회사채", "mv_krw_bn": 100, "mod_duration": 3, "spread_duration": 3, "credit_grade": "AA"}), shocks)
    bbb = _one(_pf({"class": "회사채", "mv_krw_bn": 100, "mod_duration": 3, "spread_duration": 3, "credit_grade": "BBB"}), shocks)
    assert aa["rows"][0]["impact_100m"] == pytest.approx(-6.0)    # 100십억×3×0.002 = 0.6십억 = 6억
    assert bbb["rows"][0]["impact_100m"] == pytest.approx(-30.0)
    assert aa["rows"][0]["estimated"] is False


def test_foreign_bond_fx_and_hedge():
    """해외채 1조: 헤지 80%. 금리·스프레드 0, 원화약세 +5%, 헤지비용 +50bp(1년)."""
    s = _one(_pf({"class": "해외채", "region": "US", "currency": "USD", "mv_krw_bn": 1000, "mod_duration": 7,
                  "spread_duration": 7, "credit_grade": "IG", "fx_hedge_ratio": 0.8}),
             {"ust_2y_bp": 0, "ust_10y_bp": 0, "ust_30y_bp": 0, "us_ig_oas_bp": 0, "krw_usd_pct": 5, "fx_hedge_cost_bp": 50})
    comp = s["rows"][0]["components_100m"]
    assert comp["fx"] == pytest.approx(1000 * 0.2 * 0.05 * 10)      # +100억
    assert comp["hedge_cost"] == pytest.approx(-1000 * 0.8 * 0.005 * 10)  # −40억
    assert s["rows"][0]["estimated"] is True  # 헤지 보유기간 가정


def test_real_estate_cap_rate():
    """캡레이트 4.5%(가정)에서 +45bp → −10%."""
    s = _one(_pf({"class": "부동산", "mv_krw_bn": 100}), {"kr_cre_cap_rate_bp": 45})
    assert s["rows"][0]["impact_100m"] == pytest.approx(-100.0)
    assert s["rows"][0]["estimated"] is True


def test_pf_private_debt_pe_equity_infra():
    pf = _pf({"class": "대출-부동산PF", "mv_krw_bn": 100}, {"class": "대체-사모대출", "mv_krw_bn": 100},
             {"class": "대체-PE", "mv_krw_bn": 100}, {"class": "주식", "mv_krw_bn": 100, "beta": 1.2},
             {"class": "대체-인프라", "mv_krw_bn": 100, "mod_duration": 12})
    s = _one(pf, {"kr_pf_loss_rate_pp": 3, "kr_pd_default_pp": 2, "kr_pe_value_pct": -10,
                  "equity_kospi_pct": -10, "infra_discount_rate_bp": 50})
    got = [r["impact_100m"] for r in s["rows"]]
    assert got == pytest.approx([-30.0, -100 * 0.02 * 0.45 * 10, -100.0, -120.0, -100 * 12 * 0.005 * 10])


def test_missing_factor_recorded():
    s = _one(_pf({"class": "국공채", "mv_krw_bn": 100, "mod_duration": 10}), {"ktb_10y_bp": 10})
    assert "ktb_3y_bp" in s["missing_factors"] and s["rows"][0]["impact_100m"] == pytest.approx(-10.0)


def test_alm_net_assets():
    """D_A·A = 10×1000, D_L·L = 12×900, Δy(ktb_10y) = −50bp → 자산 +500억, 부채 +540억, 순 −40억."""
    pf = _pf({"class": "국공채", "mv_krw_bn": 1000, "mod_duration": 10},
             liabilities={"duration": 12, "pv_krw_bn": 900, "value_flag": "공시", "page_ref": "p.9"})
    s = _one(pf, {"ktb_3y_bp": -50, "ktb_10y_bp": -50, "ktb_30y_bp": -50})
    assert s["alm"]["net_100m"] == pytest.approx(-40.0)
    assert s["alm"]["duration_gap_years"] == pytest.approx(-0.8)


def test_sample_fixture_and_prob_weighted():
    pf = json.loads((FIX / "sample_exposures.json").read_text(encoding="utf-8"))
    sh = json.loads((FIX / "sample_shocks.json").read_text(encoding="utf-8"))
    assert pf["is_sample"] is True and "실제 회사 데이터가 아님" in pf["_disclaimer"]
    assert sum(a["mv_krw_bn"] for a in pf["assets"]) == pf["total_invested_assets_krw_bn"] == 50000
    r = ci.run(pf, sh)
    stress = r["scenarios"][0]
    assert stress["rows"][0]["impact_100m"] == pytest.approx(-12000.0)  # 20조×12×50bp
    pw = r["prob_weighted"]
    exp = sum(s["prob"] * s["total_100m"] for s in r["scenarios"] if s["prob"] is not None)
    assert pw["total_100m"] == pytest.approx(exp, abs=0.5)
    assert pw["scenarios"] == ["장기-Base", "장기-Bull", "장기-Bear"]


def test_constraints():
    pf = json.loads((FIX / "sample_exposures.json").read_text(encoding="utf-8"))
    cons = load_yaml(CONFIG_DIR / "constraints.yaml")
    res = {c["name"]: c for c in ci.check_constraints(pf, cons, {"duration_gap_years": -0.5})}
    assert res["대체투자 합계"]["value"] == pytest.approx(0.10) and res["대체투자 합계"]["ok"]
    assert res["듀레이션 갭(년)"]["ok"] is True
    after = {c["name"]: c for c in ci.check_constraints(pf, cons, None, {"deltas_pp": {"대체-인프라": 6}})}
    assert after["대체투자 합계"]["value"] == pytest.approx(0.16) and after["대체투자 합계"]["ok"] is False
    assert after["조정폭 대체-인프라"]["ok"] is False


def test_infra_discount_rate_by_region():
    """국내 인프라는 infra_discount_rate_bp, 해외 인프라는 us_infra_discount_rate_bp (없으면 국내 값 근사 + 추정)."""
    pf = _pf({"class": "대체-인프라", "mv_krw_bn": 100, "mod_duration": 10, "region": "KR"},
             {"class": "대체-인프라", "mv_krw_bn": 100, "mod_duration": 10, "region": "US", "currency": "USD",
              "fx_hedge_ratio": 1.0})
    s = _one(pf, {"infra_discount_rate_bp": 10, "us_infra_discount_rate_bp": -20})
    assert [r["components_100m"]["discount_rate"] for r in s["rows"]] == pytest.approx([-10.0, 20.0])
    s2 = _one(pf, {"infra_discount_rate_bp": 10})
    assert s2["rows"][1]["components_100m"]["discount_rate"] == pytest.approx(-10.0)
    assert any("근사" in x for x in s2["rows"][1]["estimated_reasons"])
