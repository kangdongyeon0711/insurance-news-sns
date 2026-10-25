"""익스포저 × 팩터 충격 → 자산군 × 시나리오 영향 테이블.

사용:
  python scripts/calc_impact.py --portfolio knowledge/portfolios/현대해상/2026Q2.json \
      --shocks reports/tmp/2026-10-25_factor_shocks.json [--out reports/tmp/2026-10-25_현대해상_impact] \
      [--floating-income] [--check-constraints] [--proposal proposal.json]

- 금액 단위: 입력 mv_krw_bn(십억원) → 출력 impact_100m(억원, = 십억원 × 10), bp = 운용자산 대비.
- 계산 규칙은 config/assumptions.yaml의 class_rules로 매핑한다 (sensitivity_matrix.md의 ✅ 셀).
- 가정값(assumptions.yaml)이나 '추정' 플래그 값을 쓴 셀은 estimated: true.
- 시나리오에 없는 팩터는 0으로 보고 missing_factors에 기록한다.
- prob가 있는 시나리오들(장기 Base/Bull/Bear)은 확률가중 기대 영향(prob_weighted)을 따로 계산한다.
- 출력: {out}.json, {out}.csv (기본 out = reports/tmp/{as_of}_{company}_impact), 콘솔 표.
"""
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path

from common import CONFIG_DIR, TMP_REPORTS_DIR, load_json, load_yaml, save_json, today

BP = 1e-4


@dataclass
class Cell:
    impact_bn: float = 0.0              # 십억원
    components: dict = field(default_factory=dict)
    estimated: bool = False
    est_reasons: list = field(default_factory=list)
    used_factors: set = field(default_factory=set)

    def add(self, name: str, value_bn: float) -> None:
        self.components[name] = self.components.get(name, 0.0) + value_bn
        self.impact_bn += value_bn

    def est(self, reason: str) -> None:
        self.estimated = True
        if reason not in self.est_reasons:
            self.est_reasons.append(reason)


