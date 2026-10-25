"""ECOS '100대 통계지표' 엑셀(사용자가 ECOS 홈페이지에서 직접 내려받은 파일) → data/manual/ 수기 입력 YAML.

python scripts/import_ecos100.py <xlsx> [--date 2026-10-25]

- 원본 엑셀은 data/manual/ecos100_{YYYYMMDD}.xlsx로 복사해 보관하고, 값은 ecos100_{YYYYMMDD}.yaml로 저장한다.
- 열: 분류 | 100대통계명 | 시점 | ECOS값 | 단위. 시점은 YYYYMMDD(일), YYYYMM(월말), YYYYQn(분기말), YYYY(연말)로 해석.
- MAP에 있는 지표는 series_id·topic_id를 붙이고, 없는 지표는 ecos100_{번호}로 원래 이름을 보존한다.
- 진행 중인 기간(예: 시점 202610을 10-25에 받음)은 기간 말일 대신 자료 기준일을 as_of로 쓰고 note에 표시.
- priority: 1 → 같은 series_id·같은 날짜가 다른 수기 파일과 겹치면 이 파일 값을 쓴다(엑셀이 더 정밀).
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import pandas as pd
import yaml

from common import DATA_DIR, get_logger, today

log = get_logger("ecos100")

# 100대통계명 → (series_id, topic_id, 변환계수, 변환 후 단위). 계수 None = 원래 값·단위 유지
MAP: dict[str, tuple[str, str | None, float | None, str | None]] = {
    "한국은행 기준금리": ("kr_base_rate", "kr_rate", None, None),
    "콜금리(익일물)": ("kr_call_1d", "kr_rate", None, None),
    "KORIBOR(3개월)": ("kr_koribor_3m", "kr_rate", None, None),
    "CD수익률(91일)": ("kr_cd_91d", "kr_rate", None, None),
    "통안증권수익률(364일)": ("kr_msb_364d", "kr_rate", None, None),
    "국고채수익률(3년)": ("ktb_3y", "kr_govt_bond", None, None),
    "국고채수익률(5년)": ("ktb_5y", "kr_govt_bond", None, None),
    "회사채수익률(3년,AA-)": ("kr_corp_aa_3y", "kr_corp_bond", None, None),
    "예금은행 수신금리": ("kr_deposit_rate", "kr_rate", None, None),
    "예금은행 대출금리": ("kr_loan_rate", "kr_rate", None, None),
    "가계신용": ("kr_household_credit", "kr_rate", None, None),
    "가계대출연체율": ("kr_household_delinquency", "kr_rate", None, None),
    "M1(협의통화, 평잔)": ("kr_m1", "kr_rate", None, None),
    "M2(광의통화, 평잔)": ("kr_m2", "kr_rate", None, None),
    "Lf(평잔)": ("kr_lf", "kr_rate", None, None),
    "L(말잔)": ("kr_l", "kr_rate", None, None),
    "원/달러 환율(종가)": ("krw_usd_close", "fx_krwusd", None, None),
    "원/엔(100엔) 환율(매매기준율)": ("krw_jpy100", "fx_krwusd", None, None),
    "원/유로 환율(매매기준율)": ("krw_eur", "fx_krwusd", None, None),
    "원/위안 환율(종가)": ("krw_cny", "fx_krwusd", None, None),
    "코스피지수": ("kospi", None, None, None),
    "코스닥지수": ("kosdaq", None, None, None),
    "채권거래대금": ("kr_bond_trading_value", "kr_govt_bond", None, None),
    "국고채발행액": ("ktb_issuance", "kr_govt_bond", None, None),
    "경제성장률(실질, 계절조정 전기대비)": ("kr_gdp_qoq", "kr_rate", None, None),
    "민간소비증감률(실질, 계절조정 전기대비)": ("kr_consumption_qoq", "kr_rate", None, None),
    "설비투자증감률(실질, 계절조정 전기대비)": ("kr_capex_qoq", "kr_rate", None, None),
    "건설투자증감률(실질, 계절조정 전기대비)": ("kr_construction_qoq", "kr_alt_re", None, None),
    "재화의 수출 증감률(실질, 계절조정 전기대비)": ("kr_goods_export_qoq", "fx_krwusd", None, None),
    "동행지수순환변동치": ("kr_coincident_cycle", "kr_rate", None, None),
    "선행지수순환변동치": ("kr_leading_cycle", "kr_rate", None, None),
    "소비자심리지수": ("kr_csi", "kr_rate", None, None),
    "실업률": ("kr_unemployment", "kr_rate", None, None),
    "고용률": ("kr_employment_rate", "kr_rate", None, None),
    "경상수지": ("kr_current_account", "fx_krwusd", 0.001, "십억USD"),
    "직접투자(자산)": ("kr_fdi_assets", "fx_krwusd", None, None),
    "직접투자(부채)": ("kr_fdi_liabilities", "fx_krwusd", None, None),
    "증권투자(자산)": ("kr_portfolio_inv_assets", "fx_krwusd", None, None),
    "증권투자(부채)": ("kr_portfolio_inv_liabilities", "fx_krwusd", None, None),
    "외환보유액": ("kr_fx_reserves", "fx_krwusd", 1e-6, "십억USD"),
    "대외채무": ("kr_external_debt", "fx_krwusd", None, None),
    "대외채권": ("kr_external_assets", "fx_krwusd", None, None),
    "수출금액지수": ("kr_export_value_index", "fx_krwusd", None, None),
    "수입금액지수": ("kr_import_value_index", "fx_krwusd", None, None),
    "순상품교역조건지수": ("kr_terms_of_trade", "fx_krwusd", None, None),
    "소비자물가지수": ("kr_cpi", "kr_rate", None, None),
    "농산물 및 석유류제외 소비자물가지수": ("kr_core_cpi", "kr_rate", None, None),
    "생활물가지수": ("kr_living_cpi", "kr_rate", None, None),
    "생산자물가지수": ("kr_ppi", "kr_rate", None, None),
    "수출물가지수": ("kr_export_price", "fx_krwusd", None, None),
    "수입물가지수": ("kr_import_price", "oil", None, None),
    "주택매매가격지수": ("kr_house_price", "kr_alt_re", None, None),
    "주택전세가격지수": ("kr_jeonse_price", "kr_alt_re", None, None),
    "지가변동률(전기대비)": ("kr_land_price_chg", "kr_alt_re", None, None),
    "건설기성액": ("kr_construction_completed", "kr_alt_re", None, None),
    "건설수주액": ("kr_construction_orders", "kr_alt_re", None, None),
    "건축허가면적": ("kr_building_permits", "kr_alt_re", None, None),
    "건축착공면적": ("kr_building_starts", "kr_alt_re", None, None),
    "Dubai유(현물)": ("dubai", "oil", None, None),
    "금": ("gold", None, None, None),
}


def parse_period(p: str) -> tuple[str, str]:
    """시점 문자열 → (as_of YYYY-MM-DD, cycle)."""
    p = str(p).strip()
    if len(p) == 8 and p.isdigit():
        return f"{p[:4]}-{p[4:6]}-{p[6:]}", "D"
    if len(p) == 6 and p.isdigit():
        return (pd.Timestamp(f"{p[:4]}-{p[4:]}-01") + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d"), "M"
    if len(p) == 6 and p[4] == "Q":
        q = int(p[5])
        return (pd.Timestamp(f"{p[:4]}-{q * 3:02d}-01") + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d"), "Q"
    if len(p) == 4 and p.isdigit():
        return f"{p}-12-31", "A"
    raise ValueError(f"시점 해석 불가: {p}")


def convert(xlsx: Path, retrieved: str) -> dict:
    df = pd.read_excel(xlsx, dtype={"시점": str})
    need = ["분류", "100대통계명", "시점", "ECOS값", "단위"]
    if list(df.columns[:5]) != need:
        raise ValueError(f"예상 열 {need}, 실제 {list(df.columns)}")
    points = []
    for i, r in df.iterrows():
        name = str(r["100대통계명"]).strip()
        as_of, cycle = parse_period(r["시점"])
        partial = as_of > retrieved   # 진행 중인 기간(예: 이번 달 누적) → 기준일을 자료 기준일로
        if partial:
            as_of = retrieved
        unit = None if pd.isna(r["단위"]) else str(r["단위"]).strip()
        sid, topic, factor, new_unit = MAP.get(name, (f"ecos100_{i + 1:03d}", None, None, None))
        value = float(r["ECOS값"])
        pt = {"series_id": sid, "value": round(value * factor, 6) if factor else value, "as_of": as_of,
              "period_label": str(r["시점"]), "raw_label": f"{r['분류']} / {name}",
              "meta": {"name": name, "unit": new_unit or unit or "", "cycle": cycle,
                       "chg_type": "diff" if unit == "%" else "pct", "topic_id": topic}}
        notes = []
        if factor:
            notes.append(f"원자료 {value:g} {unit} → {new_unit}로 환산")
        if partial:
            notes.append(f"{r['시점']} 진행 중 기간 값(누적·추계 등) — 기준일을 자료 기준일 {retrieved}로 둠")
        if notes:
            pt["note"] = "; ".join(notes)
        points.append(pt)
    return {"source": "ECOS 100대 통계지표 엑셀 (사용자가 ECOS 홈페이지에서 직접 내려받음)",
            "retrieved": retrieved, "priority": 1, "raw_file": None, "points": points}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx")
    ap.add_argument("--date", default=today().isoformat(), help="자료 기준일(내려받은 날)")
    args = ap.parse_args(argv)
    tag = args.date.replace("-", "")
    mdir = DATA_DIR / "manual"
    mdir.mkdir(parents=True, exist_ok=True)
    out_yaml, out_xlsx = mdir / f"ecos100_{tag}.yaml", mdir / f"ecos100_{tag}.xlsx"
    if out_yaml.exists():
        print(f"이미 존재: {out_yaml} — 덮어쓰기 전에 확인 필요")
        return 1
    doc = convert(Path(args.xlsx), args.date)
    shutil.copy(args.xlsx, out_xlsx)
    doc["raw_file"] = f"data/manual/{out_xlsx.name}"
    header = (f"# ECOS 100대 통계지표 — {args.date} 기준, scripts/import_ecos100.py로 변환 (원본: {doc['raw_file']})\n"
              "# 수기 입력 데이터: fetch_all.py가 API 시계열과 병합(같은 날짜는 API 우선). priority 1 = 다른 수기 파일보다 우선.\n")
    out_yaml.write_text(header + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")
    mapped = sum(1 for p in doc["points"] if not p["series_id"].startswith("ecos100_"))
    print(f"저장: {out_yaml} ({len(doc['points'])}개, series_id 매핑 {mapped}개), 원본 사본: {out_xlsx}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
