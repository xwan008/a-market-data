#!/usr/bin/env python3
"""Read-only gate for a prior trend Registry/Handoff input.

This never authorizes publication. The sole legacy exception is the exact
2026-10-16 active-pool snapshot that predates the full-close publication gate.
"""
import argparse
import hashlib
import json
from pathlib import Path

try:
    from scripts.validate_trend_publication_pair import validate as validate_pair
except ModuleNotFoundError:
    from validate_trend_publication_pair import validate as validate_pair


BOOTSTRAP_DAY = "2026-10-16"
BOOTSTRAP_REGISTRY_BLOB_SHA = "67640617708c76846df46bfa8024aacb7ce867a7"
BOOTSTRAP_HANDOFF_BLOB_SHA = "5e06dd395e6223c98eb8b02a025a343aee933e27"
BOOTSTRAP_ONLY_ERRORS = ["full_market_scan_incomplete", "migration_gate_missing"]


def git_blob_sha(raw):
    return hashlib.sha1(f"blob {len(raw)}\0".encode("ascii") + raw).hexdigest()


def validate_prior(registry, handoff, registry_blob_sha, handoff_blob_sha):
    """Return (errors, baseline_mode); never alter formal publication checks."""
    errors = validate_pair(registry, handoff)
    if not errors:
        return [], "FULL_CLOSE"

    scan = registry.get("scan_audit") or {}
    gate = scan.get("state_migration_gate") or {}
    initial = (
        registry.get("trade_date") == BOOTSTRAP_DAY
        and scan.get("mode") == "initial_active_baseline"
        and scan.get("trade_date") == BOOTSTRAP_DAY
        and scan.get("tracked_count") == 5
        and scan.get("full_market_scan_completed") is None
        and gate.get("mode") == "initial_active_baseline"
        and gate.get("current_trade_date") == BOOTSTRAP_DAY
        and registry_blob_sha == BOOTSTRAP_REGISTRY_BLOB_SHA
        and handoff_blob_sha == BOOTSTRAP_HANDOFF_BLOB_SHA
    )
    if initial and errors == BOOTSTRAP_ONLY_ERRORS:
        return [], "INITIAL_READ_ONLY"
    if scan.get("mode") == "initial_active_baseline":
        return errors + ["initial_baseline_not_allowlisted"], "BLOCKED"
    return errors, "BLOCKED"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--handoff", required=True)
    args = parser.parse_args()
    try:
        reg_raw = Path(args.registry).read_bytes()
        hand_raw = Path(args.handoff).read_bytes()
        registry = json.loads(reg_raw)
        handoff = json.loads(hand_raw)
        errors, mode = validate_prior(
            registry, handoff, git_blob_sha(reg_raw), git_blob_sha(hand_raw))
    except (OSError, ValueError, TypeError) as exc:
        errors, mode = ["input_error:" + str(exc)], "BLOCKED"
    print(json.dumps({
        "status": "PASS" if not errors else "BLOCKED",
        "scope": "PRIOR_BASELINE_READ_ONLY",
        "baseline_mode": mode,
        "authorizes_publication": False,
        "errors": errors
    }, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
