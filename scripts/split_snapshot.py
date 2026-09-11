#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", default="data/snapshot.json")
    parser.add_argument("--output-dir", default="data/runtime")
    parser.add_argument("--shard-size", type=int, default=20)
    args = parser.parse_args()

    if args.shard_size <= 0:
        raise SystemExit("shard-size must be > 0")

    snapshot_path = Path(args.input)
    output_dir = Path(args.output_dir)
    snapshot = load_json(snapshot_path)

    candidates = snapshot.get("candidates") or {}
    expected = int((snapshot.get("counts") or {}).get("candidates") or 0)
    if not candidates or len(candidates) != expected:
        raise SystemExit(
            f"candidate count mismatch: expected={expected} actual={len(candidates)}"
        )

    industry_state = snapshot.get("industry_state") or {}
    level3 = industry_state.get("level3") or {}
    trade_date = snapshot.get("trade_date")
    if not trade_date:
        raise SystemExit("snapshot.trade_date is required")

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    items = list(candidates.items())
    candidate_files: list[str] = []

    for index, start in enumerate(range(0, len(items), args.shard_size)):
        chunk_items = items[start : start + args.shard_size]
        chunk = dict(chunk_items)
        industry_codes = {
            item.get("industry_code")
            for item in chunk.values()
            if item.get("industry_code")
        }
        industries = {
            code: level3[code]
            for code in industry_codes
            if code in level3
        }

        filename = f"candidates_{index:03d}.json"
        path = output_dir / filename
        payload = {
            "schema_version": 1,
            "trade_date": trade_date,
            "shard_index": index,
            "candidate_count": len(chunk),
            "industry_state": industries,
            "candidates": chunk,
        }
        write_json(path, payload)
        candidate_files.append(f"{output_dir.as_posix()}/{filename}")

    meta_snapshot = {
        key: value
        for key, value in snapshot.items()
        if key not in {"candidates", "industry_state"}
    }
    meta_snapshot["industry_state"] = {
        key: value for key, value in industry_state.items() if key != "level3"
    }

    meta = {
        "schema_version": 1,
        "runtime_format": "candidate_shards_v1",
        "snapshot": meta_snapshot,
        "candidate_count": len(candidates),
        "shard_size": args.shard_size,
        "shard_count": len(candidate_files),
        "candidate_files": candidate_files,
    }
    write_json(output_dir / "meta.json", meta)

    print(
        f"runtime shards ready: trade_date={trade_date} "
        f"candidates={len(candidates)} shards={len(candidate_files)}"
    )


if __name__ == "__main__":
    main()
