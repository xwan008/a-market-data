#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from contracts import YOY_UNIT

SCREENING_GROUP_FORMAT = "screening_group_view"
SCREENING_SERIALIZATION_FORMAT = "columnar_pretty_json"
MAX_LINE_LENGTH = 4096

MEMBER_BASE_FIELDS = [
    "code",
    "name",
    "report_date",
    "price",
    "market_cap",
    "position_pct",
    "support_distance_pct",
    "support_touches",
    "volume_zone_distance_pct",
    "volume_zone_share_pct",
    "resistance_center",
    "invalidation_price",
    "invalidation_direction",
    "structure_tier",
    "strong_support",
    "strong_volume_zone",
    "pe_ttm",
    "pe_dynamic",
    "pb",
    "roe",
    "revenue_yoy",
    "net_profit_yoy",
    "deduct_basic_eps_yoy",
    "operating_cashflow_per_share",
    "gross_margin",
    "net_profit",
]

INDUSTRY_CONTEXT_FIELDS = [
    "industry_trend",
    "industry_strength",
    "industry_breadth",
    "industry_confidence",
    "industry_core_improving_breadth",
    "industry_aggregate_revenue_yoy",
    "industry_aggregate_parent_profit_yoy",
    "industry_market_breadth",
    "industry_market_activity",
    "industry_market_confirmation",
]

QUALITY_FLAG_FIELDS = [
    "revenue_profit_direction_divergence",
    "profit_deduct_direction_divergence",
    "profit_growth_cashflow_negative",
    "revenue_and_profit_both_negative",
    "profit_and_deduct_both_negative",
    "negative_operating_cashflow_per_share",
    "core_financial_missing_count",
]

