#!/usr/bin/env python3
"""Read-only pre-publication consistency gate for complete registry + handoff.

Invoke on both PROPOSED files before any production write. The real GitHub
branch-update/readback stage is separate; a PASS here is not proof of a publish.
"""
import argparse
import json
from pathlib import Path

INDUSTRY_ROUTE_FROM = "2026-11-23"


def validate(registry, handoff):
    errors = []
    if registry.get("schema_version") != 2 or handoff.get("schema_version") != 1:
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
    scan = registry.get("scan_audit") or {}
    if scan.get("full_market_scan_completed") is not True:
        errors.append("full_market_scan_incomplete")
    gate = scan.get("state_migration_gate") or {}
    if gate.get("mode") != "full_close" or gate.get("current_trade_date") != registry.get("trade_date"):
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
    if any(t.get("market_state") not in {"趋势确认","候选趋势","观察"} or t.get("lifecycle_status") == "已失效" for t in trends):
        errors.append("nontracking_persisted")
    if any(t.get("market_state") == "观察" and t.get("in_new_position_priority") is True for t in trends):
        errors.append("observation_in_priority")
    ids = [t.get("episode_id") for t in trends]
    if not all(isinstance(x, str) and x for x in ids) or len(set(ids)) != len(ids):
        errors.append("duplicate_or_missing_episode_ids")
    prospective = registry.get("trade_date", "") >= "2026-10-27"
    independent_industry_routing = registry.get("trade_date", "") >= INDUSTRY_ROUTE_FROM

    def eligible_industries(theme):
        assessments = theme.get("industry_assessments")
        if not isinstance(assessments, list):
            return []
        result = []
        for row in assessments:
            if not isinstance(row, dict) or row.get("benefit_level") not in {"CORE", "DIRECT"}:
                continue
            if row.get("market_state") != "趋势确认":
                continue
            life = row.get("industry_lifecycle") or {}
            episodes = life.get("episodes") or []
            latest = episodes[-1] if episodes else {}
            if latest.get("d123_decision") != "CONFIRMED":
                continue
            result.append(row)
        return result

    if independent_industry_routing:
        for theme in trends:
            eligible = eligible_industries(theme)
            expected_priority = bool(eligible) and theme.get("lifecycle_status") != "已失效"
            if theme.get("in_new_position_priority") is not expected_priority:
                errors.append(f"{theme.get('trend_name')}:industry_priority_mismatch")
    elif prospective:
        if any(t.get("in_new_position_priority") is True and
               t.get("market_state") != "趋势确认" for t in trends):
            errors.append("only_confirmed_in_priority")

    priority = (
        [t for t in trends
         if eligible_industries(t) and t.get("lifecycle_status") != "已失效"]
        if independent_industry_routing
        else [t for t in trends if t.get("in_new_position_priority") is True]
    )
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
        if independent_industry_routing:
            if signal.get("theme_market_state") != source.get("market_state"):
                errors.append(f"{name}:theme_market_state_mismatch")
            if signal.get("market_state") != "趋势确认":
                errors.append(f"{name}:route_market_state_not_confirmed")
            if signal.get("trend_state") != source.get("trend_state"):
                errors.append(f"{name}:trend_state_mismatch")
            allowed = eligible_industries(source)
            expected_codes = [x.get("industry_code") for x in allowed]
            expected_names = [x.get("industry_name") for x in allowed]
            codes = signal.get("industry_codes")
            labels = signal.get("industry_names")
            if codes != expected_codes or labels != expected_names:
                errors.append(f"{name}:confirmed_route_order_or_membership_mismatch")
            expected_display_names = [name + " - " + label for label in expected_names]
            if signal.get("industry_display_names") != expected_display_names:
                errors.append(f"{name}:industry_display_names_mismatch")
            route_lifecycles = signal.get("industry_lifecycles")
            expected_lifecycles = []
            for row in allowed:
                life = row.get("industry_lifecycle") or {}
                latest = (life.get("episodes") or [{}])[-1]
                expected_lifecycles.append({
                    "industry_code": row.get("industry_code"),
                    "episode_id": latest.get("episode_id"),
                    "d123_stage": latest.get("d123_stage"),
                    "d123_decision": latest.get("d123_decision"),
                    "d123_decision_trade_date": latest.get("d123_decision_trade_date"),
                })
            if route_lifecycles != expected_lifecycles:
                errors.append(f"{name}:industry_lifecycle_handoff_mismatch")
        else:
            for field in (("trend_state", "market_state") if prospective
                          else ("trend_state", "market_state", "industry_codes", "industry_names")):
                if signal.get(field) != source.get(field):
                    errors.append(f"{name}:{field}_mismatch")
            if prospective:
                # Legacy route contract before the independent-lifecycle cutover.
                a = source.get("industry_assessments")
                if not isinstance(a, list):
                    errors.append(f"{name}:industry_assessments_missing")
                    a = []
                allowed = [x for x in a if isinstance(x, dict) and
                           x.get("market_state") == "趋势确认" and
                           x.get("benefit_level") in {"CORE", "DIRECT"}]
                eligible = {x.get("industry_code"): x.get("industry_name") for x in allowed}
                route = list(zip(signal.get("industry_codes") or [],
                                 signal.get("industry_names") or []))
                if (not route or len(route) != len(signal.get("industry_codes") or [])
                        or any(eligible.get(code) != label for code, label in route)
                        or len(set(code for code, _ in route)) != len(route)):
                    errors.append(f"{name}:unconfirmed_industry_route")
                elif set(code for code, _ in route) != set(eligible):
                    errors.append(f"{name}:confirmed_route_incomplete")
        codes = signal.get("industry_codes")
        labels = signal.get("industry_names")
        if (not isinstance(codes, list) or not codes or
                not isinstance(labels, list) or len(codes) != len(labels)):
            errors.append(f"{name}:invalid_industry_route")
        if source.get("lifecycle_status") == "已失效":
            errors.append(f"{name}:invalidated_theme_handed_off")
        if not independent_industry_routing and source.get("market_state") not in (
                {"趋势确认"} if prospective else {"趋势确认", "候选趋势"}):
            errors.append(f"{name}:ineligible_priority_state")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--handoff", required=True)
    args = parser.parse_args()
    try:
        a = json.loads(Path(args.registry).read_text(encoding="utf-8"))
        b = json.loads(Path(args.handoff).read_text(encoding="utf-8"))
        errors = validate(a, b)
    except (OSError, ValueError, TypeError) as exc:
        errors = ["input_error:" + str(exc)]
    print(json.dumps({"status": "PASS" if not errors else "BLOCKED",
                      "checks": "PREPUBLICATION",
                      "errors": errors}, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
