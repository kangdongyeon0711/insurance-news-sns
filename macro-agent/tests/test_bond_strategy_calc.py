"""bond_strategy_calc 업종별 헤지 크레딧 계산 검증(지속 시 손익 = 캐리 − 충격 × 스프레드 듀레이션)."""
import json

import pytest

import bond_strategy_calc as bsc


def test_sector_hedged_rows(tmp_path):
    out = tmp_path / "calc.json"
    assert bsc.main(["--date", "2026-10-27", "--out", str(out)]) == 0
    rows = json.loads(out.read_text())["sector_hedged_1y"]["rows"]
    assert len(rows) == len(bsc.SECTOR_STRESS)
    sd = bsc.DUR[3] - 0.9
    for r in rows:
        assert r["stress_1y_bp"] == pytest.approx(r["carry_roll_1y_bp"] - r["stress_spread_bp"] * sd, abs=0.11)
        assert r["downgrade_1notch_loss_bp"] > 0
    # 여전채 AA− → A+ 등급 절벽은 회사채 AA− → A+보다 크다
    by = {r["proxy_curve"]: r for r in rows}
    assert by["여전채AA-"]["downgrade_1notch_loss_bp"] > 1.8 * by["회사채AA-"]["downgrade_1notch_loss_bp"]
