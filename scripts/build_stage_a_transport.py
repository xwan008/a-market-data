#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from contracts import YOY_UNIT

TRANSPORT_FORMAT = "stage_a_transport_v1"
TARGET_BATCH_CANDIDATE_COUNT = 20
BATCHES_PER_PART = 2


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def serialize_transport(payload: dict[str, Any]) -> str:
    """Compact multi-line JSON optimized for whole-file connector reads.

    Member rows stay compact and one-per-line. Each transport file is much
    smaller than the canonical screening_groups.json while preserving the exact
    group objects and deterministic execution-batch boundaries.
    """
    batches = payload["batches"]
    header = [(key, value) for key, value in payload.items() if key != "batches"]

    lines = ["{"]
    for key, value in header:
        lines.append(f'  {compact(key)}: {compact(value)},')
    lines.append('  "batches": [')

    for batch_offset, batch in enumerate(batches):
        lines.append("    {")
        lines.append(f'      "batch_index": {batch["batch_index"]},')
        lines.append(f'      "candidate_count": {batch["candidate_count"]},')
        lines.append(f'      "group_count": {batch["group_count"]},')
        lines.append(f'      "industry_codes": {compact(batch["industry_codes"])},')
        lines.append('      "groups": [')
        for group_offset, group in enumerate(batch["groups"]):
            lines.append("        {")
            lines.append(f'          "industry_code": {compact(group["industry_code"])},')
            lines.append(f'          "industry_name": {compact(group["industry_name"])},')
            lines.append(f'          "candidate_count": {group["candidate_count"]},')
            lines.append(f'          "single_candidate": {compact(group["single_candidate"])},')
            lines.append(f'          "industry_context": {compact(group["industry_context"])},')
            lines.append('          "members": [')
            members = group["members"]
            for member_offset, member in enumerate(members):
                suffix = "," if member_offset < len(members) - 1 else ""
                lines.append(f"            {compact(member)}{suffix}")
            lines.append("          ]")
            suffix = "," if group_offset < len(batch["groups"]) - 1 else ""
            lines.append(f"        }}{suffix}")
        lines.append("      ]")
        suffix = "," if batch_offset < len(batches) - 1 else ""
        lines.append(f"    }}{suffix}")

    lines.append("  ]")
    lines.append("}")
    return "\n".join(lines) + "\n"


