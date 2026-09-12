#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

SCREENING_GROUP_FORMAT = "screening_group_view_v1"
YOY_UNIT = "percentage_points"

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


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


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
        members: list[dict[str, Any]] = []

        for row in group_rows:
            member = {
                field: row[index[field]]
                for field in MEMBER_BASE_FIELDS
            }
            member["quality_flags"] = quality_flags(row, index)
            members.append(member)

            code = str(member["code"])
            screening_codes.append(code)
            report_date_available += int(
                member["report_date"] not in (None, "")
            )
            valuation_core_complete += int(
                all(
                    member[field] not in (None, "")
                    for field in ("pe_ttm", "pb", "roe")
                )
            )
            operating_core_complete += int(
                all(
                    member[field] not in (None, "")
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

    singleton_count = sum(
        1 for group in groups if group["single_candidate"]
    )
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
        "coverage": coverage,
        "groups": groups,
    }
    write_json(runtime_dir / filename, payload)

    validation = {
        "status": "passed",
        "candidate_codes_unique": codes_unique,
        "candidate_codes_exact_match": exact_match,
        "candidate_count_matches": candidate_count
        == int(meta.get("candidate_count") or 0),
        "trade_date_matches": payload.get("trade_date")
        == (meta.get("snapshot") or {}).get("trade_date"),
        "yoy_unit_matches": payload.get("yoy_unit") == meta.get("yoy_unit"),
    }
    if not all(
        value is True
        for key, value in validation.items()
        if key != "status"
    ):
        raise SystemExit(
            f"screening group validation failed: {validation}"
        )

    meta["screening_group_file"] = (
        f"{runtime_dir.as_posix()}/{filename}"
    )
    meta["screening_group_format"] = SCREENING_GROUP_FORMAT
    meta["screening_group_count"] = len(groups)
    meta["screening_group_singleton_count"] = singleton_count
    meta["screening_group_max_size"] = max_group_size
    meta["screening_group_member_fields"] = MEMBER_BASE_FIELDS
    meta["screening_group_coverage"] = coverage
    meta["screening_group_validation"] = validation

    runtime_validation = meta.get("runtime_validation") or {}
    runtime_validation["screening_group_view_valid"] = True
    meta["runtime_validation"] = runtime_validation
    write_json(meta_path, meta)

    print(
        "screening group view ready: "
        f"candidates={candidate_count} groups={len(groups)} "
        f"singletons={singleton_count} max_group_size={max_group_size}"
    )


if __name__ == "__main__":
    main()
