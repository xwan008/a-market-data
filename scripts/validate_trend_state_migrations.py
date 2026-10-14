#!/usr/bin/env python3
"""Fail-closed pre-publication audit of model-proposed A-share trend transitions.

This checks structural continuity and the *presence/provenance* of evidence; it
cannot independently establish that external research claims are true. Keep
upstream research and market-data validation gates in force.
"""
from __future__ import annotations
import argparse
import json
import re
import sys

STATES = {"失效": 0, "高潮/衰退": 1, "观察": 2, "新异动": 2,
          "候选趋势": 3, "趋势确认": 4}
T_STATES = {"T0", "T1", "T2", "待核验"}
DIMENSIONS = {"COMMODITY_ANCHOR", "INDUSTRY_FUNDAMENTALS", "MARKET_STRUCTURE",
              "MARKET_BREADTH", "RELATIVE_STRENGTH", "SUPPLY_DEMAND",
              "MAJOR_CATALYST"}
SOURCE = re.compile(r"^(https?://\S+|(?:data|research)/[\w./-]+)$")
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _name_map(items, label, errors):
    if not isinstance(items, list):
        errors.append(f"{label}:not_list")
        return {}
    names = [x.get("trend_name") for x in items if isinstance(x, dict)]
    if len(names) != len(items) or not all(isinstance(n, str) and n for n in names):
        errors.append(f"{label}:invalid_names")
        return {}
    if len(set(names)) != len(names):
        errors.append(f"{label}:duplicate_names")
    return {x["trend_name"]: x for x in items}


