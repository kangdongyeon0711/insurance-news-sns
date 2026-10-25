"""fetch_all.build_snapshot: 합성 시계열(가상 데이터)로 변화량·파생지표·stale 계산 검증."""
from datetime import date

import pandas as pd

import fetch_all
from common import read_series_csv, set_verified, write_series_csv


def _write(dirp, sid, start, values, freq="D"):
    idx = pd.date_range(start, periods=len(values), freq=freq)
    write_series_csv(sid, [(d.strftime("%Y-%m-%d"), v) for d, v in zip(idx, values)], dirp)


def test_snapshot_changes_and_derived(tmp_path):
    n = 400
    _write(tmp_path, "ktb_3y", "2025-09-21", [3.0] * (n - 7) + [3.1] * 7)
    _write(tmp_path, "ktb_10y", "2025-09-21", [3.5] * n)
    _write(tmp_path, "krw_usd", "2025-09-21", [1300.0] * (n - 7) + [1365.0] * 7)
    ref = date(2026, 10, 25)
    snap = fetch_all.build_snapshot(tmp_path, ref)
    s = snap["series"]
    last = pd.Timestamp("2025-09-21") + pd.Timedelta(days=n - 1)
    assert s["ktb_3y"]["as_of"] == last.strftime("%Y-%m-%d")
    assert s["ktb_3y"]["chg_1m"] == 10.0          # +0.10%p = +10bp
    assert s["krw_usd"]["chg_1m"] == 5.0          # +5%
    assert s["ktb_10y_3y"]["last_value_bp"] == 40.0
    assert s["ktb_10y_3y"]["formula"] == "ktb_10y - ktb_3y"
    assert s["ktb_3y"]["stale"] is False
    assert "ust_10y" not in s and any("ust_10y" in w for w in snap["warnings"])


def test_stale_flag(tmp_path):
    _write(tmp_path, "ust_10y", "2026-09-01", [4.0] * 10)
    snap = fetch_all.build_snapshot(tmp_path, date(2026, 10, 25))
    assert snap["series"]["ust_10y"]["stale"] is True
    assert any("오래된 데이터" in w for w in snap["warnings"])


def test_set_verified_preserves_comments(tmp_path):
    p = tmp_path / "series.yaml"
    p.write_text("# c\nseries:\n  - series_id: a\n    verified: false  # keep\n"
                 "  - {series_id: b, code: X, verified: false}\n", encoding="utf-8")
    assert set_verified("b", True, p)
    assert set_verified("a", True, p)
    txt = p.read_text(encoding="utf-8")
    assert "verified: true  # keep" in txt and "{series_id: b, code: X, verified: true}" in txt and txt.startswith("# c")


def test_csv_roundtrip(tmp_path):
    write_series_csv("x", [("2026-01-02", 1.5), ("2026-01-01", 1.0), ("2026-01-02", 2.0)], tmp_path)
    s = read_series_csv("x", tmp_path)
    assert list(s.values) == [1.0, 2.0]
