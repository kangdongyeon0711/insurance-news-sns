"""EIA 주간 원유 재고 (선택). EIA_API_KEY가 없으면 경고 후 건너뛴다(종료코드 2 = 키 없음, 오류 아님)."""
from __future__ import annotations

import sys

from common import (RAW_DIR, MissingApiKey, get_logger, http_get, iso, load_series_config, require_key,
                    save_json, set_verified, write_series_csv, years_ago)

log = get_logger("eia")


def fetch_series(key: str, spec: dict, years: int = 10) -> list[tuple[str, float]]:
    # v2의 하위호환 엔드포인트: /v2/seriesid/{v1 series id}
    url = f"https://api.eia.gov/v2/seriesid/{spec['code']}"
    payload = http_get(url, params={"api_key": key, "start": iso(years_ago(years))}, logger=log).json()
    save_json(RAW_DIR / "eia" / f"{spec['series_id']}.json", payload)
    data = payload.get("response", {}).get("data", [])
    return [(str(d["period"])[:10], float(d["value"])) for d in data if d.get("value") is not None]


def main() -> int:
    specs = [s for s in load_series_config() if s["source"] == "eia"]
    try:
        key = require_key("EIA_API_KEY")
    except MissingApiKey:
        log.warning("EIA_API_KEY 없음 → EIA 수집 건너뜀 (선택 항목)")
        return 2
    failed = 0
    for s in specs:
        try:
            rows = fetch_series(key, s)
            write_series_csv(s["series_id"], rows)
            set_verified(s["series_id"], bool(rows))
            log.info("%s: %d건", s["series_id"], len(rows))
        except Exception as e:  # noqa: BLE001
            failed += 1
            log.error("%s 수집 실패: %s", s["series_id"], e)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
