#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

RUNTIME_FORMAT = "model_ready_candidates_v2"
SCREENING_GROUP_FORMAT = "screening_group_view_v1"
YOY_UNIT = "percentage_points"

MODEL_NOISE_COLUMNS = {
    "support_near",
    "volume_zone_near",
    "position_60d_low",
    "structural_signal_count",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_script(*args: str) -> None:
    subprocess.run([sys.executable, *args], check=True)


def validate_runtime(runtime_dir: Path) -> dict[str, Any]:
    meta_path = runtime_dir / "meta.json"
    meta = load_json(meta_path)

    assert meta.get("runtime_kind") == "low_risk_research"
    assert meta.get("runtime_format") == RUNTIME_FORMAT
    assert meta.get("yoy_unit") == YOY_UNIT
    validation = meta.get("runtime_validation") or {}
    assert validation.get("status") == "passed", validation
    assert validation.get("screening_group_view_valid") is True, validation
    assert (
        meta.get("candidate_count")
        == meta.get("structural_relevance_count")
    )
    assert (
        int(meta.get("source_candidate_count") or 0)
        >= int(meta.get("candidate_count") or 0)
    )

    candidate_path = Path(meta["candidate_file"])
    assert candidate_path.exists(), candidate_path
    candidate = load_json(candidate_path)
    assert candidate.get("runtime_format") == RUNTIME_FORMAT
    assert candidate.get("yoy_unit") == YOY_UNIT
    assert candidate.get("trade_date") == (
        meta.get("snapshot") or {}
    ).get("trade_date")
    assert candidate.get("source_candidate_count") == meta.get(
        "source_candidate_count"
    )
    rows = candidate.get("rows") or []
    columns = candidate.get("columns") or []
    assert candidate.get("candidate_count") == len(rows) == meta.get(
        "candidate_count"
    )
    assert columns == meta.get("candidate_columns")
    assert not (MODEL_NOISE_COLUMNS & set(columns)), (
        MODEL_NOISE_COLUMNS & set(columns)
    )

    required_columns = {
        "code",
        "name",
        "price",
        "industry_code",
        "industry_name",
        "industry_trend",
        "industry_strength",
        "industry_breadth",
        "industry_aggregate_revenue_yoy",
        "industry_aggregate_parent_profit_yoy",
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
        "position_pct",
        "support_distance_pct",
        "support_touches",
        "volume_zone_distance_pct",
        "volume_zone_share_pct",
        "structure_tier",
        "strong_support",
        "strong_volume_zone",
        "resistance_center",
        "invalidation_price",
        "invalidation_direction",
    }
    missing = sorted(required_columns - set(columns))
    assert not missing, missing

    code_idx = columns.index("code")
    candidate_codes = [str(row[code_idx]) for row in rows]
    assert len(candidate_codes) == len(set(candidate_codes))

    screening_path = Path(meta["screening_group_file"])
    assert screening_path.exists(), screening_path
    screening = load_json(screening_path)
    assert screening.get("runtime_format") == SCREENING_GROUP_FORMAT
    assert screening.get("yoy_unit") == YOY_UNIT
    assert screening.get("trade_date") == (
        meta.get("snapshot") or {}
    ).get("trade_date")
    assert screening.get("candidate_count") == meta.get("candidate_count")
    assert screening.get("group_count") == meta.get(
        "screening_group_count"
    )

    screening_codes = [
        str(member.get("code"))
        for group in (screening.get("groups") or [])
        for member in (group.get("members") or [])
    ]
    assert (
        len(screening_codes)
        == len(set(screening_codes))
        == len(candidate_codes)
    )
    assert set(screening_codes) == set(candidate_codes)
    assert (
        meta.get("screening_group_validation") or {}
    ).get("status") == "passed"

    assert not (runtime_dir / "peer_groups.json").exists()
    assert not (runtime_dir / "company_research_view.json").exists()
    assert not (runtime_dir / "details").exists()
    assert "peer_group_file" not in meta
    assert "company_research_file" not in meta

    structural_rule = meta.get("structural_rule") or {}
    assert structural_rule == candidate.get("structural_rule")
    assert structural_rule.get("deep_position_60d_pct_lte") == 20.0
    assert structural_rule.get("position_60d_pct_lte") == 35.0
    assert structural_rule.get("deep_support_distance_pct_lte") == 3.0
    assert structural_rule.get("deep_support_touches_gte") == 3
    assert structural_rule.get("deep_volume_distance_pct_lte") == 3.0
    assert structural_rule.get("deep_volume_share_pct_gte") == 12.0
    assert structural_rule.get("mid_low_support_distance_pct_lte") == 5.0
    assert structural_rule.get("mid_low_volume_distance_pct_lte") == 5.0

    eligibility_audit = meta.get("eligibility_audit")
    if eligibility_audit:
        universe = int(eligibility_audit.get("universe_count") or 0)
        eligible = int(eligibility_audit.get("eligible_count") or 0)
        exclusions = eligibility_audit.get(
            "exclusive_first_failure_counts"
        ) or {}
        assert universe == eligible + sum(
            int(value or 0) for value in exclusions.values()
        )
        assert eligible == int(meta.get("source_candidate_count") or 0)

    return {
        "runtime_kind": meta.get("runtime_kind"),
        "runtime_format": meta.get("runtime_format"),
        "trade_date": (meta.get("snapshot") or {}).get("trade_date"),
        "source_candidate_count": meta.get("source_candidate_count"),
        "candidate_count": meta.get("candidate_count"),
        "screening_group_count": meta.get("screening_group_count"),
        "screening_group_singleton_count": meta.get(
            "screening_group_singleton_count"
        ),
        "screening_group_max_size": meta.get(
            "screening_group_max_size"
        ),
        "screening_group_coverage": meta.get("screening_group_coverage"),
        "eligibility_audit": eligibility_audit,
        "validation": validation.get("status"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "snapshot",
        nargs="?",
        default="data/snapshot.json",
    )
    parser.add_argument("--output-dir", default="data/runtime")
    args = parser.parse_args()

    snapshot = Path(args.snapshot)
    runtime_dir = Path(args.output_dir)

    run_script(
        "scripts/split_snapshot.py",
        str(snapshot),
        "--output-dir",
        str(runtime_dir),
    )
    run_script(
        "scripts/build_screening_groups.py",
        "--runtime-dir",
        str(runtime_dir),
    )

    summary = validate_runtime(runtime_dir)
    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