def validate(previous, proposed, baseline_sha, snapshot=None):
    """Return blocking errors; [] means structurally safe to publish.

    A downgrade requires multi-day structural counterevidence plus an independent
    dimension, or a dated CRITICAL driver invalidation. Model-entered reviews
    do not establish independently verified market truth.
    """
    errors = []
    if previous.get("schema_version") != 1 or proposed.get("schema_version") != 1:
        errors.append("schema_version_mismatch")
    if previous.get("result_kind") != "a_share_trend_registry" or proposed.get("result_kind") != "a_share_trend_registry":
        errors.append("result_kind_mismatch")
    if previous.get("status") != "COMPLETE" or proposed.get("status") != "COMPLETE":
        errors.append("registry_not_complete")
    before_day, after_day = previous.get("trade_date"), proposed.get("trade_date")
    if not isinstance(before_day, str) or not DAY.fullmatch(before_day) or not isinstance(after_day, str) or not DAY.fullmatch(after_day) or after_day <= before_day:
        errors.append("invalid_trade_date_progression")
    if not isinstance(baseline_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", baseline_sha):
        errors.append("invalid_git_blob_sha")
    if snapshot is not None:
        if snapshot.get("trade_date") != after_day or snapshot.get("point_in_time_eligible") is not True or snapshot.get("auxiliary_only") is not True:
            errors.append("snapshot_date_or_point_in_time_invalid")
    old = _name_map(previous.get("trends"), "previous_trends", errors)
    new = _name_map(proposed.get("trends"), "proposed_trends", errors)
    audit = proposed.get("scan_audit") or {}
    gate = audit.get("state_migration_gate") or {}
    if gate.get("previous_registry_blob_sha") != baseline_sha or gate.get("previous_registry_trade_date") != before_day:
        errors.append("baseline_sha_or_date_not_frozen")
    if gate.get("current_trade_date") != after_day or gate.get("mode") != "full_close":
        errors.append("migration_gate_mode_or_date_invalid")
    reviews = _name_map(gate.get("reviews"), "migration_reviews", errors)
    if set(reviews) != set(old):
        errors.append("review_coverage_mismatch")
    invalidated = _name_map(proposed.get("invalidated_history", []), "invalidated_history", errors)
    for name, prior in old.items():
        latest = new.get(name)
        review = reviews.get(name)
        if latest is None:
            if name not in invalidated:
                errors.append(f"{name}:silently_removed")
            else:
                errors.append(f"{name}:removed_requires_separate_identity_migration")
            continue
        if not isinstance(review, dict):
            errors.append(f"{name}:missing_review")
            continue
        if latest.get("first_seen_trade_date") != prior.get("first_seen_trade_date"):
            errors.append(f"{name}:first_seen_rewritten")
        old_hist, new_hist = prior.get("state_history"), latest.get("state_history")
        if not isinstance(old_hist, list) or not isinstance(new_hist, list) or new_hist[:len(old_hist)] != old_hist:
            errors.append(f"{name}:history_rewritten")
            tail = []
        else:
            tail = new_hist[len(old_hist):]
        m0, m1 = prior.get("market_state"), latest.get("market_state")
        t0, t1 = prior.get("trend_state"), latest.get("trend_state")
        l0, l1 = prior.get("lifecycle_status"), latest.get("lifecycle_status")
        if m0 not in STATES or m1 not in STATES or t0 not in T_STATES or t1 not in T_STATES:
            errors.append(f"{name}:invalid_state_enum")
            continue
        changed = (m0, t0, l0) != (m1, t1, l1)
        if (review.get("previous_market_state"), review.get("proposed_market_state"),
            review.get("previous_trend_state"), review.get("proposed_trend_state")) != (m0, m1, t0, t1):
            errors.append(f"{name}:review_state_mismatch")
        if review.get("decision") != ("CHANGE" if changed else "HOLD"):
            errors.append(f"{name}:decision_mismatch")
        if not isinstance(review.get("reason"), str) or len(review["reason"].strip()) < 12:
            errors.append(f"{name}:missing_reason")
        if changed:
            if m0 != m1 and not any(h.get("trade_date") == after_day and h.get("from") == m0 and h.get("to") == m1 for h in tail if isinstance(h, dict)):
                errors.append(f"{name}:market_transition_history_missing")
            if t0 != t1 and not any(h.get("trade_date") == after_day and h.get("from") == t0 and h.get("to") == t1 for h in tail if isinstance(h, dict)):
                errors.append(f"{name}:industry_transition_history_missing")
            if l0 != l1 and not any(h.get("trade_date") == after_day for h in tail if isinstance(h, dict)):
                errors.append(f"{name}:lifecycle_transition_history_missing")
        evidence = review.get("evidence", [])
        if not isinstance(evidence, list):
            errors.append(f"{name}:invalid_evidence")
            evidence = []
        qualified = []
        for e in evidence:
            if not isinstance(e, dict):
                errors.append(f"{name}:invalid_evidence_entry")
                continue
            date = e.get("trade_date")
            if (e.get("dimension") not in DIMENSIONS or e.get("direction") not in {"SUPPORT", "COUNTER"}
                or e.get("impact") not in {"NORMAL", "STRUCTURAL", "CRITICAL"}
                or not isinstance(date, str) or not DAY.fullmatch(date) or date > after_day
                or not isinstance(e.get("source"), str) or not SOURCE.fullmatch(e["source"])
                or not isinstance(e.get("finding"), str) or len(e["finding"].strip()) < 10):
                errors.append(f"{name}:unverifiable_evidence_metadata")
                continue
            qualified.append(e)
        if changed and not any(e["trade_date"] > before_day for e in qualified):
            errors.append(f"{name}:no_new_dated_evidence")
        # Mapping gaps and single-day breadth declines are not independent
        # evidence of market structure invalidation.
        downgrade = (m0 != m1 and STATES[m1] < STATES[m0]) or (l1 == "已失效" and l0 != l1)
        if downgrade:
            counters = [e for e in qualified if e["direction"] == "COUNTER" and e["trade_date"] > before_day]
            critical = any(e["impact"] == "CRITICAL" and e["dimension"] in
                           {"COMMODITY_ANCHOR", "INDUSTRY_FUNDAMENTALS", "SUPPLY_DEMAND", "MAJOR_CATALYST", "MARKET_STRUCTURE"}
                           for e in counters)
            structural = any(e["dimension"] == "MARKET_STRUCTURE" and e["impact"] in {"STRUCTURAL", "CRITICAL"}
                             and isinstance(e.get("window_trading_days"), int) and e["window_trading_days"] >= 3
                             for e in counters)
            independent = len({e["dimension"] for e in counters}) >= 2
            if not (critical or (structural and independent)):
                errors.append(f"{name}:downgrade_without_structural_or_critical_counterevidence")
        if changed and not qualified:
            errors.append(f"{name}:transition_without_evidence")
    return errors


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--previous", required=True)
    p.add_argument("--proposed", required=True)
    p.add_argument("--previous-blob-sha", required=True)
    p.add_argument("--snapshot", help="Optional same-day auxiliary research snapshot")
    args = p.parse_args(argv)
    try:
        def load(path):
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        failures = validate(load(args.previous), load(args.proposed), args.previous_blob_sha,
                            load(args.snapshot) if args.snapshot else None)
    except (OSError, ValueError, TypeError) as exc:
        failures = ["input_error:" + str(exc)]
    print(json.dumps({"status": "PASS" if not failures else "BLOCKED", "errors": failures}, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