class Engine:
    def __init__(self, assumptions: dict | None = None, floating_income: bool = False):
        self.a = assumptions or load_yaml(CONFIG_DIR / "assumptions.yaml")
        self.floating_income = floating_income

    # ---------- 필드 조회 (공시값 우선, 없으면 가정값 + estimated) ----------
    def _field(self, asset: dict, key: str, default, cell: Cell, label: str):
        v = asset.get(key)
        if v is None:
            cell.est(f"{label}=가정 {default}")
            return default
        if (asset.get("field_flags") or {}).get(key) == "추정":
            cell.est(f"{label}=추정")
        return v

    def _duration(self, asset: dict, cell: Cell) -> float:
        return float(self._field(asset, "mod_duration", self.a["duration"].get(asset["class"], 0.0), cell, "D_mod"))

    def _spread_duration(self, asset: dict, d: float, cell: Cell) -> float:
        if asset.get("spread_duration") is not None:
            if (asset.get("field_flags") or {}).get("spread_duration") == "추정":
                cell.est("SD=추정")
            return float(asset["spread_duration"])
        cell.est("SD=D_mod 가정")
        return d

    def _convexity(self, asset: dict, d: float) -> float:
        if asset.get("convexity") is not None:
            return float(asset["convexity"])
        return d * d if self.a.get("convexity_mode") == "approx" else 0.0

    @staticmethod
    def _g(shocks: dict, name: str, cell: Cell, missing: set) -> float:
        cell.used_factors.add(name)
        if name not in shocks:
            missing.add(name)
            return 0.0
        return float(shocks[name])

    def _curve_shift_bp(self, region: str, d: float, shocks: dict, cell: Cell, missing: set) -> float:
        """듀레이션 d에 대응하는 금리 변화(bp): 커브 포인트 선형 보간, 양끝은 고정."""
        pts = [(float(t), f) for t, f in self.a["curve"][region]]
        avail = [(t, f) for t, f in pts if f in shocks]
        for _, f in pts:
            cell.used_factors.add(f)
        if not avail:
            missing.update(f for _, f in pts)
            return 0.0
        if len(avail) < len(pts):
            missing.update(f for _, f in pts if f not in shocks)
        vals = [(t, float(shocks[f])) for t, f in avail]
        if d <= vals[0][0]:
            return vals[0][1]
        if d >= vals[-1][0]:
            return vals[-1][1]
        for (t0, v0), (t1, v1) in zip(vals, vals[1:]):
            if t0 <= d <= t1:
                return v0 + (v1 - v0) * (d - t0) / (t1 - t0)
        return vals[-1][1]

    def _price_effect(self, mv: float, d: float, c: float, dy_bp: float) -> float:
        dy = dy_bp * BP
        return mv * (-d * dy + 0.5 * c * dy * dy)

    def _fx(self, asset: dict, mv: float, shocks: dict, cell: Cell, missing: set) -> None:
        if asset.get("currency", "KRW") == "KRW":
            return
        defaults = self.a["fx_hedge_ratio"]
        h = float(self._field(asset, "fx_hedge_ratio", defaults.get(asset["class"], defaults["default"]), cell, "헤지비율"))
        if asset["currency"] != "USD":
            cell.est(f"{asset['currency']} 환율을 원/달러로 근사")
        fx = self._g(shocks, "krw_usd_pct", cell, missing) / 100
        cell.add("fx", mv * (1 - h) * fx)
        hc = self._g(shocks, "fx_hedge_cost_bp", cell, missing) * BP
        cell.add("hedge_cost", -mv * h * hc * float(self.a.get("hedge_holding_years", 1.0)))
        if h > 0 and hc:
            cell.est("헤지비용 보유기간 가정")

    # ---------- 자산 1개 × 시나리오 1개 ----------
    def asset_impact(self, asset: dict, shocks: dict, missing: set) -> Cell:
        cell = Cell()
        cls = asset["class"]
        rule = self.a["class_rules"].get(cls, {"method": "none"})
        method = rule["method"]
        mv = float(asset["mv_krw_bn"])
        region = asset.get("region", "KR")
        if asset.get("value_flag") == "추정":
            cell.est("금액=추정")
        if method == "none":
            return cell

        if method == "bond_kr":
            d = self._duration(asset, cell)
            c = self._convexity(asset, d)
            cell.add("rate", self._price_effect(mv, d, c, self._curve_shift_bp("KR", d, shocks, cell, missing)))
            beta = float(self.a["spread_beta"].get(cls, 0.0))
            if beta:
                grade = (asset.get("credit_grade") or "").upper()
                if cls == "회사채" and not grade:
                    cell.est("등급 미공시 → AA 가정")
                factor = "kr_bbb_spread_bp" if grade.startswith(("BBB", "BB", "B", "HY")) and cls == "회사채" else "kr_aa_spread_bp"
                if cls != "회사채":
                    cell.est(f"스프레드 배수 {beta} 가정")
                sd = self._spread_duration(asset, d, cell)
                cell.add("spread", -mv * sd * beta * self._g(shocks, factor, cell, missing) * BP)

        elif method == "bond_foreign":
            d = self._duration(asset, cell)
            c = self._convexity(asset, d)
            if region not in ("US",):
                cell.est(f"{region} 금리를 UST로 근사")
            cell.add("rate", self._price_effect(mv, d, c, self._curve_shift_bp("US", d, shocks, cell, missing)))
            grade = (asset.get("credit_grade") or "").upper()
            if not grade:
                cell.est("등급 미공시 → IG 가정")
            factor = "us_hy_oas_bp" if grade in ("HY", "BB", "B", "CCC") else "us_ig_oas_bp"
            sd = self._spread_duration(asset, d, cell)
            cell.add("spread", -mv * sd * self._g(shocks, factor, cell, missing) * BP)
            self._fx(asset, mv, shocks, cell, missing)

        elif method == "equity":
            beta = float(self._field(asset, "beta", self.a["beta"].get(cls, 1.0), cell, "베타"))
            share = 1.0
            if rule.get("share"):
                share = float(self.a[rule["share"]])
                cell.est(f"주식 노출 비율 {share} 가정")
            factor = rule["factor"]
            if cls == "수익증권" and region != "KR":
                factor = "equity_spx_pct"
            cell.add("equity", mv * share * beta * self._g(shocks, factor, cell, missing) / 100)
            self._fx(asset, mv, shocks, cell, missing)

        elif method == "cap_rate":
            key = "KR" if region == "KR" else "US"
            cap = float(self.a["cap_rate"].get(key, self.a["cap_rate"]["default"]))
            cell.est(f"기준 캡레이트 {cap} 가정")
            if region not in ("KR", "US"):
                cell.est(f"{region} 캡레이트를 US로 근사")
            dcap = self._g(shocks, f"{key.lower()}_cre_cap_rate_bp", cell, missing) * BP
            cell.add("cap_rate", -mv * dcap / cap)
            self._fx(asset, mv, shocks, cell, missing)

        elif method == "loss_rate":
            beta = float(self.a["pf_loss_beta"].get(cls, 1.0))
            if beta != 1.0:
                cell.est(f"손실률 배수 {beta} 가정")
            cell.add("credit_loss", -mv * beta * self._g(shocks, rule["factor"], cell, missing) / 100)

        elif method == "discount_rate":
            d = self._duration(asset, cell)
            factor = rule.get("factor_foreign", rule["factor"]) if region != "KR" else rule["factor"]
            if factor not in shocks and rule["factor"] in shocks:   # 해외 팩터가 없으면 국내 값으로 근사
                cell.est(f"{factor} 없음 → {rule['factor']}로 근사")
                factor = rule["factor"]
            cell.add("discount_rate", -mv * d * self._g(shocks, factor, cell, missing) * BP)
            self._fx(asset, mv, shocks, cell, missing)

        elif method == "pe":
            factor = "kr_pe_value_pct" if region == "KR" else "us_pe_value_pct"
            cell.add("valuation", mv * self._g(shocks, factor, cell, missing) / 100)
            self._fx(asset, mv, shocks, cell, missing)

        elif method == "private_debt":
            key = "KR" if region == "KR" else "US"
            lgd = float(self.a["lgd"].get(key, self.a["lgd"]["default"]))
            cell.est(f"LGD {lgd} 가정")
            cell.add("credit_loss", -mv * self._g(shocks, f"{key.lower()}_pd_default_pp", cell, missing) / 100 * lgd)
            if self.floating_income and asset.get("floating_rate", True):
                f = self.a["floating_rate_factor"][key]
                cell.est("변동금리 이자효과 1년 가정")
                cell.add("floating_income", mv * self._g(shocks, f, cell, missing) * BP)
            self._fx(asset, mv, shocks, cell, missing)
        else:
            raise ValueError(f"알 수 없는 method: {method}")
        return cell

    # ---------- ALM ----------
    def alm(self, portfolio: dict, shocks: dict) -> dict | None:
        liab = portfolio.get("liabilities") or {}
        if liab.get("duration") is None or liab.get("pv_krw_bn") is None:
            return None
        factor = self.a.get("alm_rate_factor", "ktb_10y_bp")
        dy = float(shocks.get(factor, 0.0)) * BP
        da_a, est = 0.0, liab.get("value_flag") == "추정"
        for asset in portfolio["assets"]:
            if self.a["class_rules"].get(asset["class"], {}).get("method") in ("bond_kr", "bond_foreign", "discount_rate"):
                tmp = Cell()
                da_a += self._duration(asset, tmp) * float(asset["mv_krw_bn"])
                est = est or tmp.estimated
        dl_l = float(liab["duration"]) * float(liab["pv_krw_bn"])
        asset_side, liab_side = -da_a * dy, -dl_l * dy
        total = float(portfolio["total_invested_assets_krw_bn"])
        return {"rate_factor": factor, "dy_bp": dy / BP, "D_A": round(da_a / total, 3) if total else None,
                "D_L": liab["duration"], "L_krw_bn": liab["pv_krw_bn"],
                "duration_gap_years": round((da_a - dl_l) / total, 3) if total else None,
                "asset_100m": round(asset_side * 10, 1), "liability_100m": round(liab_side * 10, 1),
                "net_100m": round((asset_side - liab_side) * 10, 1),
                "net_bp": round((asset_side - liab_side) / total * 1e4, 1) if total else None,
                "estimated": est}


