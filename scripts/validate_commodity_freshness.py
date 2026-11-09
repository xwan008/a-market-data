#!/usr/bin/env python3
"""Read-only, point-in-time freshness check for active commodity trend anchors.

The evidence file MUST be collected and independently sourced at each run.
This checker compares timestamps and provenance; it cannot fetch prices or
prove that a supplied market-source assertion is true.
"""
import argparse
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import re
from urllib.parse import urlparse

BEIJING = timezone(timedelta(hours=8))
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CLOSE_BASIS = {"SETTLEMENT", "OFFICIAL_CLOSE", "VERIFIED_DAILY_FIX"}
SESSION_STATES = {"OPEN", "DAILY_BREAK", "WEEKEND", "HOLIDAY", "CLOSED", "UNKNOWN"}


def _time(value, asof=None):
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        if asof is not None and parsed > asof:
            return None
        return parsed
    except (TypeError, ValueError, OverflowError):
        return None


def _source(value):
    if not isinstance(value, str):
        return False
    url = urlparse(value)
    return url.scheme in {"https", "http"} and bool(url.netloc)


def _day(value):
    if not isinstance(value, str) or not DATE.fullmatch(value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _reference(value, asof):
    return (isinstance(value, dict)
            and _day(value.get("trade_date")) is not None
            and _day(value["trade_date"]) <= asof.astimezone(BEIJING).date()
            and value.get("price_basis") in CLOSE_BASIS
            and _source(value.get("source"))
            and _time(value.get("available_at"), asof) is not None)


def _quote(value, asof):
    return (isinstance(value, dict)
            and value.get("price_basis") == "INTRADAY"
            and _source(value.get("source"))
            and _time(value.get("observed_at"), asof) is not None)


def evaluate(registry, evidence, mode):
    """Return audit JSON; nonempty errors mean invalid evidence or stale close."""
    if mode not in {"morning", "close"}:
        raise ValueError("mode must be morning or close")
    errors, results = [], []
    asof = _time(evidence.get("asof"))
    if asof is None:
        return {"ok": False, "mode": mode, "errors": ["asof_invalid"], "results": []}
    markets = evidence.get("markets")
    if not isinstance(markets, list):
        return {"ok": False, "mode": mode, "errors": ["markets_missing"], "results": []}
    provided = {}
    for row in markets:
        if not isinstance(row, dict) or not isinstance(row.get("episode_id"), str):
            errors.append("market_evidence_invalid")
            continue
        key = row["episode_id"]
        if key in provided:
            errors.append(f"{key}:duplicate_evidence")
        provided[key] = row

    trends = registry.get("trends")
    if not isinstance(trends, list):
        return {"ok": False, "mode": mode, "errors": errors + ["trends_missing"],
                "results": []}
    active = [x for x in trends if isinstance(x, dict) and x.get("trend_basis") == "COMMODITY"]
    active_ids = {x.get("episode_id") for x in active}
    for extra in provided.keys() - active_ids:
        errors.append(f"{extra}:unexpected_evidence")

    for trend in active:
        key = trend.get("episode_id")
        row = provided.get(key)
        result = {"episode_id": key, "completed_status": "UNVERIFIED",
                  "quote_status": "UNVERIFIED"}
        results.append(result)
        if row is None:
            errors.append(f"{key}:evidence_missing")
            continue
        anchor = trend.get("commodity_anchor") or {}
        if not anchor.get("instrument") or row.get("instrument") != anchor.get("instrument"):
            errors.append(f"{key}:instrument_mismatch")
            continue
        state = row.get("market_status")
        result["market_status"] = state
        checked = _time(row.get("calendar_checked_at"), asof)
        if (state not in SESSION_STATES or state == "UNKNOWN"
                or not _source(row.get("calendar_source"))
                or checked is None
                or checked.astimezone(BEIJING).date() != asof.astimezone(BEIJING).date()):
            errors.append(f"{key}:session_calendar_unverified")
        current = row.get("latest_completed")
        if not _reference(current, asof):
            errors.append(f"{key}:latest_completed_unverified")
            continue
        previous = ((trend.get("confirmation_audit") or {})
                    .get("commodity_price_review") or {}).get("completed_reference")
        if previous is not None and _day(previous.get("trade_date")) is None:
            errors.append(f"{key}:registry_completed_reference_invalid")
            continue
        latest_day = _day(current["trade_date"])
        previous_day = _day(previous["trade_date"]) if previous else None
        result["latest_completed_date"] = current["trade_date"]
        result["registry_completed_date"] = previous.get("trade_date") if previous else None
        if previous_day is None or previous_day < latest_day:
            result["completed_status"] = ("NEW_COMPLETED_SESSION" if mode == "morning"
                                          else "STALE_COMPLETED_REFERENCE")
            if mode == "close":
                errors.append(f"{key}:stale_completed_reference")
        elif previous_day > latest_day:
            result["completed_status"] = "EVIDENCE_BEHIND_REGISTRY"
            errors.append(f"{key}:evidence_behind_registry")
        else:
            result["completed_status"] = "CURRENT"

        latest_quote = row.get("latest_quote")
        if latest_quote is None:
            if state == "OPEN":
                result["quote_status"] = "UNAVAILABLE"
                errors.append(f"{key}:open_quote_unverified")
            else:
                result["quote_status"] = "NOT_REQUIRED_CLOSED"
            continue
        if not _quote(latest_quote, asof):
            errors.append(f"{key}:latest_quote_invalid")
            continue
        existing_quote = ((trend.get("confirmation_audit") or {})
                          .get("commodity_price_review") or {}).get("current_quote")
        existing_time = _time((existing_quote or {}).get("observed_at"))
        latest_time = _time(latest_quote["observed_at"])
        result["latest_quote_at"] = latest_quote["observed_at"]
        result["registry_quote_at"] = (existing_quote or {}).get("observed_at")
        if existing_time is None or existing_time < latest_time:
            result["quote_status"] = ("NEW_QUOTE" if mode == "morning" else "STALE_QUOTE")
            if mode == "close":
                errors.append(f"{key}:stale_intraday_quote")
        elif existing_time > latest_time:
            result["quote_status"] = "EVIDENCE_BEHIND_REGISTRY"
            errors.append(f"{key}:quote_evidence_behind_registry")
        else:
            result["quote_status"] = "CURRENT"

    return {"ok": not errors, "asof": asof.isoformat(), "mode": mode,
            "errors": errors, "results": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--mode", required=True, choices=("morning", "close"))
    args = parser.parse_args()
    report = evaluate(json.loads(args.registry.read_text(encoding="utf-8")),
                      json.loads(args.evidence.read_text(encoding="utf-8")),
                      args.mode)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["ok"] else 2)


if __name__ == "__main__":
    main()
