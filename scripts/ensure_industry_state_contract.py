#!/usr/bin/env python3
"""Validate the current industry-state contract."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from contracts import YOY_UNIT

YOY_FIELDS = ("aggregate_revenue_yoy", "aggregate_parent_profit_yoy")
BUYABILITY_LABELS = {"favorable", "balanced", "stretched", "unknown"}
BUYABILITY_NUMERIC_FIELDS = (
    "score",
    "components.valuation_attractiveness",
    "components.price_attractiveness",
    "components.earnings_support",
    "metrics.median_positive_pe",
    "metrics.median_60d_position_pct",
    "metrics.median_20d_change_pct",
    "metrics.median_core_profit_yoy",
    "metrics.core_profit_positive_share",
    "metrics.median_roe",
    "metrics.positive_operating_cashflow_share",
)


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def nested_get(item: dict[str, Any], path: str) -> Any:
    value: Any = item
    for key in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def validate_buyability(payload: dict[str, Any], industries: dict[str, Any], *, required: bool) -> None:
    context = payload.get("buyability_context")
    if context is None:
        if required:
            raise SystemExit("industry state is missing required buyability_context")
        return
    if not isinstance(context, dict):
        raise SystemExit("buyability_context must be an object")
    if context.get("status") != "valid":
        raise SystemExit(f"buyability_context.status must be valid, got {context.get('status')!r}")
    if str(context.get("trade_date") or "") != str(payload.get("baseline_trade_date") or ""):
        raise SystemExit("buyability_context.trade_date must match baseline_trade_date")
    if "ordering context only" not in str(context.get("usage") or ""):
        raise SystemExit("buyability_context.usage must identify Stage 0 ordering-only semantics")

    valid_count = 0
    for code, item in industries.items():
        buyability = item.get("buyability")
        if buyability is None:
            if required:
                raise SystemExit(f"industry {code} is missing buyability")
            continue
        if not isinstance(buyability, dict):
            raise SystemExit(f"industry {code} buyability must be an object")
        status = buyability.get("status")
        if status not in {"valid", "unavailable"}:
            raise SystemExit(f"industry {code} buyability.status is invalid: {status!r}")
        label = buyability.get("label")
        if label not in BUYABILITY_LABELS:
            raise SystemExit(f"industry {code} buyability.label is invalid: {label!r}")
        if status == "valid":
            valid_count += 1
        for field in BUYABILITY_NUMERIC_FIELDS:
            value = nested_get(buyability, field)
            if value is not None and not is_number(value):
                raise SystemExit(f"industry {code} buyability {field} must be numeric or null")

    if required and valid_count == 0:
        raise SystemExit("buyability is required but no industry has valid buyability")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="data/research/industry_state.json")
    parser.add_argument("--require-buyability", action="store_true")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        raise SystemExit(f"missing industry state: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("yoy_unit") != YOY_UNIT:
        raise SystemExit(
            f"industry_state.yoy_unit must be {YOY_UNIT}, got {payload.get('yoy_unit')!r}"
        )
    industries = payload.get("level3_profitability")
    if not isinstance(industries, dict) or not industries:
        raise SystemExit("industry state has no level3_profitability data")
    for code, item in industries.items():
        if not isinstance(item, dict):
            raise SystemExit(f"industry {code} must be an object")
        for field in YOY_FIELDS:
            value = item.get(field)
            if value is not None and not is_number(value):
                raise SystemExit(f"industry {code} {field} must be numeric or null")

    validate_buyability(payload, industries, required=args.require_buyability)
    suffix = " buyability=required" if args.require_buyability else ""
    print(
        f"industry state contract valid: yoy_unit={YOY_UNIT} "
        f"industries={len(industries)}{suffix}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
