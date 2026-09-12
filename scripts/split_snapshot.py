#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


RUNTIME_SCHEMA_VERSION = 3
RUNTIME_FORMAT = "screening_details_v3"


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
    rows_key: str,
    rows: list[dict[str, Any]],
) -> None:
    """Write valid JSON with exactly one logical record per source line.

    This keeps runtime files small in line count and makes deterministic source-window
    reads practical for connector clients.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["{"]
    header_items = list(header.items())
    for key, value in header_items:
        lines.append(
            f"  {json.dumps(key, ensure_ascii=False)}: "
            f"{json.dumps(value, ensure_ascii=False, separators=(',', ':'))},"
        )
    lines.append(f"  {json.dumps(rows_key, ensure_ascii=False)}: [")
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


def compact_industry(code: str, raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": code,
        "name": raw.get("name"),
        "trend": raw.get("trend"),
        "strength": raw.get("strength"),
        "breadth": raw.get("breadth"),
        "confidence": raw.get("confidence"),
        "core_improving_breadth": raw.get("core_improving_breadth"),
        "aggregate_revenue_yoy": raw.get("aggregate_revenue_yoy"),
        "aggregate_parent_profit_yoy": raw.get("aggregate_parent_profit_yoy"),
        "market_breadth": raw.get("market_breadth"),
        "market_activity": raw.get("market_activity"),
        "market_confirmation": raw.get("market_confirmation"),
        "last_verified_at": raw.get("last_verified_at"),
    }


def compact_screening_candidate(
    code: str, raw: dict[str, Any], detail_file: str
) -> dict[str, Any]:
    fundamentals = raw.get("fundamentals") or {}
    structure = raw.get("price_structure") or {}

    row = {
        "code": code,
        "name": raw.get("name"),
        "price": raw.get("price"),
        "day_change_pct": raw.get("day_change_pct"),
        "industry_code": raw.get("industry_code"),
        "industry_name": raw.get("industry_name"),
        "pe_ttm": fundamentals.get("pe_ttm"),
        "pe_dynamic": fundamentals.get("pe_dynamic"),
        "pb": fundamentals.get("pb"),
        "roe": fundamentals.get("roe"),
        "revenue_yoy": fundamentals.get("revenue_yoy"),
        "net_profit_yoy": fundamentals.get("net_profit_yoy"),
        "operating_cashflow_per_share": fundamentals.get(
            "operating_cashflow_per_share"
        ),
        "gross_margin": fundamentals.get("gross_margin"),
        "close_change_5d_pct": structure.get("close_change_5d_pct"),
        "close_change_20d_pct": structure.get("close_change_20d_pct"),
        "position_pct": structure.get("position_pct"),
        "trend_state": structure.get("trend_state"),
        "break_state": structure.get("break_state"),
        "ma20": structure.get("ma20"),
        "ma60": structure.get("ma60"),
        "support_center": zone_center(structure.get("nearest_support")),
        "volume_zone_center": zone_center(structure.get("nearest_volume_zone")),
        "resistance_center": zone_center(structure.get("nearest_resistance")),
        "invalidation": structure.get("invalidation"),
        "detail_file": detail_file,
    }
    # Omit nulls from the lightweight first-pass record to reduce connector payload.
    return {key: value for key, value in row.items() if value is not None}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", default="data/snapshot.json")
    parser.add_argument("--output-dir", default="data/runtime")
    # Retained for CLI compatibility with the previous workflow. V3 does not shard the
    # screening universe; deep details are addressed directly by stock code.
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
    industry_state_path = output_dir / industry_state_filename
    industry_rows = [
        compact_industry(code, raw)
        for code, raw in sorted(level3.items(), key=lambda item: item[0])
    ]
    write_row_json(
        industry_state_path,
        {
            "schema_version": RUNTIME_SCHEMA_VERSION,
            "trade_date": trade_date,
            "industry_count": len(industry_rows),
        },
        "industries",
        industry_rows,
    )

    details_dir = output_dir / "details"
    details_dir.mkdir(parents=True, exist_ok=True)
    screening_rows: list[dict[str, Any]] = []

    for code, raw in candidates.items():
        detail_rel = f"{output_dir.as_posix()}/details/{code}.json"
        detail_path = details_dir / f"{code}.json"
        detail_payload = {
            "schema_version": RUNTIME_SCHEMA_VERSION,
            "trade_date": trade_date,
            "code": code,
            "candidate": raw,
        }
        write_json(detail_path, detail_payload)
        screening_rows.append(compact_screening_candidate(code, raw, detail_rel))

    screening_rows.sort(key=lambda row: str(row.get("code") or ""))
    screening_filename = "screening_snapshot.json"
    screening_path = output_dir / screening_filename
    write_row_json(
        screening_path,
        {
            "schema_version": RUNTIME_SCHEMA_VERSION,
            "trade_date": trade_date,
            "source_candidate_count": len(candidates),
            "screening_count": len(screening_rows),
            "detail_count": len(screening_rows),
        },
        "candidates",
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

    industry_state_file = f"{output_dir.as_posix()}/{industry_state_filename}"
    screening_file = f"{output_dir.as_posix()}/{screening_filename}"
    detail_file_template = f"{output_dir.as_posix()}/details/{{code}}.json"

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
        "industry_state_file": industry_state_file,
        "screening_file": screening_file,
        "detail_file_template": detail_file_template,
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
