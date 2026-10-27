#!/usr/bin/env python3
"""Pre-publication identity check of upstream theme -> SW L3 handoff routes.

This does NOT decide whether a company benefits from a theme and does not
replace downstream frozen-manifest/parts or buy-point verification.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SW_LEVEL3 = re.compile(r"^S\d{6}$")


def check_theme_routes(handoff: dict, low_risk_index: dict, registry: dict | None = None) -> dict:
    if handoff.get("schema_version") != 1 or handoff.get("result_kind") != "a_share_trend_handoff":
        raise ValueError("invalid_original_handoff_contract")
    day = handoff.get("trade_date")
    prospective = isinstance(day, str) and day >= "2026-10-27"
    if prospective:
        # Use exactly the authoritative publication-pair contract. The newer
        # handoff contains a verified subset, NOT every industry on a theme.
        # Do not recreate a conflicting permission rule in this router.
        from validate_trend_publication_pair import validate as pair_validate
        if registry is None:
            raise ValueError("registry_required_for_verified_handoff")
        problems = pair_validate(registry, handoff)
        if problems:
            raise ValueError("publication_pair_invalid:" + ";".join(problems))
        if handoff.get("signals") == []:
            # A legitimate no-op research day needs no company index; it must
            # not trigger an empty company work-set or reuse old stock picks.
            return {
                "status": "NO_ELIGIBLE_CONFIRMED_TREND",
                "trade_date": day, "theme_count": 0,
                "unique_industry_count": 0,
                "total_company_memberships_across_themes": 0,
                "identity_only": True,
            }
    if not day or low_risk_index.get("trade_date") != day:
        raise ValueError("handoff_low_risk_trade_date_mismatch")
    if (low_risk_index.get("validation") or {}).get("status") != "passed":
        raise ValueError("low_risk_index_validation_not_passed")
    industries = low_risk_index.get("industries")
    if not isinstance(industries, dict):
        raise ValueError("missing_low_risk_industries")
    signals = handoff.get("signals")
    if not isinstance(signals, list):
        raise ValueError("missing_handoff_signals")
    if [x.get("rank") for x in signals] != list(range(1, len(signals) + 1)):
        raise ValueError("invalid_handoff_priority_order")
    if len({x.get("trend_name") for x in signals}) != len(signals):
        raise ValueError("duplicate_theme_identity")
    if registry is not None:
        if (registry.get("trade_date") != day or registry.get("status") != "COMPLETE"
                or registry.get("result_kind") != "a_share_trend_registry"):
            raise ValueError("registry_baseline_not_same_day_complete")
        priority = sorted((t for t in registry.get("trends", [])
                           if t.get("in_new_position_priority") is True),
                          key=lambda t: t.get("priority_rank", 9999))
        if [t.get("trend_name") for t in priority] != [s.get("trend_name") for s in signals]:
            raise ValueError("handoff_registry_priority_mismatch")
        if not prospective:
            # Old dated artifacts are read-only history; do not mutate them.
            for signal, recorded in zip(signals, priority):
                if (signal.get("industry_codes") != recorded.get("industry_codes")
                        or signal.get("industry_names") != recorded.get("industry_names")
                        or signal.get("trend_state") != recorded.get("trend_state")
                        or signal.get("market_state") != recorded.get("market_state")):
                    raise ValueError("handoff_registry_route_mismatch")
    routed, total_company_memberships = set(), 0
    for signal in signals:
        if not signal.get("trend_name") or signal.get("mapping_status") != "resolved":
            raise ValueError("theme_route_not_resolved")
        codes, names = signal.get("industry_codes"), signal.get("industry_names")
        if not isinstance(codes, list) or not codes or not isinstance(names, list):
            raise ValueError("theme_routes_missing")
        if len(codes) != len(names) or len(codes) != len(set(codes)):
            raise ValueError("theme_route_identity_mismatch_or_duplicate")
        for code, name in zip(codes, names):
            if not isinstance(code, str) or not SW_LEVEL3.fullmatch(code):
                raise ValueError("not_sw_level3_code:" + str(code))
            entry = industries.get(code)
            if entry is None:
                raise ValueError("no_universe_industry_code:" + code)
            if entry.get("industry_name") != name:
                raise ValueError("industry_name_code_mismatch:" + code)
            if not isinstance(entry.get("company_count"), int) or entry["company_count"] <= 0:
                raise ValueError("no_universe_member:" + code)
            if not entry.get("manifest_file") or not isinstance(entry.get("part_count"), int) or entry["part_count"] < 1:
                raise ValueError("industry_manifest_unavailable:" + code)
            routed.add(code)
            total_company_memberships += entry["company_count"]
    return {
        "status": "ROUTING_IDENTITY_VALIDATED", "trade_date": day,
        "theme_count": len(signals), "unique_industry_count": len(routed),
        "total_company_memberships_across_themes": total_company_memberships,
        "frozen_manifest_and_business_checks": "NOT_PERFORMED_DOWNSTREAM_OWNED",
        "identity_only": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff", required=True, help="Candidate original-schema handoff JSON")
    parser.add_argument("--registry", help="Candidate same-day complete registry JSON")
    parser.add_argument("--low-risk-index", default="data/low_risk/index.json")
    args = parser.parse_args()
    def load(path):
        return json.loads(Path(path).read_text(encoding="utf-8"))
    result = check_theme_routes(
        load(args.handoff), load(args.low_risk_index),
        load(args.registry) if args.registry else None)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
