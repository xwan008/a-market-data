#!/usr/bin/env python3
"""Validate a stage-one discovery checkpoint structurally, not cognitively.

Only an external checkpoint submitted and read back before historical inputs
are exposed can corroborate timing. This script is NEVER proof of independence.
"""
import argparse
import json
import re
from pathlib import Path

DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
BLOCKED_INPUTS = (
    "research/trend_registry.json", "research/trend_handoff.json",
    "data/research/sector_discovery_snapshot.json",
    "data/research/theme_evidence_snapshot.json")


def validate(checkpoint):
    issues = []
    if checkpoint.get("schema_version") != 1 or checkpoint.get("result_kind") != "a_share_firstpass_checkpoint":
        issues.append("checkpoint_schema_invalid")
    day = checkpoint.get("trade_date")
    if not isinstance(day, str) or not DAY.fullmatch(day):
        issues.append("checkpoint_date_invalid")
    if checkpoint.get("phase") != "PRE_HISTORY_PRE_PYTHON":
        issues.append("checkpoint_phase_invalid")
    if not isinstance(checkpoint.get("data_cutoff"), str) or not checkpoint["data_cutoff"].strip():
        issues.append("data_cutoff_missing")
    if checkpoint.get("read_previous_registry") is not False or checkpoint.get("read_python_candidates") is not False:
        issues.append("isolation_claim_not_explicit")
    for field in ("market_coverage", "industry_fact_coverage"):
        value = checkpoint.get(field)
        if not isinstance(value, dict) or not isinstance(value.get("scope"), str) or not isinstance(value.get("gaps"), list):
            issues.append(field + "_not_audited")
    inputs = checkpoint.get("inputs")
    if not isinstance(inputs, list):
        issues.append("inputs_missing")
    else:
        for item in inputs:
            if not isinstance(item, dict) or not isinstance(item.get("source"), str):
                issues.append("invalid_input")
                continue
            if any(x in item["source"] for x in BLOCKED_INPUTS):
                issues.append("biased_input_in_firstpass")
    candidates = checkpoint.get("candidates")
    if not isinstance(candidates, list):
        issues.append("candidates_not_list")
    elif len({x.get("direction") for x in candidates if isinstance(x, dict)}) != len(candidates):
        issues.append("duplicate_candidate")
    if isinstance(candidates, list):
        for item in candidates:
            if not isinstance(item, dict) or not isinstance(item.get("direction"), str) or not item["direction"].strip():
                issues.append("invalid_candidate")
                continue
            if not isinstance(item.get("evidence"), list) or not item["evidence"]:
                issues.append("candidate_without_evidence")
    return issues


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--checkpoint", required=True)
    args = p.parse_args()
    try:
        doc = json.loads(Path(args.checkpoint).read_text(encoding="utf-8"))
        issues = validate(doc)
    except (OSError, ValueError, TypeError) as exc:
        issues = ["input_error:" + str(exc)]
    print(json.dumps({"status": "PASS" if not issues else "BLOCKED",
                      "validates_order_independently": False,
                      "errors": issues}, ensure_ascii=False))
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
