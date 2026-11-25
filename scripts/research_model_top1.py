#!/usr/bin/env python3
"""Research-only adapter: frozen TOP5 -> locked model TOP1 -> existing risk engine.

Never generates or overwrites formal results or monitoring handoff.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from . import trend_buy_engine as engine
except ImportError:
    import trend_buy_engine as engine

VERSION = "V1.6-R1"
GATES = ("input_verified", "five_categories_searched", "core_flow_verified",
         "fact_quality_verified", "dynamic_comparison_complete", "counterevidence_checked")
DIMENSIONS = ("trend_structure", "fund_flow", "quarterly_profit")
AUDIT = ("fresh_company_research", "working_set_frozen", "pre_screen_coverage",
         "company_research_coverage", "structure_same_day", "no_future_evidence",
         "json_schema_valid")
PLAN_FIELDS = ("setup_type", "entry_zone", "max_entry_price", "entry_trigger",
               "invalidation_price", "invalidation_rule", "initial_risk_pct",
               "upside_to_resistance_R", "exit_plan")


def require(condition, error):
    if not condition:
        raise ValueError(error)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def git_blob_sha(raw):
    return hashlib.sha1(("blob %d\0" % len(raw)).encode() + raw).hexdigest()


def valid_code(value):
    return isinstance(value, str) and len(value) == 6 and value.isascii() and value.isdigit()


def validate_pick(pick, roster):
    require(pick.get("candidate_codes") == roster, "FROZEN_ROSTER_OR_ORDER_MISMATCH")
    status, code = pick.get("status"), pick.get("top1_code")
    require("top1_code" in pick, "TOP1_FIELD_REQUIRED")
    require(nonempty(pick.get("reason")), "MISSING_SELECTION_OR_ABSTENTION_REASON")
    if status in ("INCOMPLETE", "NO_SELECTION"):
        require(code is None, "ABSTENTION_MUST_NOT_SELECT")
        return
    require(status == "COMPLETE" and code in roster, "INVALID_TOP1_SELECTION")
    gates = pick.get("completion_gate") or {}
    require(all(gates.get(k) is True for k in GATES), "MODEL_COMPLETION_GATE_FAILED")
    matrix = pick.get("research_matrix") or {}
    dynamic = pick.get("dynamic_comparison") or {}
    require(set(matrix) == set(roster) == set(dynamic), "MODEL_COMPARISON_SCOPE_MISMATCH")
    for symbol in roster:
        cells = matrix[symbol]
        require(set(cells) == set("ABCDE"), "INCOMPLETE_RESEARCH_MATRIX")
        for category, cell in cells.items():
            allowed = ("VERIFIED_FACT",) if category == "A" else ("VERIFIED_FACT", "NO_NEW_VERIFIED_EVENT")
            require(cell.get("status") in allowed and bool(cell.get("sources")),
                    "RESEARCH_CATEGORY_NOT_VERIFIED:" + symbol + ":" + category)
        require(all(nonempty(dynamic[symbol].get(k)) for k in DIMENSIONS),
                "DYNAMIC_COMPARISON_MISSING:" + symbol)
    reasons = pick.get("comparison_reasons") or {}
    require(set(reasons) == set(roster) - {code} and all(nonempty(v) for v in reasons.values()),
            "OTHER_CANDIDATE_REASONS_MISSING")
    require(nonempty(pick.get("strongest_counter")) and nonempty(pick.get("falsifier")),
            "COUNTEREVIDENCE_OR_FALSIFIER_MISSING")
    require(not pick.get("material_conflicts"), "UNRESOLVED_MATERIAL_CONFLICT")
    require(not any(k in pick for k in PLAN_FIELDS), "MODEL_MUST_NOT_SUPPLY_TRADE_PLAN")


def run(admission_raw, research, structure, selections):
    admission = json.loads(admission_raw)
    day = admission.get("trade_date")
    require(isinstance(day, str) and len(day) == 10, "INVALID_TRADE_DATE")
    require(admission.get("prescreen_version") == "CANONICAL", "CANONICAL_ADMISSION_REQUIRED")
    require(selections.get("prompt_version") == VERSION, "MODEL_RULE_VERSION_MISMATCH")
    require(selections.get("source_blob") == git_blob_sha(admission_raw), "ADMISSION_BLOB_MISMATCH")
    require(day == selections.get("trade_date") == research.get("trade_date") ==
            structure.get("reference_trade_date"), "ASOF_DATE_MISMATCH")
    require(research.get("schema_version") == "trend_buy_research_v2" and
            research.get("prescreen_version") == "CANONICAL" and
            research.get("coverage_complete") is True and
            research.get("mode") == "MODEL_TOP1_RESEARCH", "VALIDATED_FRESH_RESEARCH_REQUIRED")
    require(all((research.get("publication_audit") or {}).get(k) is True for k in AUDIT),
            "UPSTREAM_RESEARCH_GATE_FAILED")
    require(structure.get("contract_id") == "a-share-low-risk-price-structure", "STRUCTURE_CONTRACT_MISMATCH")

    groups = admission["industries"]
    by_industry = {g["industry_code"]: g["selected_codes"] for g in groups}
    require(len(groups) == len(by_industry), "DUPLICATE_INDUSTRY")
    require(all(isinstance(c, list) and 1 <= len(c) <= 5 and
                all(valid_code(x) for x in c) and len(set(c)) == len(c)
                for c in by_industry.values()), "INVALID_FROZEN_ROSTER")
    expected = {c: i for i, codes in by_industry.items() for c in codes}
    require(len(expected) == sum(map(len, by_industry.values())), "DUPLICATE_FROZEN_CODE")
    require(admission.get("selected_company_count") == len(expected), "ADMISSION_COUNT_MISMATCH")
    companies = research["companies"]
    reviewed = {c["code"]: c for c in companies}
    require(len(reviewed) == len(companies) == research.get("selected_company_count") == len(expected)
            and set(reviewed) == set(expected), "RESEARCH_SCOPE_MISMATCH")
    require(all(c.get("industry_code") == expected[code] and c.get("market_state") == "趋势确认"
                and nonempty(c.get("source_review")) for code, c in reviewed.items()),
            "RESEARCH_INDUSTRY_OR_CONFIRMATION_MISMATCH")
    picks = selections["items"]
    lookup = {p["industry_code"]: p for p in picks}
    require(len(lookup) == len(picks) and set(lookup) == set(by_industry), "SELECTION_GROUP_MISMATCH")
    # Validate every selection before calculating any plan.
    for industry, roster in by_industry.items():
        validate_pick(lookup[industry], roster)
    items = []
    for industry, roster in by_industry.items():
        pick = lookup[industry]
        code = pick["top1_code"]
        out = {"industry_code": industry, "candidate_codes": list(roster),
               "top1_code": code, "selection_status": pick["status"],
               "selection_reason": pick["reason"], "risk_status": None,
               "risk_result": None, "watch_reference": None,
               "conditional_plan": None, "route": "NO_MONITOR"}
        if code is not None:
            row = engine.evaluate_candidate(reviewed[code],
                        (structure.get("companies") or {}).get(code), day)
            status = row["status"]
            require(row.get("code") == code and status in engine.STATES, "INVALID_RISK_RESULT")
            out["risk_status"] = status
            if status == "READY":
                zone, stop = row.get("entry_zone"), row.get("invalidation_price")
                require(isinstance(zone, list) and len(zone) == 2 and
                        all(engine.pos(p) for p in zone) and engine.pos(stop) and
                        stop < zone[0] <= zone[1] and row.get("wait_reason") is None,
                        "READY_LACKS_VALID_PLAN")
                rr = row.get("upside_to_resistance_R")
                require(rr is None or (engine.val(rr) and rr >= engine.MIN_UPSIDE_R),
                        "READY_KNOWN_RESISTANCE_BELOW_MIN_RR")
                out["conditional_plan"] = {k: row.get(k) for k in PLAN_FIELDS}
                out["route"] = "RESEARCH_CONDITIONAL_ONLY"
            elif status == "WAIT":
                require(row.get("wait_reason") in engine.WAIT_REASONS, "INVALID_WAIT_REASON")
                out["watch_reference"] = engine.early_watch_reference(row)
                out["route"] = "OBSERVE_ONLY"
            # No actionable prices for WAIT/DROP/UNCERTAIN.
            out["risk_result"] = {k: v for k, v in row.items() if k not in PLAN_FIELDS}
        items.append(out)
    return {"schema_version": "model_top1_research_v1",
            "prompt_version": VERSION, "trade_date": day,
            "source_blob": selections["source_blob"], "research_only": True,
            "production_eligible": False, "no_order": True,
            "no_replacement": True, "risk_evaluated_count": sum(x["top1_code"] is not None for x in items),
            "items": items}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ("admission", "research", "structure", "selections", "output"):
        p.add_argument("--" + flag, required=True)
    a = p.parse_args()
    paths = [Path(getattr(a, k)).resolve() for k in ("admission", "research", "structure", "selections")]
    out = Path(a.output).resolve()
    require(out not in paths and out.name.startswith("top1_model_research_") and
            out.suffix == ".json", "RESEARCH_OUTPUT_ONLY")
    # Do not permit writing under repository production research/data paths.
    root = Path(__file__).resolve().parents[1]
    require(not any(out.is_relative_to(root / k) for k in ("research", "data", "automation")),
            "PRODUCTION_OUTPUT_PATH_FORBIDDEN")
    raw = paths[0].read_bytes()
    result = run(raw, *(json.loads(path.read_bytes()) for path in paths[1:]))
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")


if __name__ == "__main__":
    main()
