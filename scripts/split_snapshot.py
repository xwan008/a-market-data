#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


RUNTIME_SCHEMA_VERSION = 3
RUNTIME_FORMAT = "screening_details_v3"

INDUSTRY_COLUMNS = [
    "code",
    "name",
    "trend",
    "strength",
    "breadth",
    "confidence",
    "core_improving_breadth",
    "aggregate_revenue_yoy",
    "aggregate_parent_profit_yoy",
    "market_breadth",
    "market_activity",
    "market_confirmation",
]

SCREENING_COLUMNS = [
    "code",
    "name",
    "price",
    "industry_code",
    "pe_ttm",
    "pe_dynamic",
    "roe",
    "revenue_yoy",
    "net_profit_yoy",
    "close_change_20d_pct",
    "position_pct",
    "trend_state",
    "break_state",
    "support_center",
    "resistance_center",
    "invalidation_price",
    "invalidation_direction",
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write human/tool-readable multiline JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_row_json(
    path: Path,
    header: dict[str, Any],
    columns: list[str],
    rows: list[list[Any]],
) -> None:
    """Write valid JSON with one compact array record per source line.

    Repeated object keys dominate connector payload size. A shared columns array plus
    one row per line keeps deterministic line-window reads stable while preserving
    explicit schema semantics.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["{"]
    for key, value in header.items():
        lines.append(
            f"  {json.dumps(key, ensure_ascii=False)}: "
            f"{json.dumps(value, ensure_ascii=False, separators=(',', ':'))},"
        )
    lines.append(
        '  "columns": '
        + json.dumps(columns, ensure_ascii=False, separators=(",", ":"))
        + ","
    )
    lines.append('  "rows": [')
    for index, row in enumerate(rows):
        suffix = "," if index < len(rows) - 1 else ""
        lines.append(
            "    "
            + json.dumps(row, ensure_ascii=False, separators=(",", ":"))
            + suffix
        )
    lines.append("  ]")
    lines.append("}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def zone_center(zone: Any) -> Any:
    if not isinstance(zone, dict):
        return None
    center = zone.get("center")
    return center if is_number(center) else None


def invalidation_parts(value: Any) -> tuple[Any, Any]:
    if not isinstance(value, dict):
        return None, None
    price = value.get("price")
    direction = value.get("direction")
    return (price if is_number(price) else None, direction)


def compact_industry(code: str, raw: dict[str, Any]) -> list[Any]:
    return [
        code,
        raw.get("name"),
        raw.get("trend"),
        raw.get("strength"),
        raw.get("breadth"),
        raw.get("confidence"),
        raw.get("core_improving_breadth"),
        raw.get("aggregate_revenue_yoy"),
        raw.get("aggregate_parent_profit_yoy"),
        raw.get("market_breadth"),
        raw.get("market_activity"),
        raw.get("market_confirmation"),
    ]


def compact_screening_candidate(code: str, raw: dict[str, Any]) -> list[Any]:
    fundamentals = raw.get("fundamentals") or {}
    structure = raw.get("price_structure") or {}
    invalidation_price, invalidation_direction = invalidation_parts(
        structure.get("invalidation")
    )
    return [
        code,
        raw.get("name"),
        raw.get("price"),
        raw.get("industry_code"),
        fundamentals.get("pe_ttm"),
        fundamentals.get("pe_dynamic"),
        fundamentals.get("roe"),
        fundamentals.get("revenue_yoy"),
        fundamentals.get("net_profit_yoy"),
        structure.get("close_change_20d_pct"),
        structure.get("position_pct"),
        structure.get("trend_state"),
        structure.get("break_state"),
        zone_center(structure.get("nearest_support")),
        zone_center(structure.get("nearest_resistance")),
        invalidation_price,
        invalidation_direction,
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", default="data/snapshot.json")
    parser.add_argument("--output-dir", default="data/runtime")
    # Retained for CLI compatibility with the previous workflow.
    parser.add_argument("--shard-size", type=int, default=20)
    args = parser.parse_args()

    snapshot_path = Path(args.input)
    output_dir = Path(args.output_dir)
    snapshot = load_json(snapshot_path)

    candidates = snapshot.get("candidates") or {}
    expected = int((snapshot.get("counts") or {}).get("candidates") or 0)
    if not isinstance(candidates, dict) or not candidates:
        raise SystemExit("snapshot.candidates must be a non-empty object")
    if len(candidates) != expected:
        raise SystemExit(
            f"candidate count mismatch: expected={expected} actual={len(candidates)}"
        )

    industry_state = snapshot.get("industry_state") or {}
    level3 = industry_state.get("level3") or {}
    if not isinstance(level3, dict) or not level3:
        raise SystemExit("snapshot.industry_state.level3 must be a non-empty object")

    trade_date = snapshot.get("trade_date")
    if not trade_date:
        raise SystemExit("snapshot.trade_date is required")

    candidate_codes = list(candidates.keys())
    if len(candidate_codes) != len(set(candidate_codes)):
        raise SystemExit("duplicate candidate codes detected")

    missing_industry_codes = sorted(
        {
            str(raw.get("industry_code"))
            for raw in candidates.values()
            if not raw.get("industry_code") or raw.get("industry_code") not in level3
        }
    )
    if missing_industry_codes:
        sample = ",".join(missing_industry_codes[:10])
        raise SystemExit(
            f"candidate industry mapping incomplete: count={len(missing_industry_codes)} "
            f"sample={sample}"
        )

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    industry_state_filename = "industry_state_compact.json"
    industry_rows = [
        compact_industry(code, raw)
        for code, raw in sorted(level3.items(), key=lambda item: item[0])
    ]
    write_row_json(
        output_dir / industry_state_filename,
        {
            "schema_version": RUNTIME_SCHEMA_VERSION,
            "trade_date": trade_date,
            "industry_count": len(industry_rows),
        },
        INDUSTRY_COLUMNS,
        industry_rows,
    )

    details_dir = output_dir / "details"
    details_dir.mkdir(parents=True, exist_ok=True)
    screening_rows: list[list[Any]] = []

    for code, raw in candidates.items():
        detail_path = details_dir / f"{code}.json"
        write_json(
            detail_path,
            {
                "schema_version": RUNTIME_SCHEMA_VERSION,
                "trade_date": trade_date,
                "code": code,
                "candidate": raw,
            },
        )
        screening_rows.append(compact_screening_candidate(code, raw))

    screening_rows.sort(key=lambda row: str(row[0] or ""))
    screening_filename = "screening_snapshot.json"
    write_row_json(
        output_dir / screening_filename,
        {
            "schema_version": RUNTIME_SCHEMA_VERSION,
            "trade_date": trade_date,
            "source_candidate_count": len(candidates),
            "screening_count": len(screening_rows),
            "detail_count": len(screening_rows),
        },
        SCREENING_COLUMNS,
        screening_rows,
    )

    meta_snapshot = {
        key: value
        for key, value in snapshot.items()
        if key not in {"candidates", "industry_state"}
    }
    meta_snapshot["industry_state"] = {
        key: value for key, value in industry_state.items() if key != "level3"
    }

    validation = {
        "status": "passed",
        "schema_version": RUNTIME_SCHEMA_VERSION,
        "trade_date": trade_date,
        "candidate_codes_unique": True,
        "source_candidate_count_matches_snapshot": len(candidates) == expected,
        "screening_count_matches_source": len(screening_rows) == len(candidates),
        "detail_count_matches_screening": len(screening_rows) == len(candidates),
        "industry_count_matches_snapshot": len(industry_rows) == len(level3),
        "industry_mapping_complete": not missing_industry_codes,
    }

    meta = {
        "schema_version": RUNTIME_SCHEMA_VERSION,
        "runtime_format": RUNTIME_FORMAT,
        "snapshot": meta_snapshot,
        "source_candidate_count": len(candidates),
        "screening_count": len(screening_rows),
        "detail_count": len(screening_rows),
        "industry_count": len(industry_rows),
        "industry_state_file": f"{output_dir.as_posix()}/{industry_state_filename}",
        "screening_file": f"{output_dir.as_posix()}/{screening_filename}",
        "detail_file_template": f"{output_dir.as_posix()}/details/{{code}}.json",
        "screening_columns": SCREENING_COLUMNS,
        "industry_columns": INDUSTRY_COLUMNS,
        "runtime_validation": validation,
    }
    write_json(output_dir / "meta.json", meta)

    print(
        f"runtime ready: format={RUNTIME_FORMAT} trade_date={trade_date} "
        f"screening={len(screening_rows)} details={len(screening_rows)} "
        f"industries={len(industry_rows)} validation={validation['status']}"
    )


if __name__ == "__main__":
    main()
