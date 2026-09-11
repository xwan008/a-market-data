from __future__ import annotations

import argparse
import json
from pathlib import Path

from snapshot_io import write_snapshot


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="data/snapshot.json")
    args = parser.parse_args()

    path = Path(args.path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    previous = payload.get("source") or {}
    payload["source"] = {
        "repository": "xwan008/a-market-data",
        "mode": "local_repository_data",
        "latest_generated_at": previous.get("latest_upstream_generated_at")
        or payload.get("generated_at"),
        "industry_state_generated_at": previous.get("industry_state_generated_at")
        or ((payload.get("industry_state") or {}).get("generated_at")),
    }
    write_snapshot(path, payload)
    print(f"normalized snapshot source: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
