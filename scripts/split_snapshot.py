#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from contracts import YOY_UNIT

RUNTIME_KIND = "low_risk_research"
RUNTIME_FORMAT = "model_ready_candidates"

CANDIDATE_COLUMNS = [
    "code","name","price","day_change_pct","industry_code","industry_name",
    "industry_trend","industry_strength","industry_breadth","industry_confidence",
    "industry_core_improving_breadth","industry_aggregate_revenue_yoy",
    "industry_aggregate_parent_profit_yoy","industry_market_breadth",
    "industry_market_activity","industry_market_confirmation","report_date",
    "market_cap","pe_ttm","pe_dynamic","pb","roe","revenue_yoy","net_profit_yoy",
    "deduct_basic_eps_yoy","operating_cashflow_per_share","gross_margin","net_profit",
    "basic_eps","deduct_basic_eps","close_change_5d_pct","close_change_20d_pct",
    "high_20d","low_20d","high_60d","low_60d","ma20","ma60","position_pct",
    "trend_state","break_state","support_low","support_high","support_center",
    "support_touches","support_last_touch_date","support_distance_pct","volume_zone_low",
    "volume_zone_high","volume_zone_center","volume_zone_share_pct","volume_zone_last_date",
    "volume_zone_distance_pct","resistance_low","resistance_high","resistance_center",
    "resistance_touches","resistance_last_touch_date","invalidation_price","invalidation_direction",
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_row_json(path: Path, header: dict[str, Any], columns: list[str], rows: list[list[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["{"]
    for key, value in header.items():
        lines.append(f"  {json.dumps(key, ensure_ascii=False)}: {json.dumps(value, ensure_ascii=False, separators=(',', ':'))},")
    lines.append('  "columns": ' + json.dumps(columns, ensure_ascii=False, separators=(",", ":")) + ",")
    lines.append('  "rows": [')
    for index, row in enumerate(rows):
        suffix = "," if index < len(rows) - 1 else ""
        lines.append("    " + json.dumps(row, ensure_ascii=False, separators=(",", ":")) + suffix)
    lines.append("  ]")
    lines.append("}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def zone_part(zone: Any, key: str) -> Any:
    return zone.get(key) if isinstance(zone, dict) else None


def distance_pct(price: Any, anchor: Any) -> float | None:
    if not is_number(price) or not is_number(anchor) or anchor <= 0:
        return None
    return abs(float(price) - float(anchor)) / float(anchor) * 100.0


def invalidation_parts(value: Any) -> tuple[Any, Any]:
    if not isinstance(value, dict):
        return None, None
    price = value.get("price")
    direction = value.get("direction")
    return (price if is_number(price) else None, direction)


def industry_yoy_value(value: Any, source_unit: str | None) -> Any:
    if source_unit != YOY_UNIT:
        raise ValueError(f"unexpected industry YoY unit: {source_unit!r}")
    return value


def build_candidate_row(
    code: str,
    raw: dict[str, Any],
    industry: dict[str, Any],
    industry_yoy_unit: str | None,
) -> list[Any]:
    fundamentals = raw.get("fundamentals") or {}
    structure = raw.get("price_structure") or {}
    support = structure.get("nearest_support") or {}
    volume_zone = structure.get("nearest_volume_zone") or {}
    resistance = structure.get("nearest_resistance") or {}
    price = raw.get("price")

    support_distance = distance_pct(price, zone_part(support, "center"))
    volume_distance = distance_pct(price, zone_part(volume_zone, "center"))
    invalidation_price, invalidation_direction = invalidation_parts(
        structure.get("invalidation")
    )

    return [
        code, raw.get("name"), price, raw.get("day_change_pct"), raw.get("industry_code"), raw.get("industry_name"),
        industry.get("trend"), industry.get("strength"), industry.get("breadth"), industry.get("confidence"),
        industry.get("core_improving_breadth"), industry_yoy_value(industry.get("aggregate_revenue_yoy"), industry_yoy_unit),
        industry_yoy_value(industry.get("aggregate_parent_profit_yoy"), industry_yoy_unit),
        industry.get("market_breadth"), industry.get("market_activity"), industry.get("market_confirmation"),
        fundamentals.get("report_date"), fundamentals.get("market_cap"), fundamentals.get("pe_ttm"), fundamentals.get("pe_dynamic"),
        fundamentals.get("pb"), fundamentals.get("roe"), fundamentals.get("revenue_yoy"), fundamentals.get("net_profit_yoy"),
        fundamentals.get("deduct_basic_eps_yoy"), fundamentals.get("operating_cashflow_per_share"), fundamentals.get("gross_margin"),
        fundamentals.get("net_profit"), fundamentals.get("basic_eps"), fundamentals.get("deduct_basic_eps"),
        structure.get("close_change_5d_pct"), structure.get("close_change_20d_pct"), structure.get("high_20d"), structure.get("low_20d"),
        structure.get("high_60d"), structure.get("low_60d"), structure.get("ma20"), structure.get("ma60"), structure.get("position_pct"),
        structure.get("trend_state"), structure.get("break_state"),
        zone_part(support, "low"), zone_part(support, "high"), zone_part(support, "center"), zone_part(support, "touches"),
        zone_part(support, "last_touch_date"), support_distance,
        zone_part(volume_zone, "low"), zone_part(volume_zone, "high"), zone_part(volume_zone, "center"), zone_part(volume_zone, "volume_share_pct"),
        zone_part(volume_zone, "last_date"), volume_distance,
        zone_part(resistance, "low"), zone_part(resistance, "high"), zone_part(resistance, "center"),
        zone_part(resistance, "touches"), zone_part(resistance, "last_touch_date"), invalidation_price, invalidation_direction,
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", default="data/snapshot.json")
    parser.add_argument("--output-dir", default="data/runtime")
    args = parser.parse_args()

    snapshot_path = Path(args.input)
    output_dir = Path(args.output_dir)
    snapshot = load_json(snapshot_path)

    candidates = snapshot.get("candidates") or {}
    expected = int((snapshot.get("counts") or {}).get("candidates") or 0)
    if not isinstance(candidates, dict) or not candidates:
        raise SystemExit("snapshot.candidates must be a non-empty object")
    if len(candidates) != expected:
        raise SystemExit(f"candidate count mismatch: expected={expected} actual={len(candidates)}")

    industry_state = snapshot.get("industry_state") or {}
    level3 = industry_state.get("level3") or {}
    if not isinstance(level3, dict) or not level3:
        raise SystemExit("snapshot.industry_state.level3 must be a non-empty object")
    industry_yoy_unit = industry_state.get("yoy_unit") or (snapshot.get("units") or {}).get("industry_yoy")

    trade_date = snapshot.get("trade_date")
    if not trade_date:
        raise SystemExit("snapshot.trade_date is required")

    candidate_codes = list(candidates.keys())
    if len(candidate_codes) != len(set(candidate_codes)):
        raise SystemExit("duplicate candidate codes detected")

    missing_industry_codes = sorted({
        str(raw.get("industry_code"))
        for raw in candidates.values()
        if not raw.get("industry_code") or raw.get("industry_code") not in level3
    })
    if missing_industry_codes:
        sample = ",".join(missing_industry_codes[:10])
        raise SystemExit(
            f"candidate industry mapping incomplete: count={len(missing_industry_codes)} sample={sample}"
        )

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    model_rows: list[list[Any]] = []
    for code, raw in candidates.items():
        industry = level3.get(raw.get("industry_code")) or {}
        model_rows.append(
            build_candidate_row(code, raw, industry, industry_yoy_unit)
        )

    industry_idx = CANDIDATE_COLUMNS.index("industry_code")
    code_idx = CANDIDATE_COLUMNS.index("code")
    model_rows.sort(
        key=lambda row: (str(row[industry_idx] or ""), str(row[code_idx] or ""))
    )

    candidates_filename = "candidates.json"
    write_row_json(
        output_dir / candidates_filename,
        {
            "runtime_format": RUNTIME_FORMAT,
            "trade_date": trade_date,
            "yoy_unit": YOY_UNIT,
            "source_candidate_count": len(candidates),
            "candidate_count": len(model_rows),
        },
        CANDIDATE_COLUMNS,
        model_rows,
    )

    meta_snapshot = {
        key: value
        for key, value in snapshot.items()
        if key not in {"candidates", "industry_state"}
    }
    meta_snapshot["industry_state"] = {
        key: value for key, value in industry_state.items() if key != "level3"
    }
    meta_snapshot["industry_state"]["yoy_unit"] = YOY_UNIT

    validation = {
        "status": "passed",
        "trade_date": trade_date,
        "candidate_codes_unique": True,
        "source_candidate_count_matches_snapshot": len(candidates) == expected,
        "industry_mapping_complete": not missing_industry_codes,
        "all_hard_eligible_candidates_retained": len(model_rows) == len(candidates),
        "yoy_unit": YOY_UNIT,
    }

    meta = {
        "runtime_kind": RUNTIME_KIND,
        "runtime_format": RUNTIME_FORMAT,
        "yoy_unit": YOY_UNIT,
        "snapshot": meta_snapshot,
        "source_candidate_count": len(candidates),
        "candidate_count": len(model_rows),
        "industry_count": len(level3),
        "eligibility_audit": snapshot.get("eligibility_audit"),
        "candidate_file": f"{output_dir.as_posix()}/{candidates_filename}",
        "candidate_columns": CANDIDATE_COLUMNS,
        "runtime_validation": validation,
    }
    write_json(output_dir / "meta.json", meta)

    print(
        f"runtime base ready: kind={RUNTIME_KIND} format={RUNTIME_FORMAT} trade_date={trade_date} "
        f"source={len(candidates)} model_candidates={len(model_rows)} "
        f"industries={len(level3)} validation={validation['status']}"
    )


if __name__ == "__main__":
    main()
