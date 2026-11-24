"""Read-only parity replay of actual published trend records.

This tests publication contracts and lifecycle behavior, not investment returns.
Historical states remain exactly as published; no model is re-run and no
prices or historical industry D1s are fabricated.
"""
import argparse
from collections import Counter
from datetime import datetime
from hashlib import sha1
import json
from pathlib import Path
import sys
from unittest.mock import patch


def load(path):
    return json.loads(path.read_text("utf-8"))


def blob_sha(path):
    data = path.read_bytes()
    return sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--code-root", type=Path, required=True)
    parser.add_argument("--cutover-registry", type=Path, required=True)
    parser.add_argument("--cutover-handoff", type=Path, required=True)
    parser.add_argument("--first-24-registry", type=Path, required=True)
    parser.add_argument("--first-24-handoff", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.code_root.resolve()))
    from scripts.trend_registry import validate as migration_gate
    from scripts.validate_trend_publication_pair import validate as pair_gate
    from scripts.render_trend_report import render, research_input
    from scripts.industry_lifecycle import industry_review_records

    # Replay every archived official pair, using a cross-day transition only
    # when the published source blob is actually available. Missing prior
    # snapshots are disclosed rather than treated as successful migrations.
    snapshots = {
        day.name: (day / "trend_registry.json", day / "trend_handoff.json")
        for day in sorted(args.archive.iterdir()) if day.is_dir()
        and (day / "trend_registry.json").is_file()
        and (day / "trend_handoff.json").is_file()
    }
    snapshots["2026-11-23-cutover"] = (args.cutover_registry, args.cutover_handoff)
    snapshots["2026-11-24-first"] = (args.first_24_registry, args.first_24_handoff)
    prior_by_blob = {blob_sha(paths[0]): (key, load(paths[0]))
                     for key, paths in snapshots.items()}

    results = []
    for key, (rp, hp) in sorted(snapshots.items()):
        registry, handoff = load(rp), load(hp)
        assert registry["trade_date"] == handoff["trade_date"], key
        errors = sorted(pair_gate(registry, handoff))
        row = {"snapshot": key, "registry_blob": blob_sha(rp),
               "handoff_blob": blob_sha(hp), "pair_errors": errors,
               "themes": len(registry["trends"]),
               "industry_rows": sum(len(t.get("industry_assessments") or [])
                                    for t in registry["trends"]),
               "handoff": [(s["rank"], s["trend_name"], s["industry_codes"])
                           for s in handoff["signals"]]}
        audit = registry.get("scan_audit") or {}
        if audit.get("sw3_lifecycle_contract") == "SW3_V1" and not errors:
            records = industry_review_records(registry)
            active = research_input(registry, handoff)["active_industries"]
            row["effective_records"] = records
            row["active_codes"] = [(x["theme_episode_id"], x["assessment"]["industry_code"])
                                   for x in active]
            row["rendered_report"] = render(registry, handoff)
        if key == "2026-11-23-cutover":
            row["migration"] = "historical one-off; separately tested with replay-only validator"
        else:
            # The Nov 24 corrected close must be compared to the initial Nov 24
            # publication, not counted as a new trading day.
            revisions = audit.get("same_day_revisions") or []
            last = revisions[-1] if revisions else {}
            if (key == "2026-11-24" and last.get("industry_review_results") is not None):
                source = last["previous_registry_blob_sha"]
            else:
                source = (audit.get("state_migration_gate") or {}).get("previous_registry_blob_sha")
            prior_entry = prior_by_blob.get(source)
            if prior_entry:
                prior_key, prior = prior_entry
                if prior["trade_date"] == registry["trade_date"]:
                    # Read-only, historical replay: use the recorded revision
                    # instant for the clock, never change the production guard.
                    stamp = datetime.fromisoformat(registry["generated_at"])
                    with patch("scripts.trend_registry.datetime") as clock:
                        clock.now.return_value = stamp
                        clock.fromisoformat.side_effect = datetime.fromisoformat
                        verdict = migration_gate(prior, registry, source)
                else:
                    verdict = migration_gate(prior, registry, source)
                row["migration"] = {"source": prior_key, "errors": sorted(verdict)}
            else:
                row["migration"] = "source snapshot unavailable"
        results.append(row)

    latest = next(x for x in results if x["snapshot"] == "2026-11-24")
    first = next(x for x in results if x["snapshot"] == "2026-11-24-first")
    cutover = next(x for x in results if x["snapshot"] == "2026-11-23-cutover")
    assert not latest["pair_errors"] and not latest["migration"]["errors"]
    assert not first["pair_errors"] and not first["migration"]["errors"]
    assert not cutover["pair_errors"]
    assert first["active_codes"] == latest["active_codes"]
    assert first["handoff"] == latest["handoff"]
    assert len(latest["active_codes"]) == 10
    assert sum(not r["tracking_active"] for r in latest["effective_records"]) == 4
    assert len(latest["handoff"]) == 3
    summary = {
        "archived_days": len(results) - 2,
        "published_pairs_checked": len(results),
        "pair_pass": sum(not r["pair_errors"] for r in results),
        "pair_issues": [r["snapshot"] for r in results if r["pair_errors"]],
        "migration_checked": sum(isinstance(r["migration"], dict) for r in results),
        "migration_pass": sum(isinstance(r["migration"], dict) and not r["migration"]["errors"]
                              for r in results),
        "migration_issues": [r["snapshot"] for r in results
                             if isinstance(r["migration"], dict) and r["migration"]["errors"]],
        "migration_missing_prior": [r["snapshot"] for r in results
                                    if r["migration"] == "source snapshot unavailable"],
        "latest_active": len(latest["active_codes"]),
        "latest_expired": sum(not r["tracking_active"] for r in latest["effective_records"]),
        "latest_handoff": latest["handoff"],
        "latest_phase_counts": dict(Counter(
            (r["d123_stage"] or "unstaged") + "/" + (r["d123_decision"] or "unknown")
            for r in latest["effective_records"])),
    }
    print(json.dumps({"summary": summary, "snapshots": results},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
