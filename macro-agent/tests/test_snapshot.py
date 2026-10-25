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


def test_manual_points_merge(tmp_path):
    """수기 입력(data/manual/*.yaml)과 API CSV 병합: 같은 날짜는 API 우선 + 괴리 경고, 신규 시리즈·파생 계산."""
    series_dir, manual_dir = tmp_path / "series", tmp_path / "manual"
    manual_dir.mkdir(parents=True)
    _write(series_dir, "ktb_3y", "2026-10-20", [3.70, 3.75, 3.80])          # API: 10-20 ~ 10-22
    (manual_dir / "m.yaml").write_text(
        "source: test\npoints:\n"
        "  - {series_id: ktb_3y, value: 3.90, as_of: 2026-10-22}\n"        # API와 같은 날짜, 다른 값
        "  - {series_id: ktb_3y, value: 3.803, as_of: 2026-10-23}\n"       # API보다 최신
        "  - {series_id: kr_corp_aa_3y, value: 4.492, as_of: 2026-10-23}\n"
        "  - {series_id: kospi, value: 5550.3, as_of: 2026-10-23,\n"
        "     meta: {name: KOSPI, unit: pt, cycle: D, chg_type: pct, topic_id: null}}\n", encoding="utf-8")
    snap = fetch_all.build_snapshot(series_dir, date(2026, 10, 25), manual_dir=manual_dir)
    s = snap["series"]
    assert s["ktb_3y"]["last_value"] == 3.803 and s["ktb_3y"]["source_type"] == "manual"
    assert s["ktb_3y"]["value_flag"] == "수기" and s["ktb_3y"]["manual"]["source"] == "test"
    assert any("ktb_3y" in w and "괴리" in w for w in snap["warnings"])
    merged = read_series_csv("ktb_3y", series_dir)   # API CSV 자체는 수기값으로 덮어쓰지 않음
    assert merged.iloc[-1] == 3.80
    assert s["kr_aa_spread"]["last_value_bp"] == 68.9 and s["kr_aa_spread"]["value_flag"] == "수기"
    assert s["kospi"]["last_value"] == 5550.3 and s["kospi"]["topic_id"] is None


def test_manual_priority_and_ecos100_convert(tmp_path):
    import openpyxl

    import import_ecos100 as ie

    mdir = tmp_path / "manual"
    mdir.mkdir()
    (mdir / "a.yaml").write_text("points:\n  - {series_id: kr_current_account, value: 46.1, as_of: 2026-08-31}\n", encoding="utf-8")
    (mdir / "b.yaml").write_text("priority: 1\npoints:\n  - {series_id: kr_current_account, value: 46.113, as_of: 2026-08-31}\n",
                                 encoding="utf-8")
    snap = fetch_all.build_snapshot(tmp_path / "series", date(2026, 10, 25), manual_dir=mdir)
    assert snap["series"]["kr_current_account"]["last_value"] == 46.113
    # 엑셀 변환: 시점 해석·매핑·단위 환산
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in [("분류", "100대통계명", "시점", "ECOS값", "단위"), ("시장금리", "국고채수익률(3년)", "20261023", 3.803, "%"),
                ("국제수지", "경상수지", "202608", 46113.0, "백만달러"), ("성장률", "GDP(명목, 계절조정)", "2026Q2", 1.0, "십억원"),
                ("인구", "합계출산율", "2025", 0.799, "명"), ("채권", "채권거래대금", "202610", 81.0, "조원")]:
        ws.append(row)
    x = tmp_path / "e.xlsx"
    wb.save(x)
    pts = {p["series_id"]: p for p in ie.convert(x, "2026-10-25")["points"]}
    assert pts["ktb_3y"]["as_of"] == "2026-10-23" and pts["ktb_3y"]["meta"]["chg_type"] == "diff"
    assert pts["kr_current_account"]["value"] == 46.113 and pts["kr_current_account"]["meta"]["unit"] == "십억USD"
    assert pts["ecos100_003"]["as_of"] == "2026-06-30" and pts["ecos100_003"]["meta"]["cycle"] == "Q"
    assert pts["ecos100_004"]["as_of"] == "2025-12-31"
    assert pts["kr_bond_trading_value"]["as_of"] == "2026-10-25" and "진행 중" in pts["kr_bond_trading_value"]["note"]
