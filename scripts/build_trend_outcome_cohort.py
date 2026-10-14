#!/usr/bin/env python3
"""Freeze a prospective trend-evaluation cohort without invented future returns.

Historical first_seen is descriptive only; the prospective evaluation starts
from the archived as_of trade date and fixed input snapshots.
"""
import argparse
import json
import re
from pathlib import Path

SHA = re.compile(r"^[0-9a-f]{40}$")


def build(registry, registry_sha, quote_sha, industry_sha, archive_created_trade_date=None):
    if not all(isinstance(x, str) and SHA.fullmatch(x)
               for x in (registry_sha, quote_sha, industry_sha)):
        raise ValueError("All frozen source blob SHA values must be real 40-char hex")
    if registry.get("status") != "COMPLETE":
        raise ValueError("Incomplete registry is not a valid prospective cohort")
    day = registry.get("trade_date")
    if not isinstance(day, str):
        raise ValueError("trade_date missing")
    same_day_freeze = archive_created_trade_date == day
    themes = []
    seen = set()
    for t in registry.get("trends", []):
        name = t.get("trend_name")
        if not name or name in seen:
            raise ValueError("missing or duplicate trend name")
        seen.add(name)
        themes.append({
            "trend_name": name,
            "historical_first_seen_trade_date": t.get("first_seen_trade_date"),
            "prospective_baseline_date": day,
            "baseline_trend_state": t.get("trend_state"),
            "baseline_market_state": t.get("market_state"),
            "baseline_lifecycle_status": t.get("lifecycle_status"),
            "baseline_priority": t.get("in_new_position_priority") is True,
            "frozen_industry_codes": t.get("industry_codes") or [],
            "horizons_trading_days": [5, 10, 20],
            "future_outcomes_status": "RIGHT_CENSORED_PENDING_FUTURE_QUOTES",
            "returns": None,
            "relative_returns": None,
            "true_invalidation_delay_days": None,
        })
    return {
        "schema_version": 1,
        "result_kind": "trend_outcome_cohort",
        "as_of_trade_date": day,
        "source_refs": {
            "registry_blob_sha": registry_sha,
            "quotes_blob_sha": quote_sha,
            "company_industry_index_blob_sha": industry_sha,
        },
        "prospective_only": same_day_freeze,
        "cohort_origin": ("SAME_DAY_ARCHIVED_REQUIRES_TIMESTAMP_VERIFICATION"
                          if same_day_freeze else "RETROSPECTIVE_BASELINE_REFERENCE_ONLY"),
        "archive_created_trade_date": archive_created_trade_date,
        "future_data_not_used": True,
        "source_dates_verified": False,
        "source_date_verification_required_before_returns": True,
        "cohort_size": len(themes),
        "themes": themes,
        "limitations": [
            "Historical first_seen or retroactive archive creation does not establish a genuinely prospective sample.",
            "No 5/10/20-day performance claim until actual future completed quotes.",
            "Dates of underlying quote and company-index snapshots must be separately verified before evaluation.",
            "Fixed company membership and baseline prices must be recovered "
            "from the frozen source versions before computing outcomes.",
            "Discovery timeliness cannot be inferred from historical first_seen alone.",
            "The current model does not validate sector earnings or actual investment PnL.",
        ],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--registry", required=True)
    p.add_argument("--registry-blob-sha", required=True)
    p.add_argument("--quotes-blob-sha", required=True)
    p.add_argument("--industry-index-blob-sha", required=True)
    p.add_argument("--archive-created-trade-date", help="Actual date the snapshot archive is created")
    p.add_argument("--output")
    args = p.parse_args()
    try:
        registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
        result = build(registry, args.registry_blob_sha,
                       args.quotes_blob_sha, args.industry_index_blob_sha,
                       args.archive_created_trade_date)
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}, ensure_ascii=False))
        return 1
    data = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(data, encoding="utf-8")
    print(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
