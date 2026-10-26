"""optimize_allocation LP 제약 검증. 포트폴리오·수익률은 가상 데이터(실제 회사 아님)."""
import pytest

pytest.importorskip("scipy")
import optimize_allocation as oa


def _setup(alt_cap=0.12, kics_floor=1.5, bear_extra_bp=1000):
    pf = {"total_invested_assets_krw_bn": 1000.0, "capital_ratios": [{"name": "K-ICS", "value": 200.0}],
          "assets": [{"class": "현금예금", "mv_krw_bn": 100.0}, {"class": "국공채", "mv_krw_bn": 800.0},
                     {"class": "대체-사모대출", "mv_krw_bn": 100.0}]}
    rets = {"현금예금": {"total_pct": 3.0, "carry_net_pct": 3.0, "charge": [0.0, 0.0], "duration": 0.0, "bear_pct": 0.0},
            "국공채": {"total_pct": 3.5, "carry_net_pct": 4.0, "charge": [0.0, 0.0], "duration": 10.0, "bear_pct": -5.0},
            "대체-사모대출": {"total_pct": 6.0, "carry_net_pct": 6.0, "charge": [0.1, 0.2], "duration": 1.0, "bear_pct": -2.0}}
    cfg = {"fixed_classes": [], "alt_classes": ["대체-사모대출"], "diversification": 1.0,
           "kics_capital_fallback": {"available_trn": 0.2, "required_trn": 0.1, "source": "가상"}}
    strat = {"step_pp": 10.0, "cash_min": 0.05, "alt_cap": alt_cap, "kics_floor": kics_floor,
             "bear_extra_bp": bear_extra_bp, "gap_range": [-1, 1]}
    return pf, rets, cfg, strat


def test_alt_cap_and_cash_floor_bind():
    pf, rets, cfg, strat = _setup()
    o = oa.optimize(pf, rets, cfg, strat)
    assert o["status"] == "ok"
    # 대체 상한 12% → 사모대출 +20. 현금은 하한 5%까지 빠져 나머지는 국공채(3.5% > 3.0%)로
    assert o["deltas_krw_bn"]["대체-사모대출"] == pytest.approx(20.0, abs=0.2)
    assert o["deltas_krw_bn"]["현금예금"] == pytest.approx(-50.0, abs=0.2)
    assert o["deltas_krw_bn"]["국공채"] == pytest.approx(30.0, abs=0.2)
    assert o["delta_total_return_bp"] == pytest.approx((20 * 0.03 + 30 * 0.005) / 1000 * 1e4, abs=0.2)
    assert o["kics_now"] == pytest.approx(200.0)


def test_kics_floor_binds_with_high_charge():
    pf, rets, cfg, strat = _setup(alt_cap=0.5, kics_floor=1.9)
    o = oa.optimize(pf, rets, cfg, strat)
    # 가용 200 / 1.9 − 요구 100 = 5.26 → 사모대출 증가 ≤ 5.26 / 0.2 = 26.3
    assert o["deltas_krw_bn"]["대체-사모대출"] == pytest.approx(26.3, abs=0.2)
    assert o["kics_after"]["high"] == pytest.approx(190.0, abs=0.1)


def test_cash_floor_not_forced_and_strategic_excluded():
    pf, rets, cfg, strat = _setup(alt_cap=0.5)
    # 현금 3%로 하한(5%) 미만, 전략적 주식 500(비중 33%)은 매매 제외
    pf["assets"][0]["mv_krw_bn"] = 30.0
    pf["assets"].append({"class": "주식", "mv_krw_bn": 500.0, "strategic": True})
    pf["total_invested_assets_krw_bn"] = 1430.0
    rets["주식"] = {"total_pct": 9.0, "carry_net_pct": 9.0, "charge": [0.35, 0.35], "duration": 0.0, "bear_pct": -20.0}
    o = oa.optimize(pf, rets, cfg, strat)
    assert o["status"] == "ok"
    assert o["deltas_krw_bn"].get("현금예금", 0.0) >= -0.1          # 하한 미만이면 줄이지도, 억지로 늘리지도 않음
    assert o["deltas_krw_bn"].get("현금예금", 0.0) <= 0.1
    # 주식 합계가 constraints.yaml 한도(10%)를 이미 넘어 추가 매수 금지
    assert o["deltas_krw_bn"].get("주식", 0.0) <= 0.1


def test_rate_down_hurts_blocks_duration_cut():
    pf, rets, cfg, strat = _setup(alt_cap=0.5)
    pf["rate_sensitivity_disclosed"] = [{"shock_bp": -50, "capital_chg_krw_bn": -10.0}]
    assert oa.rate_down_hurts(pf)
    free = oa.optimize(_setup(alt_cap=0.5)[0], rets, cfg, strat)   # 민감도 공시 없음 → 제약 없음
    d_free = sum(v * rets[c]["duration"] for c, v in free["deltas_krw_bn"].items())
    o = oa.optimize(pf, rets, cfg, strat)
    dur = sum(v * rets[c]["duration"] for c, v in o["deltas_krw_bn"].items())
    assert d_free < -100       # 제약이 없으면 국공채를 줄여 듀레이션이 크게 짧아짐
    assert dur >= -1.0         # 제약이 있으면 줄이지 않음(0.1 반올림 오차 허용)
