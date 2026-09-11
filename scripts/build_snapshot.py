#!/usr/bin/env python3
"""Build the compact V2 candidate snapshot from shared upstream data.

The Action owns deterministic data preparation and coarse risk filtering only.
It does not value companies, calculate target prices, score candidates, or rank
stocks. Those judgments belong to the single SKILL at formal-run time.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from snapshot_io import write_snapshot

MAX_PRICE = 120.0
MAX_PE = 30.0


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def compact_industries(raw: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for code, item in (raw.get("level3_profitability") or {}).items():
        result[code] = {
            "name": item.get("name"),
            "trend": item.get("trend"),
            "strength": item.get("strength"),
            "breadth": item.get("breadth"),
            "confidence": item.get("confidence"),
            "last_verified_at": item.get("last_verified_at"),
            "core_improving_breadth": item.get("core_improving_breadth"),
            "aggregate_revenue_yoy": item.get("aggregate_revenue_yoy"),
            "aggregate_parent_profit_yoy": item.get("aggregate_parent_profit_yoy"),
            "market_breadth": item.get("market_breadth"),
            "market_activity": item.get("market_activity"),
            "market_confirmation": item.get("market_confirmation"),
            "market_metrics": item.get("market_metrics"),
        }
    return result


def industry_allowed(item: dict[str, Any] | None) -> bool:
    if not item:
        return False
    trend = item.get("trend")
    breadth = item.get("breadth")
    return trend == "improving" or (
        trend == "stable" and breadth in {"divergent", "broad"}
    )


def company_allowed(raw: dict[str, Any]) -> bool:
    name = str(raw.get("name") or "").upper()
    if "ST" in name:
        return False

    price = raw.get("price")
    if not is_number(price) or price <= 0:
        return False
    if price > MAX_PRICE:
        return False

    fundamentals = raw.get("fundamentals") or {}
    if not fundamentals.get("report_date"):
        return False

    net_profit = fundamentals.get("net_profit")
    if not is_number(net_profit) or net_profit <= 0:
        return False

    pe_ttm = fundamentals.get("pe_ttm")
    pe_dynamic = fundamentals.get("pe_dynamic")
    if is_number(pe_ttm) and pe_ttm > MAX_PE:
        return False
    if is_number(pe_dynamic) and pe_dynamic > MAX_PE:
        return False

    if not any(
        is_number(fundamentals.get(key))
        for key in ("pe_ttm", "pe_dynamic", "pb", "market_cap")
    ):
        return False

    revenue_yoy = fundamentals.get("revenue_yoy")
    net_profit_yoy = fundamentals.get("net_profit_yoy")
    if (
        is_number(revenue_yoy)
        and is_number(net_profit_yoy)
        and revenue_yoy < -20
        and net_profit_yoy < -50
    ):
        return False

    trend = raw.get("trend") or {}
    if (trend.get("points") or 0) < 20:
        return False
    if not (trend.get("structure_60d") or {}):
        return False

    return True


def nearest_zone(
    zones: list[dict[str, Any]], price: float, *, side: str
) -> dict[str, Any] | None:
    candidates: list[tuple[float, dict[str, Any]]] = []
    for zone in zones:
        center = zone.get("center")
        if not is_number(center):
            continue
        if side == "below" and center > price * 1.01:
            continue
        if side == "above" and center < price * 0.99:
            continue
        candidates.append((abs(center - price), zone))

    if not candidates:
        return None

    zone = min(candidates, key=lambda x: x[0])[1]
    keep = {
        "low": zone.get("low"),
        "high": zone.get("high"),
        "center": zone.get("center"),
    }
    for key in ("touches", "volume_share_pct", "last_date", "last_touch_date"):
        if zone.get(key) is not None:
            keep[key] = zone.get(key)
    return keep


def compact_candidate(raw: dict[str, Any]) -> dict[str, Any]:
    price = float(raw["price"])
    prev_close = raw.get("prev_close")
    day_change_pct = None
    if is_number(prev_close) and prev_close != 0:
        day_change_pct = (price / prev_close - 1) * 100

    fundamentals = raw.get("fundamentals") or {}
    trend = raw.get("trend") or {}
    structure = trend.get("structure_60d") or {}
    evolution = structure.get("structure_evolution") or {}

    return {
        "name": raw.get("name"),
        "price": raw.get("price"),
        "day_change_pct": day_change_pct,
        "industry_code": raw.get("sw_level3_code"),
        "industry_name": raw.get("sw_level3_name"),
        "fundamentals": {
            "report_date": fundamentals.get("report_date"),
            "pe_ttm": fundamentals.get("pe_ttm"),
            "pe_dynamic": fundamentals.get("pe_dynamic"),
            "pb": fundamentals.get("pb"),
            "market_cap": fundamentals.get("market_cap"),
            "roe": fundamentals.get("roe"),
            "revenue_yoy": fundamentals.get("revenue_yoy"),
            "net_profit_yoy": fundamentals.get("net_profit_yoy"),
            "deduct_basic_eps_yoy": fundamentals.get("deduct_basic_eps_yoy"),
            "operating_cashflow_per_share": fundamentals.get(
                "operating_cashflow_per_share"
            ),
            "gross_margin": fundamentals.get("gross_margin"),
            "net_profit": fundamentals.get("net_profit"),
        },
        "price_structure": {
            "high_20d": trend.get("high_20d"),
            "low_20d": trend.get("low_20d"),
            "close_change_5d_pct": trend.get("close_change_5d_pct"),
            "close_change_20d_pct": trend.get("close_change_20d_pct"),
            "high_60d": structure.get("high"),
            "low_60d": structure.get("low"),
            "ma20": structure.get("ma20"),
            "ma60": structure.get("ma60"),
            "position_pct": structure.get("position_pct"),
            "trend_state": evolution.get("trend_state"),
            "break_state": evolution.get("break_state"),
            "invalidation": evolution.get("invalidation"),
            "nearest_support": nearest_zone(
                structure.get("support_zones") or [], price, side="below"
            ),
            "nearest_volume_zone": nearest_zone(
                structure.get("volume_profile_zones") or [], price, side="below"
            ),
            "nearest_resistance": nearest_zone(
                structure.get("resistance_zones") or [], price, side="above"
            ),
        },
    }


def build_snapshot(source: Path) -> dict[str, Any]:
    shard_dir = source / "data" / "shards"
    shard_paths = sorted(shard_dir.glob("*.json"))
    if not shard_paths:
        raise RuntimeError(f"no upstream shards found in {shard_dir}")

    industry_path = source / "data" / "research" / "industry_state.json"
    if not industry_path.exists():
        raise RuntimeError("industry_state.json is required for V2 prefilter")

    industry_raw = load_json(industry_path)
    industries = compact_industries(industry_raw)

    trade_dates: set[str] = set()
    statuses: set[str] = set()
    generated_times: list[str] = []
    universe_count = 0
    price_count = 0
    fundamentals_count = 0
    trend_count = 0
    mapping_count = 0
    candidates: dict[str, Any] = {}

    for shard_path in shard_paths:
        shard = load_json(shard_path)
        if shard.get("trade_date"):
            trade_dates.add(str(shard["trade_date"]))
        if shard.get("market_status"):
            statuses.add(str(shard["market_status"]))
        if shard.get("generated_at"):
            generated_times.append(str(shard["generated_at"]))

        for code, raw in (shard.get("stocks") or {}).items():
            universe_count += 1
            price = raw.get("price")
            if is_number(price) and price > 0:
                price_count += 1

            fundamentals = raw.get("fundamentals") or {}
            if fundamentals.get("report_date") and any(
                is_number(fundamentals.get(key))
                for key in ("pe_ttm", "pe_dynamic", "pb", "net_profit")
            ):
                fundamentals_count += 1

            trend = raw.get("trend") or {}
            if (trend.get("points") or 0) >= 20 and trend.get("last_date"):
                trend_count += 1

            industry_code = raw.get("sw_level3_code")
            if raw.get("industry_mapping_status") == "mapped" and industry_code:
                mapping_count += 1

            if not industry_allowed(industries.get(industry_code)):
                continue
            if not company_allowed(raw):
                continue

            candidates[code] = compact_candidate(raw)

    if len(trade_dates) != 1:
        raise RuntimeError(f"upstream shards do not share one trade_date: {sorted(trade_dates)}")
    if universe_count == 0:
        raise RuntimeError("empty upstream universe")

    trade_date = next(iter(trade_dates))
    upstream_generated_at = max(generated_times) if generated_times else None

    return {
        "schema_version": 1,
        "generated_at": upstream_generated_at,
        "trade_date": trade_date,
        "market_status": next(iter(statuses)) if len(statuses) == 1 else "mixed",
        "source": {
            "repository": "xwan008/a-share-market-data",
            "ref": "main",
            "latest_upstream_generated_at": upstream_generated_at,
            "industry_state_generated_at": industry_raw.get("generated_at"),
        },
        "prefilter": {
            "purpose": "deterministic coarse risk reduction only; no valuation or ranking",
            "industry": "improving OR stable with divergent/broad breadth",
            "company": "non-ST, 0 < price <= 120, positive net profit, PE-TTM <= 30 when available, dynamic PE <= 30 when available, usable valuation fields, >=20 trend points, no simultaneous severe revenue/profit collapse",
        },
        "counts": {
            "universe_stocks": universe_count,
            "candidates": len(candidates),
            "industries": len(industries),
            "shards": len(shard_paths),
        },
        "coverage": {
            "price_pct": price_count / universe_count,
            "fundamentals_pct": fundamentals_count / universe_count,
            "trend_pct": trend_count / universe_count,
            "industry_mapping_pct": mapping_count / universe_count,
        },
        "industry_state": {
            "status": industry_raw.get("status"),
            "baseline_trade_date": industry_raw.get("baseline_trade_date"),
            "generated_at": industry_raw.get("generated_at"),
            "level3": industries,
        },
        "candidates": candidates,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="path to upstream repository")
    parser.add_argument("--output", default="data/snapshot.json")
    args = parser.parse_args()

    snapshot = build_snapshot(Path(args.source).resolve())
    output = Path(args.output)
    write_snapshot(output, snapshot)

    print(
        f"snapshot ready: trade_date={snapshot['trade_date']} "
        f"universe={snapshot['counts']['universe_stocks']} "
        f"candidates={snapshot['counts']['candidates']} "
        f"industries={snapshot['counts']['industries']}"
    )


if __name__ == "__main__":
    main()
