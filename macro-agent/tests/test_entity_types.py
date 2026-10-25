"""업종 범용화: 증권사 듀레이션·우발채무, 자산운용사 AUM 보수 영향, 공시 민감도 캘리브레이션, 업종별 제약 (가상 데이터)."""
import pytest

import calc_impact as ci
from common import CONFIG_DIR, load_yaml

KR = {"ktb_3y_bp": 100, "ktb_10y_bp": 100, "ktb_30y_bp": 100}


def _pf(entity, assets, **extra):
    total = sum(a["mv_krw_bn"] for a in assets)
    return {"company": "가상", "period": "2026Q2", "entity_type": entity, "total_invested_assets_krw_bn": total,
            "assets": [{"region": "KR", "currency": "KRW", "value_flag": "공시", "page_ref": "p.1",
                        "weight": a["mv_krw_bn"] / total, **a} for a in assets],
            "liabilities": {"duration": None, "value_flag": "미확인", "page_ref": None}, **extra}


def _sc(shocks):
    return {"as_of": "2026-10-25", "scenarios": [{"name": "s", "shocks": shocks}]}


def test_securities_uses_short_default_duration():
    """증권사 국공채 기본 듀레이션 3.0(보험사 12.0) → +100bp에 −3%."""
    r = ci.run(_pf("securities", [{"class": "국공채", "mv_krw_bn": 100}]), _sc(KR))
    assert r["scenarios"][0]["rows"][0]["impact_100m"] == pytest.approx(-30.0)
    r2 = ci.run(_pf("insurer", [{"class": "국공채", "mv_krw_bn": 100}]), _sc(KR))
    assert r2["scenarios"][0]["rows"][0]["impact_100m"] == pytest.approx(-120.0)


def test_contingent_pf_guarantee_in_total():
    pf = _pf("securities", [{"class": "현금예금", "mv_krw_bn": 1000}],
             contingent=[{"class": "대출-부동산PF", "exposure_krw_bn": 500, "loss_beta": 1.0, "value_flag": "공시", "page_ref": "p.9"}])
    s = ci.run(pf, _sc({"kr_pf_loss_rate_pp": 2}))["scenarios"][0]
    row = [r for r in s["rows"] if r["contingent"]][0]
    assert row["key"].startswith("우발:") and row["impact_100m"] == pytest.approx(-100.0)   # 500십억 × 2% = 10십억
    assert s["total_100m"] == pytest.approx(-100.0)


def test_asset_manager_aum_fee_impact():
    """AUM 주식형 10조(1만 십억), KOSPI −10%, 보수 40bp → AUM −1조, 연 보수 −40억."""
    pf = _pf("asset_manager", [{"class": "현금예금", "mv_krw_bn": 100}],
             aum=[{"class": "주식", "region": "KR", "currency": "KRW", "aum_krw_bn": 10000, "fee_bp": 40, "beta": 1.0,
                   "value_flag": "공시", "page_ref": "p.3"}])
    s = ci.run(pf, _sc({"equity_kospi_pct": -10}))["scenarios"][0]
    a = s["aum_fee"]
    assert a["rows"][0]["aum_chg_100m"] == pytest.approx(-10000.0)
    assert a["total_fee_impact_100m"] == pytest.approx(-40.0)
    assert s["total_100m"] == pytest.approx(0.0)   # AUM은 대차대조표 합계에 넣지 않음


def test_calibration_against_disclosed_sensitivity():
    """채권 10조(D=10) +50bp → 엔진 −0.5조 = −5,000억; 공시 −0.49조와 비율 약 1.02."""
    pf = _pf("insurer", [{"class": "국공채", "mv_krw_bn": 10000, "mod_duration": 10}],
             rate_sensitivity_disclosed=[{"shock_bp": 50, "asset_chg_krw_bn": -490, "liab_chg_krw_bn": -450,
                                          "value_flag": "공시", "page_ref": "p.10"}])
    pf["liabilities"] = {"duration": 9.0, "pv_krw_bn": 10000, "value_flag": "추정", "page_ref": "p.10"}
    c = ci.run(pf, _sc(KR))["calibration"][0]
    assert c["model_asset_kr_100m"] == pytest.approx(-5000.0)
    assert c["ratio_model_kr_to_disclosed"] == pytest.approx(500 / 490, abs=1e-3)
    assert c["model_liab_100m"] == pytest.approx(-4500.0)


