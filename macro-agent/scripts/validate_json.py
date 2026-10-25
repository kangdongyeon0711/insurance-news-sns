"""JSON 스키마 + 의미 검증.

사용:
  python scripts/validate_json.py knowledge/view_cards/                 # 폴더 내 *.json 전부
  python scripts/validate_json.py knowledge/macro_topics/2026-10-25/     # macro_topic 16개
  python scripts/validate_json.py file.json --type factor_shocks

유형은 경로로 추론한다(view_cards→view_card, macro_topics→macro_topic, portfolios→exposures,
*shocks*.json→factor_shocks). 오류가 하나라도 있으면 종료코드 1.

의미 검사:
  - macro_topic: 시나리오 확률 합 = 1(±0.001), Base/Bull/Bear 각 1개, factor 이름 ∈ factors.yaml,
    indicators의 value/as_of가 latest_snapshot.json과 일치(value_flag가 API 또는 수기인 경우)
  - view_card: views의 topic_id ⊆ topics, card_id = source_file 파일명
  - factor_shocks: factor 이름 ∈ factors.yaml, prob가 있으면 합 = 1
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from common import CONFIG_DIR, SCHEMA_DIR, SNAPSHOT_PATH, TOPIC_IDS, load_json, load_yaml

TYPES = {"view_card": "view_card.schema.json", "macro_topic": "macro_topic.schema.json",
         "exposures": "exposures.schema.json", "factor_shocks": "factor_shocks.schema.json"}


def _registry() -> Registry:
    reg = Registry()
    for p in SCHEMA_DIR.glob("*.schema.json"):
        reg = reg.with_resource(p.name, Resource.from_contents(load_json(p)))
    return reg


def factor_names() -> set[str]:
    return set(load_yaml(CONFIG_DIR / "factors.yaml")["factors"])


def infer_type(path: Path) -> str | None:
    parts = set(path.parts)
    if "view_cards" in parts:
        return "view_card"
    if "macro_topics" in parts:
        return "macro_topic"
    if "portfolios" in parts or "exposures" in path.name:
        return "exposures"
    if "shocks" in path.name:
        return "factor_shocks"
    return None


def _check_factors(shocks: dict, where: str, names: set[str]) -> list[str]:
    return [f"{where}: 알 수 없는 factor '{k}' (config/factors.yaml에 없음)" for k in shocks if k not in names]


def semantic_errors(kind: str, doc: dict, snapshot: dict | None) -> list[str]:
    errs: list[str] = []
    names = factor_names()
    if kind == "macro_topic":
        sc = doc.get("long_term", {}).get("scenarios", [])
        total = sum(s.get("prob", 0) for s in sc)
        if abs(total - 1) > 1e-3:
            errs.append(f"시나리오 확률 합 {total:.3f} ≠ 1")
        got = sorted(s.get("name") for s in sc)
        if got != ["Base", "Bear", "Bull"]:
            errs.append(f"시나리오는 Base/Bull/Bear 각 1개여야 함: {got}")
        errs += _check_factors(doc.get("short_term_factor_shocks", {}), "short_term_factor_shocks", names)
        for s in sc:
            errs += _check_factors(s.get("factor_shocks", {}), f"scenario {s.get('name')}", names)
        if snapshot is not None:
            series = snapshot.get("series", {})
            for ind in doc.get("current", {}).get("indicators", []):
                if ind.get("value_flag", "API") not in ("API", "수기"):
                    continue
                st = series.get(ind["series_id"])
                if st is None:
                    if ind.get("value") is not None:
                        errs.append(f"indicator {ind['series_id']}: snapshot에 없는데 값이 있음 (value_flag를 '웹확인'/'추정'으로 표시하거나 null)")
                    continue
                if ind.get("value") is None or abs(ind["value"] - st["last_value"]) > 1e-6:
                    errs.append(f"indicator {ind['series_id']}: 값 {ind.get('value')} ≠ snapshot {st['last_value']}")
                if ind.get("as_of") != st["as_of"]:
                    errs.append(f"indicator {ind['series_id']}: as_of {ind.get('as_of')} ≠ snapshot {st['as_of']}")
        if not doc.get("house_views", {}).get("cards_used") or len(doc["house_views"]["cards_used"]) < 2:
            if not any("하우스 뷰 부족" in g for g in doc.get("data_gaps", [])):
                errs.append("하우스 뷰가 1곳 이하인데 data_gaps에 '하우스 뷰 부족'이 없음")
    elif kind == "view_card":
        missing = {v["topic_id"] for v in doc.get("views", [])} - set(doc.get("topics", []))
        if missing:
            errs.append(f"views의 topic_id가 topics에 없음: {sorted(missing)}")
        stem = Path(doc.get("source_file", "")).stem
        if stem and stem != doc.get("card_id"):
            errs.append(f"card_id '{doc.get('card_id')}' ≠ source_file 파일명 '{stem}'")
        if not doc.get("topics") and "매크로 무관" not in doc.get("notes", "") and not doc.get("views"):
            errs.append("topics가 비었으면 notes에 '매크로 무관'을 적어야 함")
    elif kind == "factor_shocks":
        probs = []
        for s in doc.get("scenarios", []):
            errs += _check_factors(s.get("shocks", {}), f"scenario {s.get('name')}", names)
            if s.get("prob") is not None:
                probs.append(s["prob"])
        # 단기 시나리오(prob 없음)와 장기 Base/Bull/Bear(prob 있음)가 섞일 수 있음 → prob 있는 것만 합 검사
        if probs and abs(sum(probs) - 1) > 1e-3:
            errs.append(f"prob 합 {sum(probs):.3f} ≠ 1")
    return errs


def validate_file(path: Path, kind: str | None = None, snapshot: dict | None = None) -> list[str]:
    kind = kind or infer_type(path)
    if kind is None:
        return [f"유형을 추론할 수 없음 (--type 지정 필요)"]
    try:
        doc = load_json(path)
    except Exception as e:  # noqa: BLE001
        return [f"JSON 파싱 실패: {e}"]
    schema = load_json(SCHEMA_DIR / TYPES[kind])
    v = Draft202012Validator(schema, registry=_registry())
    errs = [f"[스키마] {'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}" for e in v.iter_errors(doc)]
    if kind == "macro_topic" and path.stem in TOPIC_IDS and doc.get("topic_id") != path.stem:
        errs.append(f"파일명 {path.stem} ≠ topic_id {doc.get('topic_id')}")
    return errs + semantic_errors(kind, doc, snapshot)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--type", choices=list(TYPES))
    ap.add_argument("--snapshot", default=str(SNAPSHOT_PATH), help="macro_topic 수치 대조용")
    ap.add_argument("--expect-all-topics", action="store_true", help="폴더에 16개 topic이 모두 있는지 검사")
    args = ap.parse_args(argv)
    snap = load_json(Path(args.snapshot)) if Path(args.snapshot).exists() else None
    files: list[Path] = []
    for p in map(Path, args.paths):
        files += sorted(x for x in p.rglob("*.json")) if p.is_dir() else [p]
    total_err = 0
    for f in files:
        errs = validate_file(f, args.type, snap)
        total_err += len(errs)
        print(f"{'OK ' if not errs else 'ERR'} {f}")
        for e in errs:
            print(f"    - {e}")
    if args.expect_all_topics:
        have = {f.stem for f in files}
        miss = [t for t in TOPIC_IDS if t not in have]
        if miss:
            print(f"ERR 누락 topic: {miss}")
            total_err += len(miss)
    print(f"\n{len(files)}개 파일, 오류 {total_err}건")
    return 1 if total_err else 0


if __name__ == "__main__":
    sys.exit(main())
