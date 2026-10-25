"""OpenDART: 보험사 정기공시 목록 + 주요 재무계정 조회.

공시 PDF를 자동 다운로드하지 않는다(원칙 2: 사용자가 직접 받아 inbox/filings/에 넣는다).
이 스크립트는 '어떤 공시가 새로 나왔는지'와 재무제표 주요 계정(총자산 등, 익스포저 교차검증용)만 가져온다.

출력: data/raw/dart/*.json, data/dart_filings.json
"""
from __future__ import annotations

import io
import sys
import xml.etree.ElementTree as ET
import zipfile
from datetime import timedelta

from common import (CONFIG_DIR, DATA_DIR, RAW_DIR, MissingApiKey, get_logger, http_get, load_json,
                    load_yaml, require_key, save_json, today)

BASE = "https://opendart.fss.or.kr/api"
log = get_logger("dart")
REPRT = {"11013": "1분기", "11012": "반기", "11014": "3분기", "11011": "사업"}


def corp_codes(key: str) -> dict[str, dict]:
    cache = RAW_DIR / "dart" / "corp_codes.json"
    if cache.exists():
        return load_json(cache)
    resp = http_get(f"{BASE}/corpCode.xml", params={"crtfc_key": key}, logger=log, timeout=60)
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        root = ET.fromstring(zf.read(zf.namelist()[0]))
    out = {}
    for el in root.iter("list"):
        sc = (el.findtext("stock_code") or "").strip()
        if sc:
            out[sc] = {"corp_code": el.findtext("corp_code"), "corp_name": el.findtext("corp_name")}
    save_json(cache, out)
    return out


def filings(key: str, corp_code: str, days: int, types: list[str]) -> list[dict]:
    end, bgn = today(), today() - timedelta(days=days)
    rows: list[dict] = []
    for ty in types:
        p = {"crtfc_key": key, "corp_code": corp_code, "bgn_de": bgn.strftime("%Y%m%d"),
             "end_de": end.strftime("%Y%m%d"), "pblntf_detail_ty": ty, "page_count": 100}
        payload = http_get(f"{BASE}/list.json", params=p, logger=log).json()
        if payload.get("status") not in ("000", "013"):  # 013 = 데이터 없음
            raise RuntimeError(f"DART 오류 {payload.get('status')}: {payload.get('message')}")
        for r in payload.get("list", []):
            rows.append({"rcept_dt": r["rcept_dt"], "report_nm": r["report_nm"].strip(),
                         "rcept_no": r["rcept_no"],
                         "viewer_url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={r['rcept_no']}"})
    return sorted(rows, key=lambda r: r["rcept_dt"], reverse=True)


def key_accounts(key: str, corp_code: str, year: int, reprt_code: str) -> list[dict]:
    p = {"crtfc_key": key, "corp_code": corp_code, "bsns_year": str(year), "reprt_code": reprt_code}
    payload = http_get(f"{BASE}/fnlttSinglAcnt.json", params=p, logger=log).json()
    if payload.get("status") != "000":
        return []
    keep = ("자산총계", "부채총계", "자본총계", "당기순이익")
    return [{"fs_div": r.get("fs_div"), "account_nm": r["account_nm"], "thstrm_amount": r.get("thstrm_amount"),
             "thstrm_nm": r.get("thstrm_nm")} for r in payload.get("list", []) if r.get("account_nm") in keep]


def main() -> int:
    cfg = load_yaml(CONFIG_DIR / "series.yaml")["dart"]
    try:
        key = require_key("DART_API_KEY")
    except MissingApiKey as e:
        log.error(str(e))
        return 2
    codes = corp_codes(key)
    result = {"as_of": today().isoformat(), "companies": []}
    for c in cfg["companies"]:
        info = codes.get(c["stock_code"])
        if not info:
            log.error("%s(%s) corp_code 미확인", c["name"], c["stock_code"])
            continue
        try:
            fl = filings(key, info["corp_code"], cfg.get("lookback_days", 400), cfg["pblntf_detail_ty"])
            # 가장 최근 정기보고서 기준 주요 계정
            accts: list[dict] = []
            for y in (today().year, today().year - 1):
                for rc in ("11014", "11012", "11013", "11011"):
                    accts = key_accounts(key, info["corp_code"], y, rc)
                    if accts:
                        accts = [{**a, "bsns_year": y, "reprt": REPRT[rc]} for a in accts]
                        break
                if accts:
                    break
            entry = {"name": c["name"], **info, "filings": fl, "key_accounts": accts}
            save_json(RAW_DIR / "dart" / f"{c['name']}.json", entry)
            result["companies"].append(entry)
            log.info("%s: 정기공시 %d건, 주요계정 %d개", c["name"], len(fl), len(accts))
        except Exception as e:  # noqa: BLE001
            log.error("%s 조회 실패: %s", c["name"], e)
    save_json(DATA_DIR / "dart_filings.json", result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