MEMBER_COLUMNS = [
    *MEMBER_BASE_FIELDS,
    *(f"quality_flag.{field}" for field in QUALITY_FLAG_FIELDS),
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def serialize_screening_payload(payload: dict[str, Any]) -> str:
    """Serialize the model work view as compact, line-addressable JSON.

    Repeated member field names are stored once in `member_columns`; each member
    is one compact JSON array on one physical line. This keeps the file easy to
    read in bounded line ranges without inflating token volume with repeated
    object keys.
    """
    groups = payload["groups"]
    header_items = [(key, value) for key, value in payload.items() if key != "groups"]

    lines = ["{"]
    for key, value in header_items:
        lines.append(f'  {compact_json(key)}: {compact_json(value)},')

    lines.append('  "groups": [')
    for group_index, group in enumerate(groups):
        lines.append("    {")
        lines.append(f'      "industry_code": {compact_json(group["industry_code"])},')
        lines.append(f'      "industry_name": {compact_json(group["industry_name"])},')
        lines.append(f'      "candidate_count": {compact_json(group["candidate_count"])},')
        lines.append(f'      "single_candidate": {compact_json(group["single_candidate"])},')
        lines.append(
            f'      "industry_context": {compact_json(group["industry_context"])},'
        )
        lines.append('      "members": [')
        members = group["members"]
        for member_index, member in enumerate(members):
            suffix = "," if member_index < len(members) - 1 else ""
            lines.append(f"        {compact_json(member)}{suffix}")
        lines.append("      ]")
        suffix = "," if group_index < len(groups) - 1 else ""
        lines.append(f"    }}{suffix}")
    lines.append("  ]")
    lines.append("}")
    return "\n".join(lines) + "\n"


def write_screening_json(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    text = serialize_screening_payload(payload)
    path.write_text(text, encoding="utf-8")

    parsed = json.loads(text)
    lines = text.splitlines()
    max_line_length = max((len(line) for line in lines), default=0)
    line_addressable = len(lines) > 1 and max_line_length <= MAX_LINE_LENGTH

    return {
        "format": SCREENING_SERIALIZATION_FORMAT,
        "line_count": len(lines),
        "max_line_length": max_line_length,
        "max_allowed_line_length": MAX_LINE_LENGTH,
        "json_roundtrip_matches": parsed == payload,
        "line_addressable": line_addressable,
    }


def numeric(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def sign(value: Any) -> int | None:
    number = numeric(value)
    if number is None:
        return None
    if number > 0:
        return 1
    if number < 0:
        return -1
    return 0


def quality_flags(row: list[Any], index: dict[str, int]) -> dict[str, Any]:
    revenue_yoy = row[index["revenue_yoy"]]
    net_profit_yoy = row[index["net_profit_yoy"]]
    deduct_yoy = row[index["deduct_basic_eps_yoy"]]
    ocfps = row[index["operating_cashflow_per_share"]]

    revenue_sign = sign(revenue_yoy)
    profit_sign = sign(net_profit_yoy)
    deduct_sign = sign(deduct_yoy)
    ocfps_number = numeric(ocfps)

    core_fields = [
        row[index["pe_ttm"]],
        row[index["pb"]],
        row[index["roe"]],
        revenue_yoy,
        net_profit_yoy,
        deduct_yoy,
        ocfps,
        row[index["gross_margin"]],
    ]

    return {
        "revenue_profit_direction_divergence": bool(
            revenue_sign is not None
            and profit_sign is not None
            and revenue_sign != profit_sign
        ),
        "profit_deduct_direction_divergence": bool(
            profit_sign is not None
            and deduct_sign is not None
            and profit_sign != deduct_sign
        ),
        "profit_growth_cashflow_negative": bool(
            numeric(net_profit_yoy) is not None
            and numeric(net_profit_yoy) > 0
            and ocfps_number is not None
            and ocfps_number < 0
        ),
        "revenue_and_profit_both_negative": bool(
            numeric(revenue_yoy) is not None
            and numeric(revenue_yoy) < 0
            and numeric(net_profit_yoy) is not None
            and numeric(net_profit_yoy) < 0
        ),
        "profit_and_deduct_both_negative": bool(
            numeric(net_profit_yoy) is not None
            and numeric(net_profit_yoy) < 0
            and numeric(deduct_yoy) is not None
            and numeric(deduct_yoy) < 0
        ),
        "negative_operating_cashflow_per_share": bool(
            ocfps_number is not None and ocfps_number < 0
        ),
        "core_financial_missing_count": sum(
            value in (None, "") for value in core_fields
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", default="data/runtime")
    args = parser.parse_args()

    runtime_dir = Path(args.runtime_dir)
    meta_path = runtime_dir / "meta.json"
    meta = load_json(meta_path)

    if meta.get("yoy_unit") != YOY_UNIT:
        raise SystemExit(
            f"unexpected runtime YoY unit: {meta.get('yoy_unit')!r}"
        )

    candidate_path = Path(meta["candidate_file"])
    candidate_payload = load_json(candidate_path)
    columns = candidate_payload.get("columns") or []
    rows = candidate_payload.get("rows") or []
    index = {name: i for i, name in enumerate(columns)}

    required = {
        "code",
        "name",
        "industry_code",
        "industry_name",
        *MEMBER_BASE_FIELDS,
        *INDUSTRY_CONTEXT_FIELDS,
    }
    missing = sorted(required - set(columns))
    if missing:
        raise SystemExit(
            f"candidate columns missing for screening view: {missing}"
        )

    grouped: dict[str, list[list[Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[index["industry_code"]] or "")].append(row)

    groups: list[dict[str, Any]] = []
    screening_codes: list[str] = []

    report_date_available = 0
    valuation_core_complete = 0
    operating_core_complete = 0

    for industry_code in sorted(grouped):
        group_rows = sorted(
            grouped[industry_code],
            key=lambda row: str(row[index["code"]] or ""),
        )
        first = group_rows[0]
        members: list[list[Any]] = []

        for row in group_rows:
            flags = quality_flags(row, index)
            member = [
                *(row[index[field]] for field in MEMBER_BASE_FIELDS),
                *(flags[field] for field in QUALITY_FLAG_FIELDS),
            ]
            members.append(member)

            code = str(row[index["code"]])
            screening_codes.append(code)
            report_date_available += int(row[index["report_date"]] not in (None, ""))
            valuation_core_complete += int(
                all(
                    row[index[field]] not in (None, "")
                    for field in ("pe_ttm", "pb", "roe")
                )
            )
            operating_core_complete += int(
                all(
                    row[index[field]] not in (None, "")
                    for field in (
                        "revenue_yoy",
                        "net_profit_yoy",
                        "deduct_basic_eps_yoy",
                        "operating_cashflow_per_share",
                        "gross_margin",
                    )
                )
            )

        groups.append(
            {
                "industry_code": industry_code,
                "industry_name": first[index["industry_name"]],
                "candidate_count": len(members),
                "single_candidate": len(members) == 1,
                "industry_context": {
                    "yoy_unit": YOY_UNIT,
                    **{
                        field.removeprefix("industry_"): first[index[field]]
                        for field in INDUSTRY_CONTEXT_FIELDS
                    },
                },
                "members": members,
            }
        )

    candidate_codes = [str(row[index["code"]]) for row in rows]
    candidate_set = set(candidate_codes)
    screening_set = set(screening_codes)
    codes_unique = len(screening_codes) == len(screening_set)
    exact_match = (
        candidate_set == screening_set
        and len(candidate_codes) == len(screening_codes)
    )
    if not codes_unique or not exact_match:
        raise SystemExit(
            "screening group candidate coverage mismatch: "
            f"candidate={len(candidate_codes)} "
            f"screening={len(screening_codes)} "
            f"unique={codes_unique} exact_match={exact_match}"
        )

    singleton_count = sum(1 for group in groups if group["single_candidate"])
    max_group_size = max(
        (group["candidate_count"] for group in groups),
        default=0,
    )
    candidate_count = len(candidate_codes)

    coverage = {
        "candidate_count": candidate_count,
        "report_date_available_count": report_date_available,
        "valuation_core_complete_count": valuation_core_complete,
        "operating_core_complete_count": operating_core_complete,
    }

    filename = "screening_groups.json"
    payload = {
        "runtime_format": SCREENING_GROUP_FORMAT,
        "trade_date": candidate_payload.get("trade_date"),
        "yoy_unit": YOY_UNIT,
        "candidate_count": candidate_count,
        "group_count": len(groups),
        "singleton_group_count": singleton_count,
        "max_group_size": max_group_size,
        "purpose": (
            "single deterministic fact view for all non-web pre-research "
            "screening: first peer dominance, then company absolute-quality "
            "pre-screen; no score, ranking, or model conclusion is precomputed"
        ),
        "member_columns": MEMBER_COLUMNS,
        "industry_context_fields": [
            "yoy_unit",
            *(field.removeprefix("industry_") for field in INDUSTRY_CONTEXT_FIELDS),
        ],
        "coverage": coverage,
        "groups": groups,
    }

    serialization = write_screening_json(runtime_dir / filename, payload)
    member_rows_count = sum(len(group["members"]) for group in groups)
    member_rows_well_formed = all(
        isinstance(member, list) and len(member) == len(MEMBER_COLUMNS)
        for group in groups
        for member in group["members"]
    )

    validation = {
        "status": "passed",
        "candidate_codes_unique": codes_unique,
        "candidate_codes_exact_match": exact_match,
        "candidate_count_matches": candidate_count
        == int(meta.get("candidate_count") or 0),
        "trade_date_matches": payload.get("trade_date")
        == (meta.get("snapshot") or {}).get("trade_date"),
        "yoy_unit_matches": payload.get("yoy_unit") == meta.get("yoy_unit"),
        "member_rows_count_matches": member_rows_count == candidate_count,
        "member_rows_well_formed": member_rows_well_formed,
        "json_roundtrip_matches": serialization["json_roundtrip_matches"],
        "line_addressable": serialization["line_addressable"],
    }
    if not all(
        value is True
        for key, value in validation.items()
        if key != "status"
    ):
        raise SystemExit(f"screening group validation failed: {validation}")

    meta["screening_group_file"] = f"{runtime_dir.as_posix()}/{filename}"
    meta["screening_group_format"] = SCREENING_GROUP_FORMAT
    meta["screening_group_count"] = len(groups)
    meta["screening_group_singleton_count"] = singleton_count
    meta["screening_group_max_size"] = max_group_size
    meta["screening_group_member_columns"] = MEMBER_COLUMNS
    meta.pop("screening_group_member_fields", None)
    meta.pop("screening_group_quality_flag_fields", None)
    meta["screening_group_coverage"] = coverage
    meta["screening_group_serialization"] = {
        key: value
        for key, value in serialization.items()
        if key not in {"json_roundtrip_matches", "line_addressable"}
    }
    meta["screening_group_validation"] = validation

    runtime_validation = meta.get("runtime_validation") or {}
    runtime_validation["screening_group_view_valid"] = True
    runtime_validation["screening_group_line_addressable"] = True
    meta["runtime_validation"] = runtime_validation
    write_json(meta_path, meta)

    print(
        "screening group view ready: "
        f"candidates={candidate_count} groups={len(groups)} "
        f"singletons={singleton_count} max_group_size={max_group_size} "
        f"lines={serialization['line_count']} "
        f"max_line_length={serialization['max_line_length']}"
    )


if __name__ == "__main__":
    main()
