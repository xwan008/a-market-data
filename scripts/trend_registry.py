#!/usr/bin/env python3
"""Canonical active trend continuity and cold exit validation.

Archived episodes are not included in daily discovery or continuity input.
"""
import argparse
import copy
import json
import re
from pathlib import Path

STATES = {"失效": 0, "高潮/衰退": 1, "观察": 2, "新异动": 2,
          "候选趋势": 3, "趋势确认": 4}
T_STATES = {"T0", "T1", "T2", "待核验"}
T_STATE_RANK = {"待核验": 0, "T0": 1, "T1": 2, "T2": 3}
DIMENSIONS = {"COMMODITY_ANCHOR", "INDUSTRY_FUNDAMENTALS", "MARKET_STRUCTURE",
              "MARKET_BREADTH", "RELATIVE_STRENGTH", "SUPPLY_DEMAND",
              "MAJOR_CATALYST"}
SOURCE = re.compile(r"^(https?://\S+|(?:data|research)/[\w./-]+)$")
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")



TRACK = {"趋势确认", "候选趋势"}
MARKET = {"趋势确认", "候选趋势", "观察", "新异动", "高潮/衰退", "失效"}
SHA = re.compile(r"^[0-9a-f]{40}$")

def _valid_evidence(e, after_day):
    """Verify provenance/shape, not the truth of external market claims."""
    if not isinstance(e, dict):
        return False
    day = e.get("trade_date")
    window = e.get("window_trading_days")
    return (
        e.get("dimension") in DIMENSIONS
        and e.get("direction") in {"SUPPORT", "COUNTER"}
        and e.get("impact") in {"NORMAL", "STRUCTURAL", "CRITICAL"}
        and isinstance(day, str) and DAY.fullmatch(day) is not None
        and day <= after_day
        and isinstance(e.get("source"), str) and SOURCE.fullmatch(e["source"]) is not None
        and isinstance(e.get("finding"), str) and len(e["finding"].strip()) >= 10
        and (window is None or (isinstance(window, int) and not isinstance(window, bool) and window > 0))
    )


def _market_state_evidence(evidence, direction, since, require_confirmation=False):
    """One evidence-quality rule, independent of elapsed trading-day count.

    Market structure must be material; breadth and relative strength provide
    independent corroboration. Industry news cannot substitute for A-share
    participation. Data verification and contradiction appraisal remain model
    research responsibilities, not promises of this metadata gate.
    """
    fresh = [e for e in evidence if e["direction"] == direction and e["trade_date"] > since]
    structural = any(e["dimension"] == "MARKET_STRUCTURE"
                     and e["impact"] in {"STRUCTURAL", "CRITICAL"} for e in fresh)
    breadth = any(e["dimension"] == "MARKET_BREADTH" for e in fresh)
    relative = any(e["dimension"] == "RELATIVE_STRENGTH" for e in fresh)
    return structural and breadth and relative if require_confirmation else structural and (breadth or relative)


def _optional_sector_audit_valid(sector_audit, day):
    """Optional audit quality check; no hard breadth or turnover threshold."""
    if not isinstance(sector_audit, dict) or sector_audit.get("trade_date") != day:
        return False
    sectors, count = sector_audit.get("sectors"), sector_audit.get("industry_count")
    if not isinstance(sectors, list) or not isinstance(count, int) or isinstance(count, bool) or count < 0:
        return False
    ids = [s.get("id") for s in sectors if isinstance(s, dict)]
    return (len(ids) == len(sectors) and all(isinstance(i, str) and i for i in ids)
            and len(set(ids)) == len(ids)
            and sum(i.startswith("industry:") for i in ids) == count)



def tracking(item):
    return item.get("market_state") in TRACK and item.get("lifecycle_status") != "已失效"


def episode_key(name, first_seen):
    return f"{name}#{first_seen}"



def exit_archive(previous, proposed, source_sha):
    """Freeze ALL previously non-tracked entries before they leave the live JSON."""
    if previous.get("schema_version") != 2 or proposed.get("schema_version") != 2:
        raise ValueError("CURRENT_REGISTRY_REQUIRED")
    if not isinstance(source_sha, str) or not SHA.fullmatch(source_sha):
        raise ValueError("REAL_SOURCE_BLOB_SHA_REQUIRED")
    return {
        "schema_version": 1,
        "result_kind": "a_share_trend_exit_archive",
        "source_registry_trade_date": previous["trade_date"],
        "archive_trade_date": proposed["trade_date"],
        "source_registry_blob_sha": source_sha,
        "episodes": [copy.deepcopy(t) for t in previous["trends"] if not tracking(t)],
    }



def validate(previous, proposed, source_sha, snapshot=None, sector_audit=None, archive=None):
    """Fail closed on unverified state changes, silent exit or stale evidence."""
    errors = []
    before, day = previous.get("trade_date"), proposed.get("trade_date")
    if previous.get("schema_version") != 2 or proposed.get("schema_version") != 2:
        errors.append("schema_version_mismatch")
    if previous.get("result_kind") != "a_share_trend_registry" or proposed.get("result_kind") != "a_share_trend_registry":
        errors.append("result_kind_mismatch")
    if previous.get("status") != "COMPLETE" or proposed.get("status") != "COMPLETE":
        errors.append("registry_not_complete")
    if not isinstance(before, str) or not DAY.fullmatch(before) or not isinstance(day, str) or not DAY.fullmatch(day):
        return errors + ["invalid_trade_dates"]
    if not isinstance(source_sha, str) or not SHA.fullmatch(source_sha):
        return errors + ["invalid_previous_blob_sha"]
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

    if not isinstance(before, str) or not isinstance(day, str) or day <= before or gate.get("mode") != "full_close":
        errors.append("invalid_close_mode")
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
        if not isinstance(archive, dict) or archive.get("result_kind") != "a_share_trend_exit_archive" or archive.get("source_registry_blob_sha") != source_sha or archive.get("source_registry_trade_date") != before or archive.get("archive_trade_date") != day or archived != to_archive:
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
            # Newly confirmed names need separate first-confirmation support,
            # and a matching new-episode review (excluded from old HOLD coverage).
            new_reviews = gate.get("new_confirmation_reviews") or []
            review = next((r for r in new_reviews if r.get("episode_id") == episode), None)
            facts = review.get("evidence", []) if isinstance(review, dict) else []
            qualified = [e for e in facts if _valid_evidence(e, day)]
            if len(facts) != len(qualified) or not _market_state_evidence(qualified, "SUPPORT", before, True):
                errors.append(f"{episode}:new_confirmation_without_independent_evidence")
    return errors


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--previous", required=True)
    p.add_argument("--proposed", required=True)
    p.add_argument("--previous-blob-sha", required=True)
    p.add_argument("--archive-output", required=True)
    a = p.parse_args()
    def load(path):
        return json.loads(Path(path).read_text(encoding="utf-8"))
    archive = exit_archive(load(a.previous), load(a.proposed), a.previous_blob_sha)
    dest = Path(a.archive_output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(archive, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "archived_count": len(archive["episodes"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
