#!/usr/bin/env python3
"""Minimal integrity checks for compact data/snapshot.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(f"snapshot validation failed: {message}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="data/snapshot.json")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        fail(f"missing file: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if data.get("schema_version") != 1:
        fail("schema_version must be 1")
    trade_date = data.get("trade_date")
    if not trade_date:
        fail("trade_date is missing")

    market_state = data.get("market_state")
    if not isinstance(market_state, dict):
        fail("market_state must be present")
    if market_state.get("trade_date") != trade_date:
        fail("market_state.trade_date must match snapshot.trade_date")
    allowed_market_values = {
        "trend": {"bullish", "bearish", "transition", "unknown"},
        "breadth": {"strong", "weak", "neutral", "unknown"},
        "liquidity": {"high", "low", "normal", "unknown"},
        "risk_level": {"low", "medium", "high"},
    }
    for key, allowed in allowed_market_values.items():
        if market_state.get(key) not in allowed:
            fail(f"invalid market_state.{key}: {market_state.get(key)!r}")

    counts = data.get("counts") or {}
    universe = counts.get("universe_stocks") or 0
    candidate_count = counts.get("candidates") or 0
    industries = counts.get("industries") or 0

    if universe < 3000:
        fail(f"unexpected upstream universe size: {universe}")
    if industries < 50:
        fail(f"unexpected industry count: {industries}")

    candidates = data.get("candidates")
    if not isinstance(candidates, dict):
        fail("candidates must be an object")
    if len(candidates) != candidate_count:
        fail("counts.candidates does not match actual candidates length")
    if candidate_count == 0:
        fail("candidate universe is unexpectedly empty")
    if candidate_count > universe:
        fail("candidate count cannot exceed upstream universe")

    coverage = data.get("coverage") or {}
    thresholds = {
        "price_pct": 0.95,
        "fundamentals_pct": 0.80,
        "trend_pct": 0.90,
        "industry_mapping_pct": 0.80,
    }
    for key, threshold in thresholds.items():
        value = coverage.get(key)
        if not isinstance(value, (int, float)) or value < threshold:
            fail(f"{key}={value!r} < required {threshold:.0%}")

    required_candidate_fields = (
        "name",
        "price",
        "industry_code",
        "fundamentals",
        "price_structure",
    )
    for code, stock in candidates.items():
        missing = [key for key in required_candidate_fields if stock.get(key) is None]
        if missing:
            fail(f"candidate {code} missing fields: {missing}")

        fundamentals = stock.get("fundamentals") or {}
        if not fundamentals.get("report_date"):
            fail(f"candidate {code} missing report_date")

        structure = stock.get("price_structure") or {}
        if structure.get("position_pct") is None:
            fail(f"candidate {code} missing position_pct")

    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > 3.0:
        fail(f"snapshot is too large for V2 target: {size_mb:.2f} MB")

    print(
        "snapshot valid: "
        f"universe={universe} candidates={candidate_count} industries={industries} "
        f"market_risk={market_state.get('risk_level')} size={size_mb:.2f}MB"
    )


if __name__ == "__main__":
    main()
