#!/usr/bin/env python3
"""2026-11-23 frozen financial profit shadow. NO writes to production or main.

A: exact canonical program admission + official frozen attention scores.
B: replace *only* financial core-growth YoY input by verified single-quarter
   deductible net-profit YoY. Keep price/entry/technical/risk inputs frozen.
True quarter-over-quarter profits are intentionally NOT estimated: prior
quarter actual deductible profit amounts are absent from the source artifact.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from copy import deepcopy
import json
import math
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_trend_buy_manual_research as scanner
import prepare_trend_buy_candidates as admission
import trend_buy_prescreen_core as prescreen

DAY = "2026-11-23"
SOURCE = admission.F10_SOURCE


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def clamp(x):
    return max(0.0, min(1.0, x))


def source_ok(row, rec):
    return (
        isinstance(rec, dict)
        and rec.get("source_report") == SOURCE
        and rec.get("report_date") == row.get("report_date")
        and all(
            isinstance(rec.get(k), str) and bool(rec[k]) and rec[k] <= DAY
            for k in ("report_date", "notice_date", "update_date")
        )
    )


def shadow_admission(index, finance, qoq_factors=None):
    with tempfile.TemporaryDirectory(prefix="profit-shadow-") as dirname:
        empty = Path(dirname) / "empty_reviews.json"
        empty.write_text(json.dumps({
            "schema_version": "trend_buy_company_reviews_v2",
            "as_of_date": DAY, "reviews": []
        }), encoding="utf-8")
        scan = deepcopy(scanner.build(empty, audit_only=True))
    audited = scan["screen_audit"]["lightweight_scanned"]
    audit_by_code = {row["code"]: row for row in audited}
    if len(audit_by_code) != len(audited):
        raise ValueError("duplicate audited code")
    groups = defaultdict(list)
    for row in audited:
        groups[row["industry_code"]].append(row["code"])
    validated_overlay = {}
    coverage = []
    source_rows = []
    for sw3, codes in sorted(groups.items()):
        frozen = prescreen.frozen_industry_rows(ROOT, index, sw3, DAY)
        selected = set(codes)
        rows = [r for r in frozen if r["code"] in selected]
        if len(rows) != len(codes):
            raise ValueError("frozen source company count inconsistent")
        patched, modified = [], []
        missing = []
        for row in rows:
            f10 = finance["records"].get(row["code"])
            patch, _ = admission.validated_core_patch(row, f10, DAY)
            if patch:
                validated_overlay[row["code"]] = patch
            old = {**row, **patch}
            changed = dict(old)
            if source_ok(row, f10) and num(f10.get("single_quarter_deduct_net_profit_yoy")):
                changed["deduct_net_profit_yoy"] = f10["single_quarter_deduct_net_profit_yoy"]
                source_rows.append({
                    "code": row["code"], "industry_code": sw3,
                    "cumulative_deduct_profit_yoy": f10.get("deduct_net_profit_yoy"),
                    "single_quarter_deduct_profit_yoy": f10["single_quarter_deduct_net_profit_yoy"],
                    "prev_single_quarter_deduct_profit_yoy":
                        (f10.get("quarterly_acceleration") or {}).get("previous_single_quarter_deduct_profit_yoy_pct"),
                    "yoy_acceleration_pp":
                        (f10.get("quarterly_acceleration") or {}).get("deduct_profit_acceleration_pp"),
                    "true_profit_qoq": None,
                    "true_profit_qoq_gap": "PREVIOUS_QUARTER_SINGLE_PERIOD_AMOUNT_NOT_STORED",
                })
            else:
                missing.append(row["code"])
            patched.append(old)
            modified.append(changed)
        # Do not quietly mix financial source coverage when selecting names.
        if missing:
            raise ValueError(f"missing_same_day_quarterly_profit_yoy:{sw3}:{','.join(missing)}")
        for original, shadow, row in zip(
            scanner.scores(patched, financial_mode="CORE_FIRST"),
            scanner.scores(modified, financial_mode="CORE_FIRST"),
            rows,
        ):
            audit = audit_by_code[row["code"]]
            if not num(original[0]) or not num(shadow[0]):
                raise ValueError("unverified score")
            audit["fundamental_score"] = max(0.0, min(1.0, shadow[0] + 0.05 * (qoq_factors or {}).get(row["code"], 0.0)))
            audit["growth"] = shadow[1]
            audit["quality"] = shadow[2]
            audit["valuation_match"] = shadow[3]
            audit["growth_risk"] = shadow[5]
        coverage.append({"sw3": sw3, "hard_eligible": len(rows), "quarter_yoy_valid": len(rows)})
    new = prescreen.run(ROOT, scan, industry_index=index,
                        financial_overlay=validated_overlay)
    return new, coverage, source_rows


def attention_shadow(official, finance):
    output = []
    changed_rank = 0
    for theme in official["top5_by_theme"]:
        entries = []
        for r in theme["items"]:
            rec = finance["records"].get(r["code"])
            score = r["opportunity_rank_evidence"]
            components = score["research_quality_components"]
            if not rec or not num(rec.get("single_quarter_deduct_net_profit_yoy")):
                raise ValueError("shadow_attention_missing_quarter_yoy:"+r["code"])
            new_growth_component = clamp((rec["single_quarter_deduct_net_profit_yoy"] + 25) / 75)
            old_growth_component = components["core_growth_component"]
            new_quality = (score["research_quality_score"] +
                           50 * (new_growth_component - old_growth_component))
            # Existing quality occupies 15% of opportunity score.
            new_score = score["score"] + .15 * (new_quality - score["research_quality_score"])
            entries.append({
                "code": r["code"], "name": r["company_name"],
                "status": r["status"], "original_rank": r["attention_rank"],
                "original_score": score["score"], "shadow_score": round(new_score, 4),
                "published_cumulative_yoy": rec["deduct_net_profit_yoy"],
                "single_quarter_yoy": rec["single_quarter_deduct_net_profit_yoy"],
                "previous_quarter_yoy":
                    (rec.get("quarterly_acceleration") or {}).get("previous_single_quarter_deduct_profit_yoy_pct"),
                "yoy_acceleration_pp":
                    (rec.get("quarterly_acceleration") or {}).get("deduct_profit_acceleration_pp"),
            })
        # The READY-first priority is frozen, not recomputed.
        neworder = sorted(entries, key=lambda x: (
            0 if x["status"] == "READY" else 1,
            -x["shadow_score"], x["code"]))
        for rank, item in enumerate(neworder, 1):
            item["shadow_rank"] = rank
            changed_rank += item["shadow_rank"] != item["original_rank"]
        output.append({
            "theme": theme["trend_name"],
            "old_order": [r["code"] for r in sorted(entries, key=lambda x: x["original_rank"])],
            "shadow_order": [r["code"] for r in neworder],
            "items": sorted(entries, key=lambda x: x["original_rank"]),
        })
    return output, changed_rank


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="/tmp/profit_shadow_20261123.json")
    a = p.parse_args()
    out = Path(a.output).resolve()
    if ROOT.resolve() in out.parents or out == ROOT.resolve():
        raise ValueError("NO_SHADOW_OUTPUT_INSIDE_REPO")
    index = read(ROOT/"data/low_risk/index.json")
    finance = read(ROOT/"data/research/core_profit_refresh_latest.json")
    saved = read(ROOT/"research/trend_buy_candidates/latest.json")
    official = read(ROOT/"research/trend_buy_formal_result.json")
    if (index["trade_date"] != DAY or saved["trade_date"] != DAY
            or official["trade_date"] != DAY):
        raise ValueError("ASOF_20261123_INPUT_NOT_FROZEN")
    admission.validate_financial_source(finance, DAY)
    baseline = admission.prepare(ROOT)
    if baseline["industries"] != saved["industries"]:
        raise ValueError("BASELINE_REPLAY_DIFFERS_FROM_FORMAL_ADMISSION")
    shadow, coverage, sources = shadow_admission(index, finance)
    base_by_sw3 = {g["industry_code"]: g["selected_codes"]
                   for g in baseline["industries"]}
    candidate_diff = []
    for g in shadow["industry_groups"]:
        sw3 = g["industry_code"]
        new = g["research_codes"]
        old = base_by_sw3[sw3]
        candidate_diff.append({
            "industry_code": sw3, "original_codes": old, "shadow_codes": new,
            "added_codes": sorted(set(new)-set(old)),
            "removed_codes": sorted(set(old)-set(new)),
            "order_changed": new != old,
            "hard_eligible": g["hard_eligible_count"],
            "technically_eligible": g["eligible_with_new_technical_evidence"],
        })
    ranked, changes = attention_shadow(official, finance)
    result = {
        "mode": "READ_ONLY_FINANCIAL_SHADOW_NO_PRODUCTION_WRITES",
        "trade_date": DAY, "finance_asof": finance["asof_trade_date"],
        "baseline_replayed": True,
        "hypothesis": "replace cumulative deduct profit YoY with single-quarter deduct profit YoY ONLY",
        "qoq_metric_status": "BLOCKED_MISSING_ADJACENT_QUARTER_PROFIT_AMOUNTS",
        "qoq_must_not_be_inferred_from_yoy_acceleration": True,
        "financial_source_coverage": coverage,
        "candidate_differences": candidate_diff,
        "original_frozen_cohort_attention_differences": ranked,
        "original_cohort_rank_changes": changes,
        "financial_metrics_for_all_hard_eligible": sources,
        "official_ready_wait_unchanged": True,
        "official_handoff_unchanged": True,
        "not_an_executable_buy_list": True,
        "interpretation_note": ("Candidate differences require new same-day company reviews "
          "and independent READY risk checks; frozen 15-stock attention reweighting "
          "does not authorize any new stock or trade."),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print("SHADOW_REPORT", json.dumps({
        "date": DAY, "financial_coverage": coverage,
        "candidate_differences": candidate_diff,
        "original_cohort_rank_changes": changes,
        "qoq_status": result["qoq_metric_status"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
