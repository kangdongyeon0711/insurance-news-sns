"""FRED 시계열 수집.

사용:
  python scripts/fetch_fred.py            # series.yaml의 source: fred 항목 수집
  python scripts/fetch_fred.py --verify   # fred/series 메타데이터로 코드 존재·주기 확인 후 verified 갱신
"""
from __future__ import annotations

import argparse
import sys

from common import (CONFIG_DIR, RAW_DIR, MissingApiKey, get_logger, http_get, iso, load_series_config,
                    load_yaml, require_key, save_json, set_verified, write_series_csv, years_ago)

BASE = "https://api.stlouisfed.org/fred"
log = get_logger("fred")
FREQ = {"D": "Daily", "W": "Weekly", "M": "Monthly"}


def fetch_series(key: str, spec: dict, years: int) -> list[tuple[str, float]]:
    params = {"series_id": spec["code"], "api_key": key, "file_type": "json",
              "observation_start": iso(years_ago(years))}
    payload = http_get(f"{BASE}/series/observations", params=params, logger=log).json()
    save_json(RAW_DIR / "fred" / f"{spec['series_id']}.json", payload)
    return [(o["date"], float(o["value"])) for o in payload.get("observations", []) if o["value"] not in (".", "")]


def verify(key: str, specs: list[dict]) -> int:
    bad = 0
    for s in specs:
        try:
            payload = http_get(f"{BASE}/series", params={"series_id": s["code"], "api_key": key,
                                                         "file_type": "json"}, logger=log).json()
            meta = (payload.get("seriess") or [{}])[0]
            ok = meta.get("id") == s["code"] and meta.get("frequency", "").startswith(FREQ.get(s["cycle"], "?"))
            log.info("%-16s %s: %s (%s, %s) → %s", s["series_id"], s["code"], meta.get("title"),
                     meta.get("frequency"), meta.get("units"), "확인" if ok else "불일치")
        except Exception as e:  # noqa: BLE001
            ok = False
            log.error("%s 메타데이터 조회 실패: %s", s["code"], e)
        set_verified(s["series_id"], ok)
        bad += 0 if ok else 1
    return bad


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args(argv)
    specs = [s for s in load_series_config() if s["source"] == "fred"]
    try:
        key = require_key("FRED_API_KEY")
    except MissingApiKey as e:
        log.error(str(e))
        return 2
    if args.verify:
        return 1 if verify(key, specs) else 0
    years = load_yaml(CONFIG_DIR / "series.yaml").get("lookback_years", 10)
    failed = 0
    for s in specs:
        try:
            rows = fetch_series(key, s, years)
            write_series_csv(s["series_id"], rows)
            log.info("%s: %d건 (마지막 %s)", s["series_id"], len(rows), rows[-1][0] if rows else "없음")
        except Exception as e:  # noqa: BLE001
            failed += 1
            log.error("%s 수집 실패: %s", s["series_id"], e)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
