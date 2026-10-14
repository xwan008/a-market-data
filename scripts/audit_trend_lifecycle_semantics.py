#!/usr/bin/env python3
"""Read-only registry audit: identify lifecycle invalidations lacking primary proof.

A WATCH item is an evidence gap, NOT a retrospective conclusion that an
industry is valid. Never rewrite historical trade dates or existing states.
"""
import argparse
import json
from pathlib import Path

PRIMARY = {"COMMODITY_ANCHOR", "INDUSTRY_FUNDAMENTALS",
           "SUPPLY_DEMAND", "MAJOR_CATALYST"}
PRICE_ONLY = {"MARKET_STRUCTURE", "MARKET_BREADTH", "RELATIVE_STRENGTH"}


def audit(registry, baseline_sha):
    findings = []
    themes = registry.get("trends") or []
    migration = (registry.get("scan_audit") or {}).get("state_migration_gate") or {}
    reviews = {r.get("trend_name"): r for r in migration.get("reviews", [])
               if isinstance(r, dict)}
    for theme in themes:
        if theme.get("lifecycle_status") != "已失效":
            continue
        name = theme.get("trend_name")
        first_invalidation = next(
            (h for h in theme.get("state_history", [])
             if isinstance(h, dict) and h.get("event") == "trend_invalidated"),
            None)
        events = [h for h in theme.get("state_history", [])
                  if isinstance(h, dict) and
                  (h.get("to") == "已失效" or h.get("event") == "trend_invalidated")]
        review = reviews.get(name) or {}
        counter = [e for e in review.get("evidence", [])
                   if isinstance(e, dict) and e.get("direction") == "COUNTER"]
        primary = [e for e in counter if e.get("dimension") in PRIMARY and
                   e.get("impact") in {"STRUCTURAL", "CRITICAL"}]
        if not primary:
            findings.append({
                "trend_name": name,
                "status": "REVIEW_REQUIRED",
                "reason": "LIFECYCLE_INVALIDATION_PRIMARY_EVIDENCE_NOT_STRUCTURED",
                "original_invalidation_date": (first_invalidation or (events[0] if events else {})).get("trade_date"),
                "industry_state": theme.get("trend_state"),
                "market_state": theme.get("market_state"),
                "note": "No independently auditable primary-driver counterevidence "
                        "was stored in state_migration_gate; this does NOT prove "
                        "that historical invalidation was wrong.",
            })
    return {
        "schema_version": 1,
        "result_kind": "trend_lifecycle_semantics_readonly_audit",
        "baseline_trade_date": registry.get("trade_date"),
        "baseline_git_blob_sha": baseline_sha,
        "audit_only": True,
        "historical_data_mutated": False,
        "themes_examined": len(themes),
        "invalidated_examined": sum(
            x.get("lifecycle_status") == "已失效" for x in themes),
        "requires_review": len(findings),
        "findings": findings,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--registry", required=True)
    p.add_argument("--registry-blob-sha", required=True)
    p.add_argument("--output", help="Optional read-only audit report destination")
    args = p.parse_args()
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    report = audit(registry, args.registry_blob_sha)
    result = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(result + "\n", encoding="utf-8")
    print(result)


if __name__ == "__main__":
    main()