def row_key(asset: dict, idx: int, counts: dict) -> str:
    base = asset["class"] + ("" if asset.get("region", "KR") == "KR" else f"({asset['region']})")
    if counts[base] > 1:
        base += f"#{asset.get('label') or idx + 1}"
    return base


def run(portfolio: dict, shocks_doc: dict, engine: Engine | None = None) -> dict:
    engine = engine or Engine()
    total = float(portfolio["total_invested_assets_krw_bn"])
    assets = portfolio["assets"]
    from collections import Counter

    counts = Counter(a["class"] + ("" if a.get("region", "KR") == "KR" else f"({a['region']})") for a in assets)
    keys = [row_key(a, i, counts) for i, a in enumerate(assets)]
    scenarios_out = []
    for sc in shocks_doc["scenarios"]:
        shocks, missing = sc["shocks"], set()
        rows = []
        for key, asset in zip(keys, assets):
            cell = engine.asset_impact(asset, shocks, missing)
            rows.append({"key": key, "class": asset["class"], "region": asset.get("region", "KR"),
                         "mv_krw_bn": asset["mv_krw_bn"], "impact_100m": round(cell.impact_bn * 10, 2),
                         "impact_bp": round(cell.impact_bn / total * 1e4, 2) if total else None,
                         "pct_of_class": round(cell.impact_bn / asset["mv_krw_bn"] * 100, 3) if asset["mv_krw_bn"] else None,
                         "components_100m": {k: round(v * 10, 2) for k, v in cell.components.items()},
                         "estimated": cell.estimated, "estimated_reasons": cell.est_reasons})
        tot_bn = sum(r["impact_100m"] for r in rows) / 10
        scenarios_out.append({
            "name": sc["name"], "prob": sc.get("prob"), "horizon": sc.get("horizon"),
            "rows": rows, "total_100m": round(tot_bn * 10, 1),
            "total_bp": round(tot_bn / total * 1e4, 1) if total else None,
            "any_estimated": any(r["estimated"] for r in rows),
            "missing_factors": sorted(missing), "alm": engine.alm(portfolio, shocks),
        })
    weighted = [s for s in scenarios_out if s["prob"] is not None]
    pw = None
    if weighted:
        psum = sum(s["prob"] for s in weighted)
        by_key = {k: sum(s["prob"] * s["rows"][i]["impact_100m"] for s in weighted) / psum for i, k in enumerate(keys)}
        tot = sum(by_key.values())
        pw = {"scenarios": [s["name"] for s in weighted], "probs": [s["prob"] for s in weighted],
              "rows": [{"key": k, "impact_100m": round(v, 2), "impact_bp": round(v / 10 / total * 1e4, 2)}
                       for k, v in by_key.items()],
              "total_100m": round(tot, 1), "total_bp": round(tot / 10 / total * 1e4, 1)}
    return {
        "company": portfolio["company"], "period": portfolio["period"], "is_sample": portfolio.get("is_sample", False),
        "total_invested_assets_krw_bn": total, "shocks_as_of": shocks_doc.get("as_of"),
        "shocks_source": shocks_doc.get("source"), "computed_at": today().isoformat(),
        "valuation_basis": engine.a.get("valuation_basis"), "units": {"impact": "억원", "bp": "운용자산 대비 bp"},
        "scenarios": scenarios_out, "prob_weighted": pw,
    }