def test_constraints_entity_override():
    cons = load_yaml(CONFIG_DIR / "constraints.yaml")
    pf = _pf("securities", [{"class": "현금예금", "mv_krw_bn": 3}, {"class": "주식", "mv_krw_bn": 97}])
    res = {c["name"]: c for c in ci.check_constraints(pf, cons, {"duration_gap_years": -5})}
    assert "듀레이션 갭(년)" not in res            # 증권사는 갭 한도 없음
    assert res["현금성 최소"]["ok"] is False and res["주식 합계"]["ok"] is False


def test_render_entity_sections():
    import check_report as cr
    import render_portfolio as rp

    pf = _pf("securities", [{"class": "국공채", "mv_krw_bn": 1000, "mod_duration": 2.0}],
             contingent=[{"class": "대출-부동산PF", "exposure_krw_bn": 300, "value_flag": "공시", "page_ref": "p.9"}],
             capital_ratios=[{"name": "NCR", "value": 1500, "unit": "%", "value_flag": "공시", "page_ref": "p.3"}],
             rate_sensitivity_disclosed=[{"shock_bp": 50, "asset_chg_krw_bn": -10, "value_flag": "공시", "page_ref": "p.4"}])
    r = ci.run(pf, {"as_of": "2026-10-25", "scenarios": [{"name": "장기-Bear", "prob": 1.0,
                                                          "shocks": {**KR, "kr_pf_loss_rate_pp": 1}}]})
    md = rp.render(r, [pf], "2026-10-25")
    for h in ("## 자본비율", "## 공시 금리 민감도 vs 엔진", "## 조달·유동성", "업종: 증권사"):
        assert h in md
    assert "| 우발:대출-부동산PF |" in md
    assert cr.check_portfolio(md, r)[0] == []


def test_disclosed_alm_and_calibrated_total():
    """공시 +50bp 가용자본 −110십억 → Δy +10bp면 −22십억(−220억); 공시 보정 합계 = 금리요인 × 1/비율."""
    pf = _pf("insurer", [{"class": "국공채", "mv_krw_bn": 10000, "mod_duration": 10}],
             rate_sensitivity_disclosed=[
                 {"shock_bp": 50, "asset_chg_krw_bn": -625, "liab_chg_krw_bn": -515, "capital_chg_krw_bn": -110,
                  "ratio_name": "K-ICS", "ratio_chg_pp": 0.7, "value_flag": "공시", "page_ref": "p.10"},
                 {"shock_bp": -50, "asset_chg_krw_bn": 625, "liab_chg_krw_bn": 515, "capital_chg_krw_bn": 80,
                  "ratio_chg_pp": 0.3, "value_flag": "공시", "page_ref": "p.10"}])
    pf["liabilities"] = {"duration": 10.0, "pv_krw_bn": 10300, "value_flag": "공시", "page_ref": "p.10"}
    r = ci.run(pf, _sc({"ktb_3y_bp": 10, "ktb_10y_bp": 10, "ktb_30y_bp": 10}))
    s = r["scenarios"][0]
    assert s["alm"]["disclosed_capital_100m"] == pytest.approx(-220.0)
    assert s["alm"]["disclosed_ratio_pp"] == pytest.approx(0.14)
    # 엔진 +50bp = −500십억, 공시 −625 → 비율 0.8 → 보정 계수 1.25; 시나리오 금리요인 −100십억(−1,000억) → 보정 −1,250억
    assert r["calibration"][0]["ratio_model_kr_fx_to_disclosed"] == pytest.approx(0.8)
    assert s["calibrated"]["total_100m"] == pytest.approx(-1250.0)
