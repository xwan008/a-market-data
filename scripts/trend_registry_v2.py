#!/usr/bin/env python3
"""V2 trend lifecycle: independent discovery, candidate continuity, cold exits.

Archived episodes are never read for ordinary research or used as evidence.
This module validates transitions and provides deterministic archive artifacts.
"""
import argparse
import copy
import json
import re
from pathlib import Path

TRACK = {"趋势确认", "候选趋势"}
MARKET = {"趋势确认", "候选趋势", "观察", "新异动", "高潮/衰退", "失效"}
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SHA = re.compile(r"^[0-9a-f]{40}$")


def tracking(item):
    return item.get("market_state") in TRACK and item.get("lifecycle_status") != "已失效"


def episode_key(name, first_seen):
    return f"{name}#{first_seen}"


def cutover(previous, source_sha):
    """One-time v1 -> v2 conversion, without rewriting old trend evidence."""
    if previous.get("schema_version") != 1 or previous.get("status") != "COMPLETE":
        raise ValueError("V1_COMPLETE_BASELINE_REQUIRED")
    if not isinstance(source_sha, str) or not SHA.fullmatch(source_sha):
        raise ValueError("REAL_SOURCE_BLOB_SHA_REQUIRED")
    active = []
    for item in previous["trends"]:
        if tracking(item):
            t = copy.deepcopy(item)
            t["episode_id"] = episode_key(t["trend_name"], t["first_seen_trade_date"])
            active.append(t)
    day = previous["trade_date"]
    out = {
        "schema_version": 2,
        "result_kind": "a_share_trend_registry",
        "trade_date": day,
        "generated_at": previous.get("generated_at"),
        "timezone": "Asia/Shanghai",
        "status": "COMPLETE",
        "scan_audit": {
            "mode": "v2_cutover", "previous_registry_trade_date": day,
            "original_trend_count": len(previous["trends"]),
            "active_trend_count": len(active),
            "archived_trend_count": len(previous["trends"]) - len(active),
            "source_legacy_blob_sha": source_sha,
            "state_migration_gate": {
                "mode": "v2_cutover", "previous_registry_trade_date": day,
                "previous_registry_blob_sha": source_sha,
                "current_trade_date": day, "reviews": [],
                "archived_count": len(previous["trends"]) - len(active),
            },
        },
        "trends": active,
        "invalidated_history": [],
        "recheck_queue": [],
    }
    return out


def exit_archive(previous, proposed, source_sha):
    """Freeze ALL previously non-tracked entries before they leave the live JSON."""
    if previous.get("schema_version") != 2 or proposed.get("schema_version") != 2:
        raise ValueError("V2_REQUIRED")
    if not isinstance(source_sha, str) or not SHA.fullmatch(source_sha):
        raise ValueError("REAL_SOURCE_BLOB_SHA_REQUIRED")
    return {
        "schema_version": 1,
        "result_kind": "a_share_trend_v2_exit_archive",
        "source_registry_trade_date": previous["trade_date"],
        "archive_trade_date": proposed["trade_date"],
        "source_registry_blob_sha": source_sha,
        "episodes": [copy.deepcopy(t) for t in previous["trends"] if not tracking(t)],
    }


