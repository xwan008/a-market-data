#!/usr/bin/env python3
"""Minimal integrity checks for data/snapshot.json."""

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
    if not data.get("trade_date"):
        fail("trade_date is missing")

    stocks = data.get("stocks")
    if not isinstance(stocks, dict) or len(stocks) < 3000:
        fail(f"unexpected stock count: {0 if not isinstance(stocks, dict) else len(stocks)}")

    usable_price = 0
    usable_fundamentals = 0
    usable_trend = 0
    mapped_industry = 0

    for stock in stocks.values():
        if isinstance(stock.get("price"), (int, float)) and stock["price"] > 0:
            usable_price += 1

        fundamentals = stock.get("fundamentals") or {}
        if fundamentals.get("report_date") and (
            fundamentals.get("pe_ttm") is not None
            or fundamentals.get("pb") is not None
            or fundamentals.get("net_profit") is not None
        ):
            usable_fundamentals += 1

        trend = stock.get("trend") or {}
        if (trend.get("points") or 0) >= 20 and trend.get("last_date"):
            usable_trend += 1

        if stock.get("industry_mapping_status") == "mapped" and stock.get("sw_level3_code"):
            mapped_industry += 1

    total = len(stocks)
    thresholds = {
        "price": (usable_price, 0.95),
        "fundamentals": (usable_fundamentals, 0.80),
        "trend": (usable_trend, 0.90),
        "industry_mapping": (mapped_industry, 0.80),
    }

    for name, (count, ratio) in thresholds.items():
        actual = count / total
        if actual < ratio:
            fail(f"{name} coverage {actual:.1%} < required {ratio:.0%}")

    counts = data.get("counts") or {}
    if counts.get("stocks") != total:
        fail("counts.stocks does not match actual stocks length")

    print(
        "snapshot valid: "
        f"stocks={total} price={usable_price/total:.1%} "
        f"fundamentals={usable_fundamentals/total:.1%} "
        f"trend={usable_trend/total:.1%} industry={mapped_industry/total:.1%}"
    )


if __name__ == "__main__":
    main()