def check_constraints(portfolio: dict, constraints: dict, alm: dict | None = None,
                      proposal: dict | None = None) -> list[dict]:
    """현재(또는 proposal의 %p 조정 반영 후) 비중이 한도를 지키는지 점검."""
    total = float(portfolio["total_invested_assets_krw_bn"])
    weights = []
    for a in portfolio["assets"]:
        weights.append({**a, "w": float(a["mv_krw_bn"]) / total if total else 0.0})
    if proposal:
        for w in weights:
            w["w"] += float(proposal.get("deltas_pp", {}).get(w["class"], 0.0)) / 100 / max(
                1, sum(1 for x in weights if x["class"] == w["class"]))
    out = []
    for lim in constraints.get("limits", []):
        sel = [w for w in weights
               if (not lim.get("classes") or w["class"] in lim["classes"])
               and (not lim.get("regions") or w.get("region") in lim["regions"])
               and (not lim.get("grades") or (w.get("credit_grade") or "").upper() in lim["grades"])]
        val = sum(w["w"] for w in sel)
        ok = (lim.get("max") is None or val <= lim["max"] + 1e-9) and (lim.get("min") is None or val >= lim["min"] - 1e-9)
        out.append({"name": lim["name"], "value": round(val, 4), "min": lim.get("min"), "max": lim.get("max"), "ok": ok})
    gap_lim = constraints.get("duration_gap", {}).get("max_abs_years")
    if gap_lim is not None:
        gap = alm.get("duration_gap_years") if alm else None
        out.append({"name": "듀레이션 갭(년)", "value": gap, "min": -gap_lim, "max": gap_lim,
                    "ok": None if gap is None else abs(gap) <= gap_lim})
    if proposal:
        step = constraints.get("max_step_pp")
        for cls, d in proposal.get("deltas_pp", {}).items():
            if step is not None and abs(d) > step:
                out.append({"name": f"조정폭 {cls}", "value": d, "min": -step, "max": step, "ok": False})
    return out


