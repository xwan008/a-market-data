"""Read-only, point-in-time archive of the two published A-share research products.

Writes ONLY validation/archive/<trade_date>/.  Once archived, a day's files
are immutable; later source revisions cannot silently rewrite old decisions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SOURCE = {
    "trend_registry.json": "research/trend_registry.json",
    "trend_handoff.json": "research/trend_handoff.json",
    "trend_buy_formal_result.json": "research/trend_buy_formal_result.json",
    "trend_buy_handoff.json": "research/trend_buy_handoff.json",
}
ARCHIVE_ROOT = ROOT / "validation" / "archive"


def sha_blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def frozen_universe(registry: dict, trade_date: str) -> dict:
    """Freeze *as-of* constituent identities, not constituents seen in the future."""
    result = {}
    for trend in registry.get("trends", []):
        codes, missing = set(), []
        industry_codes = trend.get("industry_codes") or []
        for industry in industry_codes:
            path = ROOT / "data" / "low_risk" / "by_industry" / str(industry) / "manifest.json"
            if not path.is_file():
                missing.append(str(industry) + ":missing")
                continue
            m = load(path)
            if m.get("trade_date") != trade_date or m.get("industry_code") != industry:
                missing.append(str(industry) + ":stale_or_mismatched")
                continue
            entries = m.get("universe_company_codes") or []
            if not entries:
                missing.append(str(industry) + ":empty")
            codes.update(str(c).zfill(6) for c in entries if str(c).zfill(6).isdigit())
        result[trend["trend_name"]] = {
            "market_state": trend.get("market_state"),
            "trend_state": trend.get("trend_state"),
            "lifecycle_status": trend.get("lifecycle_status"),
            "first_seen_trade_date": trend.get("first_seen_trade_date"),
            "last_verified_trade_date": trend.get("last_verified_trade_date"),
            "industry_codes": industry_codes,
            "constituents": sorted(codes),
            "universe_issues": missing,
            "constituents_usable": bool(codes) and not missing,
        }
    return result


def archive(requested_date: str | None = None) -> str:
    trade_date = requested_date or datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    dest = ARCHIVE_ROOT / trade_date
    if dest.exists():
        required = [*SOURCE, "universe.json", "manifest.json"]
        if not all((dest / name).is_file() for name in required):
            raise ValueError("PARTIAL_ARCHIVE_EXISTS:" + trade_date)
        print("VALIDATION_ARCHIVE_EXISTS_IMMUTABLE", trade_date)
        return "existing"

    originals = {}
    for name, relpath in SOURCE.items():
        path = ROOT / relpath
        originals[name] = (path.read_bytes(), load(path))
        if originals[name][1].get("trade_date") != trade_date:
            print("VALIDATION_WAIT_FOR_SAME_DAY_RESEARCH", name, trade_date)
            return "waiting"

    registry = originals["trend_registry.json"][1]
    formal = originals["trend_buy_formal_result.json"][1]
    trend_handoff = originals["trend_handoff.json"][1]
    buy_handoff = originals["trend_buy_handoff.json"][1]
    audit = registry.get("scan_audit") or {}
    if (registry.get("status") != "COMPLETE"
            or not audit.get("full_market_scan_completed")
            or registry.get("generated_at", "")[:10] != trade_date):
        print("VALIDATION_WAIT_FOR_COMPLETE_CLOSE_RESEARCH", trade_date)
        return "waiting"
    if (formal.get("mode") != "FORMAL" or formal.get("status") != "COMPLETE"
            or formal.get("production_eligible") is not True):
        print("VALIDATION_WAIT_FOR_FORMAL_BUY_RESEARCH", trade_date)
        return "waiting"
    if (buy_handoff.get("status") != "COMPLETE"
            or buy_handoff.get("shadow") is not False
            or buy_handoff.get("source_run_id") != formal.get("run_id")
            or buy_handoff.get("source_formal_blob_sha")
                != sha_blob(originals["trend_buy_formal_result.json"][0])):
        print("VALIDATION_WAIT_FOR_VERIFIED_HANDOFF", trade_date)
        return "waiting"
    if trend_handoff.get("result_kind") != "a_share_trend_handoff":
        raise ValueError("TREND_HANDOFF_KIND_MISMATCH")

    universe = frozen_universe(registry, trade_date)
    metadata = {
        "schema_version": 1,
        "trade_date": trade_date,
        "archived_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "research_run_id": formal["run_id"],
        "archive_policy": "immutable_point_in_time_after_close",
        "constituents_frozen_at_archive": True,
        "sources": {
            name: {"path": rel, "git_blob_sha": sha_blob(originals[name][0])}
            for name, rel in SOURCE.items()
        },
        "trend_count": len(universe),
        "company_research_count": sum(len(formal.get(status, []))
                                      for status in ("ready", "wait", "uncertain", "drop")),
    }

    # Write the manifest last.  GitHub Actions stages/commits this new directory
    # only after the complete and verified source copies exist.
    dest.mkdir(parents=True, exist_ok=False)
    try:
        for name in SOURCE:
            (dest / name).write_bytes(originals[name][0])
        (dest / "universe.json").write_text(
            json.dumps(universe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (dest / "manifest.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception:
        # A partial archive must never be published.
        for child in dest.glob("*"):
            child.unlink()
        dest.rmdir()
        raise
    print("VALIDATION_ARCHIVE_CREATED", trade_date, len(universe))
    return "created"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trade-date", default=None)
    args = parser.parse_args()
    archive(args.trade_date)


if __name__ == "__main__":
    main()
