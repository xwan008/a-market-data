#!/usr/bin/env python3
"""Build the single V2 market snapshot from the shared upstream repository.

This script intentionally performs deterministic data shaping only. It does not
make investment decisions, rank stocks, or fetch public-web research.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def git_sha(repo: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:
        return None


def compact_structure(trend: dict[str, Any]) -> dict[str, Any] | None:
    structure = trend.get("structure_60d") or {}
    if not structure:
        return None

    evolution = structure.get("structure_evolution") or {}
    return {
        "points": structure.get("points"),
        "high": structure.get("high"),
        "low": structure.get("low"),
        "close_change_pct": structure.get("close_change_pct"),
        "ma20": structure.get("ma20"),
        "ma60": structure.get("ma60"),
        "position_pct": structure.get("position_pct"),
        "trend_state": evolution.get("trend_state"),
        "break_state": evolution.get("break_state"),
        "invalidation": evolution.get("invalidation"),
        "latest_high": evolution.get("latest_high"),
        "latest_low": evolution.get("latest_low"),
        "support_zones": (structure.get("support_zones") or [])[:3],
        "resistance_zones": (structure.get("resistance_zones") or [])[:3],
        "dense_price_zones": (structure.get("dense_price_zones") or [])[:3],
        "volume_profile_zones": (structure.get("volume_profile_zones") or [])[:3],
    }


def compact_fundamentals(raw: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "valuation_date",
        "pe_dynamic",
        "pe_ttm",
        "pb",
        "market_cap",
        "report_date",
        "notice_date",
        "roe",
        "revenue_yoy",
        "net_profit_yoy",
        "deduct_net_profit_yoy",
        "operating_cashflow_per_share",
        "gross_margin",
        "revenue",
        "net_profit",
        "basic_eps",
        "deduct_basic_eps",
        "deduct_basic_eps_prev_year",
        "deduct_basic_eps_yoy",
    )
    return {key: raw.get(key) for key in keys}


def compact_industry_state(raw: dict[str, Any]) -> dict[str, Any]:
    profitability = raw.get("level3_profitability") or {}
    industries: dict[str, Any] = {}
    for code, item in profitability.items():
        industries[code] = {
            "code": item.get("code", code),
            "name": item.get("name"),
            "trend": item.get("trend"),
            "strength": item.get("strength"),
            "breadth": item.get("breadth"),
            "confidence": item.get("confidence"),
            "leading_variables": item.get("leading_variables") or [],
            "last_verified_at": item.get("last_verified_at"),
            "company_count": item.get("company_count_with_paired_h1"),
            "core_improving_breadth": item.get("core_improving_breadth"),
            "aggregate_revenue_yoy": item.get("aggregate_revenue_yoy"),
            "aggregate_parent_profit_yoy": item.get("aggregate_parent_profit_yoy"),
        }
    return {
        "status": raw.get("status"),
        "baseline_trade_date": raw.get("baseline_trade_date"),
        "generated_at": raw.get("generated_at"),
        "level3": industries,
    }


def build_snapshot(source: Path) -> dict[str, Any]:
    shard_dir = source / "data" / "shards"
    shard_paths = sorted(shard_dir.glob("*.json"))
    if not shard_paths:
        raise RuntimeError(f"no upstream shards found in {shard_dir}")

    stocks: dict[str, Any] = {}
    trade_dates: set[str] = set()
    statuses: set[str] = set()
    generated_times: list[str] = []

    for shard_path in shard_paths:
        shard = load_json(shard_path)
        if shard.get("trade_date"):
            trade_dates.add(str(shard["trade_date"]))
        if shard.get("market_status"):
            statuses.add(str(shard["market_status"]))
        if shard.get("generated_at"):
            generated_times.append(str(shard["generated_at"]))

        for code, raw in (shard.get("stocks") or {}).items():
            trend = raw.get("trend") or {}
            stocks[code] = {
                "name": raw.get("name"),
                "price": raw.get("price"),
                "prev_close": raw.get("prev_close"),
                "open": raw.get("open"),
                "high": raw.get("high"),
                "low": raw.get("low"),
                "price_time": raw.get("price_time"),
                "confidence": raw.get("confidence"),
                "fundamentals": compact_fundamentals(raw.get("fundamentals") or {}),
                "trend": {
                    "points": trend.get("points"),
                    "last_date": trend.get("last_date"),
                    "last_close": trend.get("last_close"),
                    "history_confidence": trend.get("history_confidence"),
                    "high_20d": trend.get("high_20d"),
                    "low_20d": trend.get("low_20d"),
                    "close_change_5d_pct": trend.get("close_change_5d_pct"),
                    "close_change_20d_pct": trend.get("close_change_20d_pct"),
                    "last5": trend.get("last5") or [],
                    "structure_60d": compact_structure(trend),
                },
                "sw_level3_code": raw.get("sw_level3_code"),
                "sw_level3_name": raw.get("sw_level3_name"),
                "industry_mapping_status": raw.get("industry_mapping_status"),
            }

    if len(trade_dates) != 1:
        raise RuntimeError(f"upstream shards do not share one trade_date: {sorted(trade_dates)}")

    industry_path = source / "data" / "research" / "industry_state.json"
    industry_state = None
    if industry_path.exists():
        industry_state = compact_industry_state(load_json(industry_path))

    trade_date = next(iter(trade_dates))
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trade_date": trade_date,
        "market_status": next(iter(statuses)) if len(statuses) == 1 else "mixed",
        "source": {
            "repository": "xwan008/a-share-market-data",
            "commit": git_sha(source),
            "latest_upstream_generated_at": max(generated_times) if generated_times else None,
            "note": "source commit is audit metadata only; V2 does not require an artifact bound to this SHA",
        },
        "counts": {
            "shards": len(shard_paths),
            "stocks": len(stocks),
            "industries": len((industry_state or {}).get("level3", {})),
        },
        "industry_state": industry_state,
        "stocks": stocks,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="path to upstream repository")
    parser.add_argument("--output", default="data/snapshot.json")
    args = parser.parse_args()

    snapshot = build_snapshot(Path(args.source).resolve())
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")

    print(
        f"snapshot ready: trade_date={snapshot['trade_date']} "
        f"stocks={snapshot['counts']['stocks']} industries={snapshot['counts']['industries']}"
    )


if __name__ == "__main__":
    main()
