#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

TARGET_LINE_LENGTH = 200
MAX_LINE_LENGTH = 280


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def wrap_minified_json(payload: dict[str, Any]) -> str:
    """Insert whitespace-only line breaks into minified JSON.

    Breaks are emitted only after structural delimiters outside JSON strings, so
    parsing the result produces exactly the original payload. The target line
    length keeps each formal 40-line connector read below the observed response
    budget while still reducing the number of reads versus the original view.
    """
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    lines: list[str] = []
    start = 0
    in_string = False
    escaped = False
    last_safe_break: int | None = None

    for index, char in enumerate(raw):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        else:
            if char == '"':
                in_string = True
            elif char in ",]}{[":
                last_safe_break = index + 1

        current_length = index + 1 - start
        if current_length >= TARGET_LINE_LENGTH and last_safe_break is not None:
            if last_safe_break <= start:
                continue
            lines.append(raw[start:last_safe_break])
            start = last_safe_break
            last_safe_break = None

    if start < len(raw):
        lines.append(raw[start:])

    if not lines:
        lines = [raw]

    max_line_length = max(len(line) for line in lines)
    if max_line_length > MAX_LINE_LENGTH:
        raise SystemExit(
            f"compacted screening line too long: {max_line_length} > {MAX_LINE_LENGTH}"
        )

    text = "\n".join(lines) + "\n"
    if json.loads(text) != payload:
        raise SystemExit("screening compaction changed JSON payload")
    return text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", default="data/runtime")
    args = parser.parse_args()

    runtime_dir = Path(args.runtime_dir)
    meta_path = runtime_dir / "meta.json"
    meta = load_json(meta_path)
    screening_path = Path(meta["screening_group_file"])
    payload = load_json(screening_path)

    original_candidate_count = int(payload.get("candidate_count") or 0)
    original_group_count = int(payload.get("group_count") or 0)
    original_columns = payload.get("member_columns") or []
    if "code" not in original_columns:
        raise SystemExit("screening member_columns missing code")
    code_index = original_columns.index("code")
    original_codes = [
        str(member[code_index])
        for group in (payload.get("groups") or [])
        for member in (group.get("members") or [])
    ]

    text = wrap_minified_json(payload)
    screening_path.write_text(text, encoding="utf-8")
    parsed = json.loads(text)
    lines = text.splitlines()
    max_line_length = max((len(line) for line in lines), default=0)

    parsed_codes = [
        str(member[code_index])
        for group in (parsed.get("groups") or [])
        for member in (group.get("members") or [])
    ]

    validation = meta.get("screening_group_validation") or {}
    validation.update(
        {
            "status": "passed",
            "candidate_codes_unique": len(parsed_codes) == len(set(parsed_codes)),
            "candidate_codes_exact_match": parsed_codes == original_codes,
            "candidate_count_matches": len(parsed_codes) == original_candidate_count,
            "member_rows_count_matches": len(parsed_codes) == original_candidate_count,
            "json_roundtrip_matches": parsed == payload,
            "line_addressable": True,
        }
    )
    if int(parsed.get("group_count") or 0) != original_group_count:
        raise SystemExit("screening compaction changed group count")
    if not all(
        value is True for key, value in validation.items() if key != "status"
    ):
        raise SystemExit(f"screening compaction validation failed: {validation}")

    serialization = meta.get("screening_group_serialization") or {}
    serialization.update(
        {
            "line_count": len(lines),
            "max_line_length": max_line_length,
            "max_allowed_line_length": MAX_LINE_LENGTH,
        }
    )
    meta["screening_group_serialization"] = serialization
    meta["screening_group_validation"] = validation

    # Keep a single formal Stage A fact source. Earlier experimental derived
    # transport shards are removed so bootstrap context stays minimal.
    for stale in runtime_dir.glob("stage_a_transport_*.json"):
        stale.unlink()
    meta.pop("stage_a_transport", None)

    runtime_validation = meta.get("runtime_validation") or {}
    runtime_validation["screening_group_view_valid"] = True
    runtime_validation["screening_group_line_addressable"] = True
    runtime_validation["screening_group_compaction_valid"] = True
    runtime_validation.pop("stage_a_transport_valid", None)
    meta["runtime_validation"] = runtime_validation
    write_json(meta_path, meta)

    print(
        "screening groups compacted without semantic changes: "
        f"lines={len(lines)} max_line_length={max_line_length} "
        f"40_line_reads={(len(lines) + 39) // 40}"
    )


if __name__ == "__main__":
    main()
