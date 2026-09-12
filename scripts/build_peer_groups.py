#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

PEER_GROUP_FORMAT = "peer_group_view_v1"

MEMBER_FIELDS = [
    "code",
    "name",
    "price",
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

    required = {
        "code",
        "name",
        "industry_code",
        "industry_name",
        *MEMBER_FIELDS,
        *INDUSTRY_CONTEXT_FIELDS,
    }
    missing = sorted(required - set(columns))
    if missing:
        raise SystemExit(f"candidate columns missing for peer view: {missing}")

    grouped: dict[str, list[list[Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[index["industry_code"]] or "")].append(row)

    groups: list[dict[str, Any]] = []
    peer_codes: list[str] = []
    for industry_code in sorted(grouped):
        group_rows = sorted(
            grouped[industry_code],
            key=lambda row: str(row[index["code"]] or ""),
        )
        first = group_rows[0]
        members: list[dict[str, Any]] = []
        for row in group_rows:
            member = {field: row[index[field]] for field in MEMBER_FIELDS}
            members.append(member)
            peer_codes.append(str(member["code"]))

        groups.append(
            {
                "industry_code": industry_code,
                "industry_name": first[index["industry_name"]],
                "candidate_count": len(members),
                "single_candidate": len(members) == 1,
                "industry_context": {
                    field.removeprefix("industry_"): first[index[field]]
                    for field in INDUSTRY_CONTEXT_FIELDS
                },
                "members": members,
            }
        )

    candidate_codes = [str(row[index["code"]]) for row in rows]
    candidate_set = set(candidate_codes)
    peer_set = set(peer_codes)
    codes_unique = len(peer_codes) == len(peer_set)
    exact_match = candidate_set == peer_set and len(candidate_codes) == len(peer_codes)
    if not codes_unique or not exact_match:
        raise SystemExit(
            "peer group candidate coverage mismatch: "
            f"candidate={len(candidate_codes)} peer={len(peer_codes)} "
            f"unique={codes_unique} exact_match={exact_match}"
        )

    singleton_count = sum(1 for group in groups if group["single_candidate"])
    max_group_size = max((group["candidate_count"] for group in groups), default=0)
    peer_filename = "peer_groups.json"
    peer_path = runtime_dir / peer_filename
    peer_payload = {
        "runtime_format": PEER_GROUP_FORMAT,
        "trade_date": candidate_payload.get("trade_date"),
        "candidate_count": len(candidate_codes),
        "group_count": len(groups),
        "singleton_group_count": singleton_count,
        "max_group_size": max_group_size,
        "purpose": "deterministic peer grouping and raw comparison facts only; no score or ranking",
        "groups": groups,
    }
    write_json(peer_path, peer_payload)

    peer_validation = {
        "status": "passed",
        "candidate_codes_unique": codes_unique,
        "candidate_codes_exact_match": exact_match,
        "candidate_count_matches": len(peer_codes) == int(meta.get("candidate_count") or 0),
        "trade_date_matches": peer_payload.get("trade_date")
        == (meta.get("snapshot") or {}).get("trade_date"),
    }
    if not all(
        value is True
        for key, value in peer_validation.items()
        if key != "status"
    ):
        raise SystemExit(f"peer view validation failed: {peer_validation}")

    meta["peer_group_file"] = f"{runtime_dir.as_posix()}/{peer_filename}"
    meta["peer_group_format"] = PEER_GROUP_FORMAT
    meta["peer_group_count"] = len(groups)
    meta["peer_group_singleton_count"] = singleton_count
    meta["peer_group_max_size"] = max_group_size
    meta["peer_group_member_fields"] = MEMBER_FIELDS
    meta["peer_group_validation"] = peer_validation
    runtime_validation = meta.get("runtime_validation") or {}
    runtime_validation["peer_group_view_valid"] = True
    meta["runtime_validation"] = runtime_validation
    write_json(meta_path, meta)

    print(
        "peer view ready: "
        f"candidates={len(candidate_codes)} groups={len(groups)} "
        f"singletons={singleton_count} max_group_size={max_group_size}"
    )


if __name__ == "__main__":
    main()
