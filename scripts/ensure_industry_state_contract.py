#!/usr/bin/env python3
"""Validate the current industry-state contract."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from contracts import YOY_UNIT

YOY_FIELDS = ("aggregate_revenue_yoy", "aggregate_parent_profit_yoy")


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="data/research/industry_state.json")
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

    print(
        f"industry state contract valid: yoy_unit={YOY_UNIT} "
        f"industries={len(industries)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