def validate_v2(previous, proposed, source_sha, archive=None,
                snapshot=None, sector_audit=None):
    """Structural fail-closed V2 gate. External evidence truth is not asserted."""
    from scripts.validate_trend_state_migrations import (
        _valid_evidence, _market_state_evidence, _optional_sector_audit_valid,
        STATES, T_STATES, T_STATE_RANK)
    errors = []
    before, day = previous.get("trade_date"), proposed.get("trade_date")
    if proposed.get("schema_version") != 2 or proposed.get("result_kind") != "a_share_trend_registry":
        errors.append("v2_schema_invalid")
    if previous.get("schema_version") not in (1, 2):
        errors.append("unsupported_previous_schema")
    if previous.get("status") != "COMPLETE" or proposed.get("status") != "COMPLETE":
        errors.append("registry_not_complete")
    if not isinstance(before, str) or not DAY.fullmatch(before) or not isinstance(day, str) or not DAY.fullmatch(day):
        errors.append("invalid_trade_dates")
    if not isinstance(source_sha, str) or not SHA.fullmatch(source_sha):
        errors.append("invalid_previous_blob_sha")
    if snapshot is not None and (snapshot.get("trade_date") != day or
                                 snapshot.get("point_in_time_eligible") is not True or
                                 snapshot.get("auxiliary_only") is not True):
        errors.append("snapshot_invalid")
    if sector_audit is not None and not _optional_sector_audit_valid(sector_audit, day):
        errors.append("sector_audit_invalid")
    gate = (proposed.get("scan_audit") or {}).get("state_migration_gate") or {}
    if gate.get("previous_registry_blob_sha") != source_sha or gate.get("previous_registry_trade_date") != before or gate.get("current_trade_date") != day:
        errors.append("baseline_sha_or_date_not_frozen")
    if not isinstance(proposed.get("trends"), list) or not isinstance(previous.get("trends"), list):
        return errors + ["trends_not_list"]
    if not all(isinstance(t, dict) for t in previous["trends"] + proposed["trends"]):
        return errors + ["invalid_trend_entry"]
    names = [t.get("trend_name") for t in proposed["trends"]]
    ids = [t.get("episode_id") for t in proposed["trends"]]
    if not all(isinstance(n, str) and n for n in names) or len(set(names)) != len(names):
        errors.append("duplicate_or_missing_trend_names")
    if not all(isinstance(n, str) and n for n in ids) or len(set(ids)) != len(ids):
        errors.append("duplicate_or_missing_episode_ids")

    if previous.get("schema_version") == 1:
        if gate.get("mode") != "v2_cutover" or day != before:
            errors.append("invalid_v2_cutover_mode")
        if archive != previous:
            errors.append("legacy_archive_not_exact")
        expected = cutover(previous, source_sha)["trends"] if SHA.fullmatch(str(source_sha)) else []
        if proposed["trends"] != expected:
            errors.append("cutover_active_pool_not_exact")
        if gate.get("archived_count") != len(previous["trends"]) - len(expected):
            errors.append("cutover_archive_count_invalid")
        if (proposed.get("scan_audit") or {}).get("source_legacy_blob_sha") != source_sha:
            errors.append("cutover_legacy_source_invalid")
        return errors

    if not isinstance(before, str) or not isinstance(day, str) or day <= before or gate.get("mode") != "full_close":
        errors.append("invalid_v2_close_mode")
    prior_by_id = {t.get("episode_id"): t for t in previous["trends"]}
    curr_by_id = {t.get("episode_id"): t for t in proposed["trends"]}
    if len(prior_by_id) != len(previous["trends"]):
        errors.append("duplicate_previous_episode_id")
    reviews = gate.get("reviews", [])
    if not isinstance(reviews, list) or not all(isinstance(r, dict) for r in reviews):
        return errors + ["reviews_not_list"]
    by_id = {r.get("episode_id"): r for r in reviews}
    if len(by_id) != len(reviews):
        errors.append("duplicate_review_episode_id")
    continued = {t.get("episode_id") for t in previous["trends"] if tracking(t)}
    if set(by_id) != continued:
        errors.append("active_review_coverage_mismatch")
    for episode in continued:
        prior = prior_by_id[episode]
        now = curr_by_id.get(episode)
        if now is None:
            errors.append(f"{episode}:active_silently_removed")
            continue
        review = by_id.get(episode) or {}
        name = prior.get("trend_name")
        if now.get("trend_name") != name or now.get("first_seen_trade_date") != prior.get("first_seen_trade_date"):
            errors.append(f"{episode}:identity_changed")
        earlier = prior.get("state_history")
        current = now.get("state_history")
        if not isinstance(earlier, list) or not isinstance(current, list) or current[:len(earlier)] != earlier:
            errors.append(f"{episode}:history_rewritten")
            tail = []
        else:
            tail = current[len(earlier):]
        m0, m1 = prior.get("market_state"), now.get("market_state")
        t0, t1 = prior.get("trend_state"), now.get("trend_state")
        l0, l1 = prior.get("lifecycle_status"), now.get("lifecycle_status")
        if m0 not in STATES or m1 not in STATES or t0 not in T_STATES or t1 not in T_STATES:
            errors.append(f"{episode}:invalid_state")
            continue
        changed = (m0, t0, l0) != (m1, t1, l1)
        if review.get("decision") != ("CHANGE" if changed else "HOLD") or (
            review.get("previous_market_state"), review.get("proposed_market_state"),
            review.get("previous_trend_state"), review.get("proposed_trend_state")
        ) != (m0, m1, t0, t1):
            errors.append(f"{episode}:review_state_mismatch")
        if not isinstance(review.get("reason"), str) or len(review["reason"].strip()) < 12:
            errors.append(f"{episode}:review_reason_missing")
        if changed:
            if m0 != m1 and not any(isinstance(h, dict) and h.get("trade_date") == day and h.get("from") == m0 and h.get("to") == m1 for h in tail):
                errors.append(f"{episode}:market_history_missing")
            if t0 != t1 and not any(isinstance(h, dict) and h.get("trade_date") == day and h.get("from") == t0 and h.get("to") == t1 for h in tail):
                errors.append(f"{episode}:industry_history_missing")
            if l0 != l1 and not any(isinstance(h, dict) and h.get("trade_date") == day for h in tail):
                errors.append(f"{episode}:lifecycle_history_missing")
        facts = review.get("evidence", [])
        if not isinstance(facts, list):
            facts = []
            errors.append(f"{episode}:invalid_evidence")
        qualified = [e for e in facts if _valid_evidence(e, day)]
        if len(qualified) != len(facts):
            errors.append(f"{episode}:unverifiable_evidence")
        if changed and not any(e["trade_date"] > before for e in qualified):
            errors.append(f"{episode}:no_fresh_evidence")
        if (t0 != t1 and T_STATE_RANK[t1] < T_STATE_RANK[t0]) or (l1 == "已失效" and l0 != l1):
            if not any(e["direction"] == "COUNTER" and e["trade_date"] > before and
                       e["impact"] in {"STRUCTURAL", "CRITICAL"} and
                       e["dimension"] in {"COMMODITY_ANCHOR", "INDUSTRY_FUNDAMENTALS", "SUPPLY_DEMAND", "MAJOR_CATALYST"}
                       for e in qualified):
                errors.append(f"{episode}:industry_downgrade_without_primary_counter")
        if m0 != m1:
            direction = "COUNTER" if STATES[m1] < STATES[m0] else "SUPPORT"
            if not _market_state_evidence(qualified, direction, before, require_confirmation=m1 == "趋势确认"):
                errors.append(f"{episode}:market_change_without_independent_evidence")
    to_archive = [t for t in previous["trends"] if not tracking(t)]
    archived = (archive or {}).get("episodes", []) if isinstance(archive, dict) else []
    if to_archive:
        if not isinstance(archive, dict) or archive.get("result_kind") != "a_share_trend_v2_exit_archive" or archive.get("source_registry_blob_sha") != source_sha or archive.get("source_registry_trade_date") != before or archive.get("archive_trade_date") != day or archived != to_archive:
            errors.append("missing_or_inexact_exit_archive")
    elif archive is not None and (not isinstance(archived, list) or archived):
        errors.append("unexpected_archive_entries")
    if gate.get("archived_count") != len(to_archive):
        errors.append("archive_count_mismatch")
    for prior in to_archive:
        if prior.get("episode_id") in curr_by_id:
            errors.append(f"{prior.get('episode_id')}:nontracking_episode_carried")
    for item in proposed["trends"]:
        episode = item.get("episode_id")
        if item.get("market_state") not in MARKET or item.get("trend_state") not in T_STATES:
            errors.append(f"{episode}:invalid_state")
        if episode in prior_by_id:
            if episode not in continued:
                errors.append(f"{episode}:old_nontracking_episode_reused")
            continue
        name = item.get("trend_name")
        if (item.get("first_seen_trade_date") != day or
                episode != episode_key(name, day) or
                not isinstance(item.get("state_history"), list) or
                not any(isinstance(h, dict) and h.get("trade_date") == day for h in item["state_history"])):
            errors.append(f"{episode}:new_cycle_identity_or_date_invalid")
        if not isinstance(item.get("supporting_evidence"), list) or not item["supporting_evidence"]:
            errors.append(f"{episode}:new_cycle_without_evidence")
        if item.get("market_state") == "趋势确认":
            review = by_id.get(episode)
            # Newly confirmed names need separate first-confirmation support,
            # and a matching new-episode review (excluded from old HOLD coverage).
            new_reviews = gate.get("new_confirmation_reviews") or []
            review = next((r for r in new_reviews if r.get("episode_id") == episode), None)
            facts = review.get("evidence", []) if isinstance(review, dict) else []
            qualified = [e for e in facts if _valid_evidence(e, day)]
            if len(facts) != len(qualified) or not _market_state_evidence(qualified, "SUPPORT", before, True):
                errors.append(f"{episode}:new_confirmation_without_independent_evidence")
    return errors


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", required=True, choices=["cutover", "archive-exits"])
    p.add_argument("--previous", required=True)
    p.add_argument("--proposed")
    p.add_argument("--previous-blob-sha", required=True)
    p.add_argument("--registry-output")
    p.add_argument("--archive-output", required=True)
    a = p.parse_args()
    previous = _load(a.previous)
    if a.mode == "cutover":
        if not a.registry_output:
            p.error("--registry-output is required for cutover")
        _write(a.registry_output, cutover(previous, a.previous_blob_sha))
        # The frozen legacy archive is the EXACT full original JSON.
        Path(a.archive_output).parent.mkdir(parents=True, exist_ok=True)
        Path(a.archive_output).write_bytes(Path(a.previous).read_bytes())
    else:
        if not a.proposed:
            p.error("--proposed required for archive-exits")
        _write(a.archive_output, exit_archive(previous, _load(a.proposed), a.previous_blob_sha))


if __name__ == "__main__":
    main()
