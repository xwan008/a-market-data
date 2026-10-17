#!/usr/bin/env python3
"""Production-only active trend validation with no historical bypass."""
import argparse
import json
import sys
try:
    from scripts.trend_registry import validate
except ModuleNotFoundError:
    from trend_registry import validate


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--previous", required=True)
    p.add_argument("--proposed", required=True)
    p.add_argument("--previous-blob-sha", required=True)
    p.add_argument("--snapshot")
    p.add_argument("--sector-audit")
    p.add_argument("--archive")
    a = p.parse_args(argv)
    try:
        def load(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        errors = validate(load(a.previous), load(a.proposed), a.previous_blob_sha,
                          snapshot=load(a.snapshot) if a.snapshot else None,
                          sector_audit=load(a.sector_audit) if a.sector_audit else None,
                          archive=load(a.archive) if a.archive else None)
    except (OSError, ValueError, TypeError) as exc:
        errors = ["input_error:" + str(exc)]
    print(json.dumps({"status": "PASS" if not errors else "BLOCKED", "errors": errors}, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
