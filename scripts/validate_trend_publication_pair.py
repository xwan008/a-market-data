#!/usr/bin/env python3
"""Read-only pre-publication consistency gate for complete registry + handoff.

Invoke on both PROPOSED files before any production write. The real GitHub
branch-update/readback stage is separate; a PASS here is not proof of a publish.
"""
import argparse
import json
from pathlib import Path


def validate(registry, handoff, require_migration=True):
    errors = []
    if registry.get("schema_version") not in (1, 2) or handoff.get("schema_version") != 1:
        errors.append("schema_version_mismatch")
    if registry.get("result_kind") != "a_share_trend_registry":
        errors.append("registry_result_kind_invalid")
    if handoff.get("result_kind") != "a_share_trend_handoff":
        errors.append("handoff_result_kind_invalid")
    if registry.get("status") != "COMPLETE":
        errors.append("registry_not_complete")
    if (not registry.get("trade_date") or
            registry.get("trade_date") != handoff.get("trade_date")):
        errors.append("trade_date_mismatch")
    gate = (registry.get("scan_audit") or {}).get("state_migration_gate") or {}
    if require_migration and (gate.get("mode") != "full_close" or
                              gate.get("current_trade_date") != registry.get("trade_date")):
        errors.append("migration_gate_missing")
    trends = registry.get("trends")
    signals = handoff.get("signals")
    if not isinstance(trends, list) or not isinstance(signals, list):
        return errors + ["trends_or_signals_not_list"]
    if not all(isinstance(x, dict) for x in trends + signals):
        return errors + ["trends_or_signals_invalid_items"]
    names = [t.get("trend_name") for t in trends]
    if len(set(names)) != len(names):
        errors.append("duplicate_registry_trend")
    if registry.get("schema_version") == 2:
        ids = [t.get("episode_id") for t in trends]
        if not all(isinstance(x, str) and x for x in ids) or len(set(ids)) != len(ids):
            errors.append("duplicate_or_missing_episode_ids")
    priority = [t for t in trends if t.get("in_new_position_priority") is True]
    actual = [s.get("trend_name") for s in signals]
    expected = [t.get("trend_name") for t in priority]
    if actual != expected:
        errors.append("priority_names_or_order_mismatch")
    if len(set(actual)) != len(actual):
        errors.append("duplicate_handoff_signal")
    lookup = {t.get("trend_name"): t for t in priority}
    for n, signal in enumerate(signals, start=1):
        name = signal.get("trend_name")
        source = lookup.get(name)
        if signal.get("rank") != n:
            errors.append(f"{name}:nonsequential_rank")
        if source is None:
            continue
        for field in ("trend_state", "market_state", "industry_codes", "industry_names"):
            if signal.get(field) != source.get(field):
                errors.append(f"{name}:{field}_mismatch")
        codes = signal.get("industry_codes")
        labels = signal.get("industry_names")
        if (not isinstance(codes, list) or not codes or
                not isinstance(labels, list) or len(codes) != len(labels)):
            errors.append(f"{name}:invalid_industry_route")
        if source.get("lifecycle_status") == "已失效":
            errors.append(f"{name}:invalidated_theme_handed_off")
        if registry.get("schema_version") == 2 and source.get("market_state") not in {"趋势确认", "候选趋势"}:
            errors.append(f"{name}:ineligible_v2_priority_state")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--handoff", required=True)
    parser.add_argument("--historical-baseline-only", action="store_true",
                        help="Validate a pre-migration historical pair, not safe to publish")
    args = parser.parse_args()
    try:
        a = json.loads(Path(args.registry).read_text(encoding="utf-8"))
        b = json.loads(Path(args.handoff).read_text(encoding="utf-8"))
        errors = validate(a, b, not args.historical_baseline_only)
    except (OSError, ValueError, TypeError) as exc:
        errors = ["input_error:" + str(exc)]
    print(json.dumps({"status": "PASS" if not errors else "BLOCKED",
                      "checks": "HISTORICAL" if args.historical_baseline_only else "PREPUBLICATION",
                      "errors": errors}, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
