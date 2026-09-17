#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from build_screening_groups import write_screening_json

EXTRA_STRUCTURE_FIELDS = [
    "high_60d",
    "low_60d",
    "ma20",
    "ma60",
    "support_low",
    "support_high",
    "support_center",
    "volume_zone_low",
    "volume_zone_high",
    "volume_zone_center",
    "resistance_low",
    "resistance_high",
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def enrich_payload(
    payload: dict[str, Any],
    candidate_columns: list[str],
    candidate_by_code: dict[str, list[Any]],
) -> dict[str, Any]:
    member_columns = list(payload.get("member_columns") or [])
    if "code" not in member_columns:
        raise SystemExit("screening cache member_columns missing code")

    missing_source_fields = [
        field for field in EXTRA_STRUCTURE_FIELDS if field not in candidate_columns
    ]
    if missing_source_fields:
        raise SystemExit(
            f"candidate source missing structure fields: {missing_source_fields}"
        )

    append_fields = [field for field in EXTRA_STRUCTURE_FIELDS if field not in member_columns]
    code_index = member_columns.index("code")
    candidate_index = {name: idx for idx, name in enumerate(candidate_columns)}

    if append_fields:
        for group in payload.get("groups") or []:
            for member in group.get("members") or []:
                code = str(member[code_index])
                source = candidate_by_code.get(code)
                if source is None:
                    raise SystemExit(f"screening cache code missing from candidates: {code}")
                member.extend(source[candidate_index[field]] for field in append_fields)
        member_columns.extend(append_fields)

    payload["member_columns"] = member_columns
    payload["cache_role"] = "candidate_fact_cache_only"
    payload["authoritative_universe_source"] = "data/research/company_industry_index.json"
    payload["fallback_fact_source"] = "data/shards/*.json"
    payload["purpose"] = (
        "candidate-scoped performance cache for repeated low-risk research reads; "
        "contains valuation, financial-quality and price-structure facts. It is not "
        "an authoritative industry universe and must never veto companies that exist "
        "in company_industry_index; cache misses fall back to data/shards/*.json"
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", default="data/runtime")
    args = parser.parse_args()

    runtime_dir = Path(args.runtime_dir)
    meta_path = runtime_dir / "meta.json"
    meta = load_json(meta_path)

    candidate_path = Path(meta["candidate_file"])
    candidate = load_json(candidate_path)
    candidate_columns = list(candidate.get("columns") or [])
    candidate_rows = list(candidate.get("rows") or [])
    if "code" not in candidate_columns:
        raise SystemExit("candidate columns missing code")
    candidate_code_index = candidate_columns.index("code")
    candidate_by_code = {
        str(row[candidate_code_index]): row for row in candidate_rows
    }

    screening_path = Path(meta["screening_group_file"])
    screening = enrich_payload(
        load_json(screening_path), candidate_columns, candidate_by_code
    )
    serialization = write_screening_json(screening_path, screening)

    shard_dir = Path(meta["screening_group_industry_shard_dir"])
    shard_index_path = Path(meta["screening_group_index_file"])
    shard_index = load_json(shard_index_path)

    total_shard_codes: set[str] = set()
    member_columns = list(screening["member_columns"])
    code_index = member_columns.index("code")

    for industry_code, item in (shard_index.get("industries") or {}).items():
        shard_path = Path(item["file"])
        shard_payload = enrich_payload(
            load_json(shard_path), candidate_columns, candidate_by_code
        )
        shard_serialization = write_screening_json(shard_path, shard_payload)
        item["line_count"] = shard_serialization["line_count"]
        item["max_line_length"] = shard_serialization["max_line_length"]
        for group in shard_payload.get("groups") or []:
            for member in group.get("members") or []:
                total_shard_codes.add(str(member[code_index]))

    shard_index["member_columns"] = member_columns
    shard_index["cache_role"] = "candidate_fact_cache_only"
    shard_index["authoritative_universe_source"] = (
        "data/research/company_industry_index.json"
    )
    write_json(shard_index_path, shard_index)

    screening_codes = {
        str(member[code_index])
        for group in screening.get("groups") or []
        for member in group.get("members") or []
    }
    candidate_codes = set(candidate_by_code)
    if screening_codes != candidate_codes or total_shard_codes != candidate_codes:
        raise SystemExit(
            "enriched screening cache coverage changed: "
            f"candidates={len(candidate_codes)} screening={len(screening_codes)} "
            f"industry_shards={len(total_shard_codes)}"
        )

    meta["screening_group_member_columns"] = member_columns
    meta["screening_group_cache_role"] = "candidate_fact_cache_only"
    meta["screening_group_authoritative_universe_source"] = (
        "data/research/company_industry_index.json"
    )
    meta["screening_group_fallback_fact_source"] = "data/shards/*.json"
    meta["screening_group_structure_fields"] = EXTRA_STRUCTURE_FIELDS
    meta["screening_group_serialization"] = {
        **(meta.get("screening_group_serialization") or {}),
        "format": serialization["format"],
        "line_count": serialization["line_count"],
        "max_line_length": serialization["max_line_length"],
        "max_allowed_line_length": serialization["max_allowed_line_length"],
    }
    validation = meta.get("screening_group_validation") or {}
    validation["structure_cache_enriched"] = True
    validation["candidate_codes_exact_match"] = True
    validation["member_rows_well_formed"] = True
    meta["screening_group_validation"] = validation
    write_json(meta_path, meta)

    print(
        "screening group cache enriched: "
        f"candidates={len(candidate_codes)} industries={len(shard_index.get('industries') or {})} "
        f"added_structure_fields={len(EXTRA_STRUCTURE_FIELDS)}"
    )


if __name__ == "__main__":
    main()