def print_table(result: dict) -> None:
    from tabulate import tabulate

    names = [s["name"] for s in result["scenarios"]]
    keys = [r["key"] for r in result["scenarios"][0]["rows"]]
    rows = []
    for i, k in enumerate(keys):
        cells = []
        for s in result["scenarios"]:
            r = s["rows"][i]
            cells.append(f"{r['impact_100m']:,.0f}{'*' if r['estimated'] else ''}")
        if result["prob_weighted"]:
            cells.append(f"{result['prob_weighted']['rows'][i]['impact_100m']:,.0f}")
        rows.append([k, f"{result['scenarios'][0]['rows'][i]['mv_krw_bn']:,.0f}"] + cells)
    tot = [f"{s['total_100m']:,.0f}" for s in result["scenarios"]]
    bp = [f"{s['total_bp']:+.1f}bp" for s in result["scenarios"]]
    if result["prob_weighted"]:
        tot.append(f"{result['prob_weighted']['total_100m']:,.0f}")
        bp.append(f"{result['prob_weighted']['total_bp']:+.1f}bp")
    rows += [["합계(억원)", f"{result['total_invested_assets_krw_bn']:,.0f}"] + tot, ["운용자산 대비", ""] + bp]
    hdr = ["자산군", "MV(십억원)"] + names + (["확률가중"] if result["prob_weighted"] else [])
    print(f"{result['company']} {result['period']}{' [가상 샘플]' if result['is_sample'] else ''} — 영향(억원), * = 추정 포함")
    print(tabulate(rows, headers=hdr, disable_numparse=True, colalign=("left",) + ("right",) * (len(hdr) - 1)))
    for s in result["scenarios"]:
        if s["missing_factors"]:
            print(f"  [{s['name']}] 0으로 처리한 팩터: {', '.join(s['missing_factors'])}")
        if s["alm"]:
            a = s["alm"]
            print(f"  [{s['name']}] ALM: Δy={a['dy_bp']:+.0f}bp, 순자산 {a['net_100m']:,.0f}억원 ({a['net_bp']:+.1f}bp), 갭 {a['duration_gap_years']}년")


def write_csv(result: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["scenario", "prob", "key", "class", "region", "mv_krw_bn", "impact_100m", "impact_bp", "estimated",
                    "components_100m", "estimated_reasons"])
        for s in result["scenarios"]:
            for r in s["rows"]:
                w.writerow([s["name"], s["prob"], r["key"], r["class"], r["region"], r["mv_krw_bn"], r["impact_100m"],
                            r["impact_bp"], r["estimated"], r["components_100m"], "; ".join(r["estimated_reasons"])])
            w.writerow([s["name"], s["prob"], "합계", "", "", result["total_invested_assets_krw_bn"], s["total_100m"],
                        s["total_bp"], s["any_estimated"], "", ""])
        if result["prob_weighted"]:
            for r in result["prob_weighted"]["rows"]:
                w.writerow(["확률가중", "", r["key"], "", "", "", r["impact_100m"], r["impact_bp"], "", "", ""])
            w.writerow(["확률가중", "", "합계", "", "", "", result["prob_weighted"]["total_100m"],
                        result["prob_weighted"]["total_bp"], "", "", ""])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--portfolio", required=True)
    ap.add_argument("--shocks", required=True)
    ap.add_argument("--out", help="출력 경로 prefix (확장자 제외)")
    ap.add_argument("--floating-income", action="store_true", help="사모대출 변동금리 이자효과 포함")
    ap.add_argument("--check-constraints", action="store_true")
    ap.add_argument("--proposal", help='리밸런싱안 JSON: {"deltas_pp": {"해외채": -2, "국공채": 2}}')
    args = ap.parse_args(argv)
    portfolio, shocks = load_json(Path(args.portfolio)), load_json(Path(args.shocks))
    result = run(portfolio, shocks, Engine(floating_income=args.floating_income))
    if args.check_constraints or args.proposal:
        cons = load_yaml(CONFIG_DIR / "constraints.yaml")
        alm = next((s["alm"] for s in result["scenarios"] if s["alm"]), None)
        result["constraints_current"] = check_constraints(portfolio, cons, alm)
        if args.proposal:
            result["constraints_after_proposal"] = check_constraints(portfolio, cons, alm, load_json(Path(args.proposal)))
    out = Path(args.out) if args.out else TMP_REPORTS_DIR / f"{shocks.get('as_of', today().isoformat())}_{portfolio['company']}_impact"
    save_json(out.with_suffix(".json"), result)
    write_csv(result, out.with_suffix(".csv"))
    print_table(result)
    for key in ("constraints_current", "constraints_after_proposal"):
        if key in result:
            from tabulate import tabulate

            print(f"\n{key}:")
            print(tabulate([[c["name"], c["value"], c["min"], c["max"], {True: "충족", False: "위반", None: "미확인"}[c["ok"]]]
                            for c in result[key]], headers=["제약", "값", "min", "max", "판정"]))
    print(f"\n저장: {out.with_suffix('.json')}, {out.with_suffix('.csv')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
