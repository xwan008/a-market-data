#!/usr/bin/env python3
"""Migrate legacy industry_state.json into the current unit contract.

This is intentionally idempotent. Current files are left unchanged; only the
legacy schema-2 representation (aggregate YoY stored as decimal ratios) is
converted to percentage points.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from contracts import YOY_UNIT

CURRENT_SCHEMA_VERSION = 3
LEGACY_SCHEMA_VERSION = 2
YOY_FIELDS = (
    "aggregate_revenue_yoy",
    "aggregate_parent_profit_yoy",
)


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "path",
        nargs="?",
        default="data/research/industry_state.json",
    )
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        raise SystemExit(f"missing industry state: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = int(payload.get("schema_version") or 0)
    unit = payload.get("yoy_unit")

    if unit == YOY_UNIT:
        if schema_version < CURRENT_SCHEMA_VERSION:
            raise SystemExit(
                f"industry state declares {YOY_UNIT} but schema_version="
                f"{schema_version} < {CURRENT_SCHEMA_VERSION}"
            )
        print(
            f"industry state contract current: schema={schema_version} "
            f"yoy_unit={unit}"
        )
        return 0

    if unit is not None:
        raise SystemExit(f"unsupported industry YoY unit: {unit!r}")
    if schema_version != LEGACY_SCHEMA_VERSION:
        raise SystemExit(
            "cannot safely infer legacy YoY representation: "
            f"schema_version={schema_version} yoy_unit={unit!r}"
        )

    industries = payload.get("level3_profitability") or {}
    if not isinstance(industries, dict) or not industries:
        raise SystemExit("industry state has no level3_profitability data")

    converted_values = 0
    for item in industries.values():
        if not isinstance(item, dict):
            continue
        for field in YOY_FIELDS:
            value = item.get(field)
            if is_number(value):
                item[field] = float(value) * 100.0
                converted_values += 1

    payload["schema_version"] = CURRENT_SCHEMA_VERSION
    payload["yoy_unit"] = YOY_UNIT
    payload["unit_migration"] = {
        "from_schema_version": LEGACY_SCHEMA_VERSION,
        "from_yoy_unit": "decimal_ratio",
        "to_yoy_unit": YOY_UNIT,
        "converted_value_count": converted_values,
    }

    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"industry state migrated: schema={CURRENT_SCHEMA_VERSION} "
        f"yoy_unit={YOY_UNIT} converted_values={converted_values}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
