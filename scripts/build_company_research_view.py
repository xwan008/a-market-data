#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

COMPANY_RESEARCH_FORMAT = "company_research_view_v1"

BASE_FIELDS = [
    "code",
    "name",
    "industry_code",
    "industry_name",
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
    "industry_trend",
    "industry_strength",
    "industry_breadth",
]

OUTPUT_FIELDS = [
    *BASE_FIELDS,
    "business_description",
    "profit_driver",
    "structure_tier",
    "strong_support",
    "strong_volume_zone",
    "revenue_profit_direction_divergence",
    "profit_deduct_direction_divergence",
    "profit_growth_cashflow_negative",
    "revenue_and_profit_both_negative",
    "profit_and_deduct_both_negative",
    "negative_operating_cashflow_per_share",
    "core_financial_missing_count",
]

BUSINESS_DESCRIPTION_CANDIDATES = [
    "business_description",
    "main_business",
    "business_scope",
]
PROFIT_DRIVER_CANDIDATES = ["profit_driver", "profit_drivers"]


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


def first_available(row: list[Any], index: dict[str, int], names: list[str]) -> Any:
    for name in names:
        pos = index.get(name)
        if pos is not None:
            value = row[pos]
            if value not in (None, ""):
                return value
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", default="data/runtime")
    args = parser.parse_args()

    runtime_dir = Path(args.runtime_dir)
    meta_path = runtime_dir / "meta.json"
    meta = load_json(meta_path)

    candidate_path = Path(meta["candidate_file"])
    candidate_payload = load_json(candidate_path)
    columns = candidate_payload.get("columns") or []
    rows = candidate_payload.get("rows") or []
    index = {name: i for i, name in enumerate(columns)}

    missing = sorted(set(BASE_FIELDS) - set(columns))
    if missing:
        raise SystemExit(f"candidate columns missing for company research view: {missing}")

    output_rows: list[list[Any]] = []
    research_codes: list[str] = []

    report_date_available = 0
    valuation_core_complete = 0
    operating_core_complete = 0
    business_description_available = 0
    profit_driver_available = 0

    for row in rows:
        code = str(row[index["code"]])
        research_codes.append(code)

        position = numeric(row[index["position_pct"]])
        support_distance = numeric(row[index["support_distance_pct"]])
        support_touches = numeric(row[index["support_touches"]])
        volume_distance = numeric(row[index["volume_zone_distance_pct"]])
        volume_share = numeric(row[index["volume_zone_share_pct"]])

        strong_support = bool(
            support_distance is not None
            and support_distance <= 3.0
            and support_touches is not None
            and support_touches >= 3.0
        )
        strong_volume = bool(
            volume_distance is not None
            and volume_distance <= 3.0
            and volume_share is not None
            and volume_share >= 12.0
        )

        if position is not None and position <= 20.0:
            structure_tier = "deep_low_strong_acceptance"
        elif position is not None and position <= 35.0:
            structure_tier = "mid_low_dual_acceptance"
        else:
            structure_tier = "unexpected"

        revenue_yoy = row[index["revenue_yoy"]]
        net_profit_yoy = row[index["net_profit_yoy"]]
        deduct_yoy = row[index["deduct_basic_eps_yoy"]]
        ocfps = row[index["operating_cashflow_per_share"]]

        revenue_sign = sign(revenue_yoy)
        profit_sign = sign(net_profit_yoy)
        deduct_sign = sign(deduct_yoy)
        ocfps_number = numeric(ocfps)

        revenue_profit_divergence = bool(
            revenue_sign is not None
            and profit_sign is not None
            and revenue_sign != profit_sign
        )
        profit_deduct_divergence = bool(
            profit_sign is not None
            and deduct_sign is not None
            and profit_sign != deduct_sign
        )
        profit_growth_cashflow_negative = bool(
            numeric(net_profit_yoy) is not None
            and numeric(net_profit_yoy) > 0
            and ocfps_number is not None
            and ocfps_number < 0
        )
        revenue_and_profit_both_negative = bool(
            numeric(revenue_yoy) is not None
            and numeric(revenue_yoy) < 0
            and numeric(net_profit_yoy) is not None
            and numeric(net_profit_yoy) < 0
        )
        profit_and_deduct_both_negative = bool(
            numeric(net_profit_yoy) is not None
            and numeric(net_profit_yoy) < 0
            and numeric(deduct_yoy) is not None
            and numeric(deduct_yoy) < 0
        )
        negative_ocfps = bool(ocfps_number is not None and ocfps_number < 0)

        core_financial_fields = [
            row[index["pe_ttm"]],
            row[index["pb"]],
            row[index["roe"]],
            revenue_yoy,
            net_profit_yoy,
            deduct_yoy,
            ocfps,
            row[index["gross_margin"]],
        ]
        core_missing_count = sum(value in (None, "") for value in core_financial_fields)

        business_description = first_available(
            row, index, BUSINESS_DESCRIPTION_CANDIDATES
        )
        profit_driver = first_available(row, index, PROFIT_DRIVER_CANDIDATES)

        report_date_available += int(row[index["report_date"]] not in (None, ""))
        valuation_core_complete += int(
            all(row[index[field]] not in (None, "") for field in ["pe_ttm", "pb", "roe"])
        )
        operating_core_complete += int(
            all(
                row[index[field]] not in (None, "")
                for field in [
                    "revenue_yoy",
                    "net_profit_yoy",
                    "deduct_basic_eps_yoy",
                    "operating_cashflow_per_share",
                    "gross_margin",
                ]
            )
        )
        business_description_available += int(business_description is not None)
        profit_driver_available += int(profit_driver is not None)

        values = {field: row[index[field]] for field in BASE_FIELDS}
        values.update(
            {
                "business_description": business_description,
                "profit_driver": profit_driver,
                "structure_tier": structure_tier,
                "strong_support": strong_support,
                "strong_volume_zone": strong_volume,
                "revenue_profit_direction_divergence": revenue_profit_divergence,
                "profit_deduct_direction_divergence": profit_deduct_divergence,
                "profit_growth_cashflow_negative": profit_growth_cashflow_negative,
                "revenue_and_profit_both_negative": revenue_and_profit_both_negative,
                "profit_and_deduct_both_negative": profit_and_deduct_both_negative,
                "negative_operating_cashflow_per_share": negative_ocfps,
                "core_financial_missing_count": core_missing_count,
            }
        )
        output_rows.append([values[field] for field in OUTPUT_FIELDS])

    candidate_codes = [str(row[index["code"]]) for row in rows]
    candidate_set = set(candidate_codes)
    research_set = set(research_codes)
    codes_unique = len(research_codes) == len(research_set)
    exact_match = (
        candidate_set == research_set
        and len(candidate_codes) == len(research_codes)
    )
    if not codes_unique or not exact_match:
        raise SystemExit(
            "company research candidate coverage mismatch: "
            f"candidate={len(candidate_codes)} research={len(research_codes)} "
            f"unique={codes_unique} exact_match={exact_match}"
        )

    candidate_count = len(candidate_codes)
    coverage = {
        "candidate_count": candidate_count,
        "report_date_available_count": report_date_available,
        "valuation_core_complete_count": valuation_core_complete,
        "operating_core_complete_count": operating_core_complete,
        "business_description_available_count": business_description_available,
        "profit_driver_available_count": profit_driver_available,
        "business_profile_note": (
            "business_description/profit_driver stay null when the current repository "
            "has no reliable structured source; do not infer them from industry names"
        ),
    }

    filename = "company_research_view.json"
    path = runtime_dir / filename
    payload = {
        "runtime_format": COMPANY_RESEARCH_FORMAT,
        "trade_date": candidate_payload.get("trade_date"),
        "candidate_count": candidate_count,
        "purpose": (
            "compact company-level deterministic facts for pre-screening before public "
            "Deep Research; no score, ranking, or final exclusion decision"
        ),
        "columns": OUTPUT_FIELDS,
        "coverage": coverage,
        "rows": output_rows,
    }
    write_json(path, payload)

    validation = {
        "status": "passed",
        "candidate_codes_unique": codes_unique,
        "candidate_codes_exact_match": exact_match,
        "candidate_count_matches": candidate_count == int(meta.get("candidate_count") or 0),
        "trade_date_matches": payload.get("trade_date")
        == (meta.get("snapshot") or {}).get("trade_date"),
    }
    if not all(value is True for key, value in validation.items() if key != "status"):
        raise SystemExit(f"company research view validation failed: {validation}")

    meta["company_research_file"] = f"{runtime_dir.as_posix()}/{filename}"
    meta["company_research_format"] = COMPANY_RESEARCH_FORMAT
    meta["company_research_columns"] = OUTPUT_FIELDS
    meta["company_research_coverage"] = coverage
    meta["company_research_validation"] = validation
    runtime_validation = meta.get("runtime_validation") or {}
    runtime_validation["company_research_view_valid"] = True
    meta["runtime_validation"] = runtime_validation
    write_json(meta_path, meta)

    print(
        "company research view ready: "
        f"candidates={candidate_count} report_date={report_date_available} "
        f"valuation_complete={valuation_core_complete} "
        f"operating_complete={operating_core_complete} "
        f"business_profiles={business_description_available}"
    )


if __name__ == "__main__":
    main()
