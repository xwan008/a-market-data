#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from build_screening_groups import (
    MEMBER_COLUMNS,
    SCREENING_GROUP_FORMAT,
    SCREENING_SERIALIZATION_FORMAT,
)
from contracts import YOY_UNIT
from split_snapshot import RUNTIME_FORMAT, RUNTIME_KIND

MODEL_NOISE_COLUMNS = {
    "support_near",
    "volume_zone_near",
    "position_60d_low",
    "structural_signal_count",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def run_script(*args: str) -> None:
    subprocess.run([sys.executable, *args], check=True)


def normalize_runtime_meta(runtime_dir: Path) -> None:
    """Keep final meta compact and single-source.

    Eligibility audit is promoted to top-level meta. Do not retain a second
    embedded copy inside snapshot metadata.
    """
    meta_path = runtime_dir / "meta.json"
    meta = load_json(meta_path)
    snapshot_meta = meta.get("snapshot") or {}
    snapshot_meta.pop("eligibility_audit", None)
    snapshot_meta.pop("prefilter", None)  # legacy compatibility cleanup
    meta["snapshot"] = snapshot_meta
    write_json(meta_path, meta)


def validate_runtime(runtime_dir: Path) -> dict[str, Any]:
    meta_path = runtime_dir / "meta.json"
    meta = load_json(meta_path)

    assert meta.get("runtime_kind") == RUNTIME_KIND
    assert meta.get("runtime_format") == RUNTIME_FORMAT
    assert meta.get("yoy_unit") == YOY_UNIT
    validation = meta.get("runtime_validation") or {}
    assert validation.get("status") == "passed", validation
    assert validation.get("screening_group_view_valid") is True, validation
    assert validation.get("screening_group_line_addressable") is True, validation
    assert meta.get("candidate_count") == meta.get("structural_relevance_count")
    assert int(meta.get("source_candidate_count") or 0) >= int(
        meta.get("candidate_count") or 0
    )

    snapshot_meta = meta.get("snapshot") or {}
    assert "eligibility_audit" not in snapshot_meta
    assert "prefilter" not in snapshot_meta

    candidate_path = Path(meta["candidate_file"])
    assert candidate_path.exists(), candidate_path
    candidate = load_json(candidate_path)
    assert candidate.get("runtime_format") == RUNTIME_FORMAT
    assert candidate.get("yoy_unit") == YOY_UNIT
    assert candidate.get("trade_date") == snapshot_meta.get("trade_date")
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
    assert screening.get("trade_date") == snapshot_meta.get("trade_date")
    assert screening.get("candidate_count") == meta.get("candidate_count")
    assert screening.get("group_count") == meta.get("screening_group_count")

    screening_columns = screening.get("member_columns") or []
    assert screening_columns == MEMBER_COLUMNS
    assert screening_columns == meta.get("screening_group_member_columns")
    screening_code_idx = screening_columns.index("code")

    screening_members = [
        member
        for group in (screening.get("groups") or [])
        for member in (group.get("members") or [])
    ]
    assert all(
        isinstance(member, list) and len(member) == len(screening_columns)
        for member in screening_members
    )
    screening_codes = [
        str(member[screening_code_idx]) for member in screening_members
    ]
    assert (
        len(screening_codes)
        == len(set(screening_codes))
        == len(candidate_codes)
    )
    assert set(screening_codes) == set(candidate_codes)

    screening_serialization = meta.get("screening_group_serialization") or {}
    assert screening_serialization.get("format") == SCREENING_SERIALIZATION_FORMAT
    assert int(screening_serialization.get("line_count") or 0) > 1
    assert int(screening_serialization.get("max_line_length") or 0) <= int(
        screening_serialization.get("max_allowed_line_length") or 0
    )

    screening_validation = meta.get("screening_group_validation") or {}
    assert screening_validation.get("status") == "passed"
    assert screening_validation.get("candidate_codes_exact_match") is True
    assert screening_validation.get("member_rows_count_matches") is True
    assert screening_validation.get("member_rows_well_formed") is True
    assert screening_validation.get("json_roundtrip_matches") is True
    assert screening_validation.get("line_addressable") is True

    assert not (runtime_dir / "peer_groups.json").exists()
    assert not (runtime_dir / "company_research_view.json").exists()
    assert not (runtime_dir / "details").exists()
    assert "peer_group_file" not in meta
    assert "company_research_file" not in meta

    # Structural thresholds are intentionally NOT copied here. split_snapshot.py
    # is the calculation source; downstream validation only checks that both
    # formal runtime files carry the exact same declared rule.
    structural_rule = meta.get("structural_rule") or {}
    assert structural_rule
    assert structural_rule == candidate.get("structural_rule")

    eligibility_audit = meta.get("eligibility_audit")
    if eligibility_audit:
        universe = int(eligibility_audit.get("universe_count") or 0)
        eligible = int(eligibility_audit.get("eligible_count") or 0)
        exclusions = eligibility_audit.get("exclusive_first_failure_counts") or {}
        assert universe == eligible + sum(
            int(value or 0) for value in exclusions.values()
        )
        assert eligible == int(meta.get("source_candidate_count") or 0)

    return {
        "runtime_kind": meta.get("runtime_kind"),
        "runtime_format": meta.get("runtime_format"),
        "trade_date": snapshot_meta.get("trade_date"),
        "source_candidate_count": meta.get("source_candidate_count"),
        "candidate_count": meta.get("candidate_count"),
        "screening_group_count": meta.get("screening_group_count"),
        "screening_group_singleton_count": meta.get("screening_group_singleton_count"),
        "screening_group_max_size": meta.get("screening_group_max_size"),
        "screening_group_coverage": meta.get("screening_group_coverage"),
        "screening_group_serialization": screening_serialization,
        "eligibility_audit": eligibility_audit,
        "validation": validation.get("status"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", nargs="?", default="data/snapshot.json")
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
    normalize_runtime_meta(runtime_dir)
    run_script(
        "scripts/build_screening_groups.py",
        "--runtime-dir",
        str(runtime_dir),
    )

    summary = validate_runtime(runtime_dir)
    print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