def build_batches(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    batches: list[dict[str, Any]] = []
    current_groups: list[dict[str, Any]] = []
    current_count = 0

    def close_current() -> None:
        nonlocal current_groups, current_count
        if not current_groups:
            return
        batches.append(
            {
                "batch_index": len(batches) + 1,
                "candidate_count": current_count,
                "group_count": len(current_groups),
                "industry_codes": [g["industry_code"] for g in current_groups],
                "groups": current_groups,
            }
        )
        current_groups = []
        current_count = 0

    for group in groups:
        group_count = int(group.get("candidate_count") or 0)
        if group_count <= 0:
            raise SystemExit(f"invalid screening group candidate_count: {group}")

        if current_groups and current_count + group_count > TARGET_BATCH_CANDIDATE_COUNT:
            close_current()

        current_groups.append(group)
        current_count += group_count

        if group_count > TARGET_BATCH_CANDIDATE_COUNT:
            close_current()

    close_current()
    return batches


def flatten_codes(groups: list[dict[str, Any]], code_index: int) -> list[str]:
    return [
        str(member[code_index])
        for group in groups
        for member in (group.get("members") or [])
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", default="data/runtime")
    args = parser.parse_args()

    runtime_dir = Path(args.runtime_dir)
    meta_path = runtime_dir / "meta.json"
    meta = load_json(meta_path)

    screening_path = Path(meta["screening_group_file"])
    screening = load_json(screening_path)

    if screening.get("yoy_unit") != YOY_UNIT or meta.get("yoy_unit") != YOY_UNIT:
        raise SystemExit("unexpected YoY unit while building Stage A transport")

    groups = screening.get("groups") or []
    member_columns = screening.get("member_columns") or []
    if "code" not in member_columns:
        raise SystemExit("screening member_columns missing code")
    code_index = member_columns.index("code")

    candidate_count = int(screening.get("candidate_count") or 0)
    group_count = int(screening.get("group_count") or 0)
    source_codes = flatten_codes(groups, code_index)

    if len(groups) != group_count or len(source_codes) != candidate_count:
        raise SystemExit("canonical screening_groups count mismatch")
    if len(source_codes) != len(set(source_codes)):
        raise SystemExit("canonical screening_groups codes are not unique")

    batches = build_batches(groups)
    reconstructed_groups = [group for batch in batches for group in batch["groups"]]
    if reconstructed_groups != groups:
        raise SystemExit("Stage A transport batch construction changed group order/content")

    batch_candidate_total = sum(batch["candidate_count"] for batch in batches)
    if batch_candidate_total != candidate_count:
        raise SystemExit("Stage A transport candidate total mismatch")

    for batch in batches:
        if batch["candidate_count"] > TARGET_BATCH_CANDIDATE_COUNT:
            if batch["group_count"] != 1:
                raise SystemExit("oversized Stage A batch contains more than one group")
            only_group = batch["groups"][0]
            if int(only_group.get("candidate_count") or 0) <= TARGET_BATCH_CANDIDATE_COUNT:
                raise SystemExit("Stage A batch exceeds target without oversized source group")

    parts: list[dict[str, Any]] = []
    for start in range(0, len(batches), BATCHES_PER_PART):
        part_batches = batches[start : start + BATCHES_PER_PART]
        parts.append(
            {
                "part_index": len(parts) + 1,
                "batches": part_batches,
                "candidate_count": sum(b["candidate_count"] for b in part_batches),
            }
        )

    for stale in runtime_dir.glob("stage_a_transport_*.json"):
        stale.unlink()

    files: list[str] = []
    part_candidate_counts: list[int] = []
    part_batch_indices: list[list[int]] = []
    written_payloads: list[dict[str, Any]] = []

    for part in parts:
        filename = f"stage_a_transport_{part['part_index']:02d}.json"
        path = runtime_dir / filename
        payload = {
            "runtime_format": TRANSPORT_FORMAT,
            "trade_date": screening.get("trade_date"),
            "yoy_unit": YOY_UNIT,
            "source_screening_group_file": meta["screening_group_file"],
            "candidate_count": candidate_count,
            "group_count": group_count,
            "member_columns": member_columns,
            "target_batch_candidate_count": TARGET_BATCH_CANDIDATE_COUNT,
            "part_index": part["part_index"],
            "part_count": len(parts),
            "batch_count": len(batches),
            "batch_indices": [b["batch_index"] for b in part["batches"]],
            "part_candidate_count": part["candidate_count"],
            "batches": part["batches"],
        }
        text = serialize_transport(payload)
        path.write_text(text, encoding="utf-8")
        parsed = json.loads(text)
        if parsed != payload:
            raise SystemExit(f"transport JSON roundtrip mismatch: {filename}")

        files.append(f"{runtime_dir.as_posix()}/{filename}")
        part_candidate_counts.append(part["candidate_count"])
        part_batch_indices.append(payload["batch_indices"])
        written_payloads.append(payload)

    transported_groups = [
        group
        for payload in written_payloads
        for batch in payload["batches"]
        for group in batch["groups"]
    ]
    transported_codes = flatten_codes(transported_groups, code_index)

    validation = {
        "status": "passed",
        "source_groups_exact_match": transported_groups == groups,
        "candidate_codes_exact_order_match": transported_codes == source_codes,
        "candidate_codes_unique": len(transported_codes) == len(set(transported_codes)),
        "candidate_count_matches": len(transported_codes) == candidate_count,
        "group_count_matches": len(transported_groups) == group_count,
        "batch_count_matches": sum(len(p["batches"]) for p in written_payloads) == len(batches),
        "part_count_matches": len(files) == len(parts),
        "trade_date_matches": all(
            p["trade_date"] == screening.get("trade_date") for p in written_payloads
        ),
        "member_columns_match": all(
            p["member_columns"] == member_columns for p in written_payloads
        ),
    }
    if not all(value is True for key, value in validation.items() if key != "status"):
        raise SystemExit(f"Stage A transport validation failed: {validation}")

    meta["stage_a_transport"] = {
        "format": TRANSPORT_FORMAT,
        "source_screening_group_file": meta["screening_group_file"],
        "files": files,
        "part_count": len(parts),
        "batch_count": len(batches),
        "batches_per_part": BATCHES_PER_PART,
        "target_batch_candidate_count": TARGET_BATCH_CANDIDATE_COUNT,
        "candidate_count": candidate_count,
        "group_count": group_count,
        "part_candidate_counts": part_candidate_counts,
        "part_batch_indices": part_batch_indices,
        "validation": validation,
    }

    runtime_validation = meta.get("runtime_validation") or {}
    runtime_validation["stage_a_transport_valid"] = True
    meta["runtime_validation"] = runtime_validation
    write_json(meta_path, meta)

    print(
        "Stage A transport ready: "
        f"parts={len(parts)} batches={len(batches)} candidates={candidate_count} "
        f"part_candidates={part_candidate_counts}"
    )


if __name__ == "__main__":
    main()
