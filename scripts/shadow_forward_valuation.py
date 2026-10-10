#!/usr/bin/env python3
"""Standalone, fail-closed forward valuation SHADOW tool.

Run only on a separate exported frozen-facts snapshot AFTER the formal report is
published. No network access, no data/shards, no formal result/handoff writes.

python scripts/shadow_forward_valuation.py --input shadow_input.json --output shadow_result.json
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import date
from pathlib import Path


def positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def iso_day(value):
    if not isinstance(value, str):
        raise ValueError("missing ISO date")
    return date.fromisoformat(value[:10]).isoformat()


def valid_evidence(items, as_of):
    if not isinstance(items, list) or not items:
        return False
    for item in items:
        if not isinstance(item, dict):
            return False
        if not isinstance(item.get("source_url"), str) or not item["source_url"].startswith(("https://", "http://")):
            return False
        if not isinstance(item.get("business_line"), str) or not item["business_line"].strip():
            return False
        try:
            when = iso_day(item.get("published_at"))
        except (TypeError, ValueError):
            return False
        if when > as_of:
            return False
    return True


def reverse_eps(price, pe, years, discount, terminal_dividend=0.0):
    return (price * (1 + discount) ** years - terminal_dividend) / pe


def eval_one(company, as_of):
    code = str(company.get("code") or "")
    price = company.get("current_price")
    price_day = company.get("price_date")
    valuation_day = company.get("valuation_date")
    formal_status = company.get("formal_status")
    transmission = company.get("transmission")
    result = {
        "code": code,
        "name": company.get("name"),
        "formal_status_unchanged": formal_status,
        "transmission_unchanged": transmission,
        "shadow_scope": "EARLY_OPPORTUNITY_OBSERVATION" if transmission == "EARLY_EVIDENCE" else "SUPPORTED_SHADOW",
        "baseline": company.get("baseline") or {},
        "data_flags": [],
        "market_implied": {"status": "NOT_COMPUTABLE", "implied_forward_eps": None},
        "scenario_valuation": {"status": "INSUFFICIENT_EVIDENCE", "expected_value_now": None, "cases": None},
        "trade_structure": {
            "ma20": company.get("ma20"),
            "ma60": company.get("ma60"),
            "position_pct": company.get("position_pct"),
            "break_state": company.get("break_state"),
            "price_above_ma20": None,
            "price_above_ma60": None,
        },
    }
    try:
        pd = iso_day(price_day)
        if pd != as_of or not positive(price):
            result["data_flags"].append("PRICE_DATE_OR_PRICE_INVALID")
            return result
        if valuation_day is None or iso_day(valuation_day) != pd:
            result["data_flags"].append("STALE_MULTIPLE")
        report_day = company.get("report_date")
        if report_day and iso_day(report_day) > as_of:
            result["data_flags"].append("FUTURE_REPORT_DATE")
            return result
    except (ValueError, TypeError):
        result["data_flags"].append("BAD_DATE")
        return result

    for key, output in (("ma20", "price_above_ma20"), ("ma60", "price_above_ma60")):
        if positive(company.get(key)):
            result["trade_structure"][output] = price >= company[key]

    archetype = company.get("valuation_archetype")
    if archetype != "PE_FORWARD":
        result["scenario_valuation"]["status"] = "UNSUPPORTED_ARCHETYPE"
        result["data_flags"].append("FORWARD_MODEL_NOT_IMPLEMENTED")
        return result

    # Reverse valuation is strictly conditional on analyst-provided assumptions.
    assumptions = company.get("assumptions") or {}
    multiple = assumptions.get("reference_exit_pe")
    years = assumptions.get("horizon_years")
    discount = assumptions.get("required_return")
    valid_terms = (
        positive(multiple) and number(years) and 0.25 <= years <= 5
        and number(discount) and 0 < discount < 0.5
    )
    if valid_terms:
        result["market_implied"] = {
            "status": "CONDITIONAL_SENSITIVITY",
            "implied_forward_eps": round(reverse_eps(price, multiple, years, discount), 6),
            "reference_exit_pe": multiple,
            "horizon_years": years,
            "required_return": discount,
            "dividends": "omitted_not_assumed_zero_in_reality",
        }
    else:
        result["data_flags"].append("MISSING_DEFENSIBLE_REVERSE_ASSUMPTIONS")

    cases = company.get("scenarios")
    if not isinstance(cases, list) or len(cases) != 3 or {c.get("kind") for c in cases if isinstance(c, dict)} != {"bear", "base", "bull"}:
        return result
    probs = [c.get("probability") for c in cases]
    if not all(number(p) and 0 <= p <= 1 for p in probs) or abs(sum(probs) - 1.0) > 1e-9:
        result["scenario_valuation"]["status"] = "INVALID_PROBABILITIES"
        return result
    if not valid_terms:
        return result
    values = []
    for c in cases:
        if (not positive(c.get("forward_eps")) or not positive(c.get("exit_pe"))
                or not valid_evidence(c.get("evidence"), as_of)
                or not isinstance(c.get("falsifier"), str) or not c["falsifier"].strip()):
            result["scenario_valuation"]["status"] = "INSUFFICIENT_EVIDENCE"
            return result
        # EPS/exit PE must share the target horizon in the upstream research.
        v = c["forward_eps"] * c["exit_pe"] / ((1 + discount) ** years)
        values.append({"kind": c["kind"], "value_now": round(v, 4), "probability": c["probability"]})
    expected = sum(c["probability"] * c["forward_eps"] * c["exit_pe"] / (1 + discount) ** years for c in cases)
    result["scenario_valuation"] = {
        "status": "SCENARIO_ASSUMPTIONS_TO_VERIFY",
        "expected_value_now": round(expected, 4),
        "cases": values,
        "expected_upside_pct": round(100 * (expected / price - 1), 2),
        "verification_note": "Source URLs and EPS assumptions require analyst verification; not a formal target price.",
        "dividends": "omitted_not_assumed_zero_in_reality",
    }
    return result


def evaluate(payload):
    if payload.get("model") != "FORWARD_SHADOW_V1":
        raise ValueError("wrong model marker")
    as_of = iso_day(payload.get("as_of_date"))
    records = payload.get("companies")
    if not isinstance(records, list) or not records:
        raise ValueError("companies must be nonempty")
    codes = [str(x.get("code")) for x in records]
    if len(codes) != len(set(codes)):
        raise ValueError("duplicate company code")
    results = [eval_one(c, as_of) for c in records]
    return {
        "model": "FORWARD_SHADOW_V1",
        "production_effect": "NONE",
        "as_of_date": as_of,
        "input_provenance": payload.get("input_provenance"),
        "company_count": len(results),
        "companies": results,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    source = Path(args.input).resolve()
    target = Path(args.output).resolve()
    if source == target:
        raise ValueError("refusing to overwrite input")
    blocked = {"latest_formal_result.json", "low_risk_handoff.json", "trend_handoff.json"}
    if target.name in blocked:
        raise ValueError("refusing to overwrite formal research/handoff")
    payload = json.loads(source.read_text(encoding="utf-8"))
    result = evaluate(payload)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(target), "company_count": result["company_count"], "production_effect": "NONE"}))


if __name__ == "__main__":
    main()
