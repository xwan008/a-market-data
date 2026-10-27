#!/usr/bin/env python3
"""Active trend continuity and evidence-backed exit validation."""
import re
from datetime import datetime, timezone, timedelta

STATES = {"失效": 0, "高潮/衰退": 1, "观察": 2, "新异动": 2,
          "候选趋势": 3, "趋势确认": 4}
T_STATES = {"T0", "T1", "T2", "待核验"}
T_STATE_RANK = {"待核验": 0, "T0": 1, "T1": 2, "T2": 3}
DIMENSIONS = {"COMMODITY_ANCHOR", "INDUSTRY_FUNDAMENTALS", "MARKET_STRUCTURE",
              "MARKET_BREADTH", "RELATIVE_STRENGTH", "SUPPLY_DEMAND",
              "MAJOR_CATALYST"}
SOURCE = re.compile(r"^(https?://\S+|(?:data|research)/[\w./-]+)$")
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")



TRACK = {"趋势确认", "候选趋势", "观察"}
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


def _market_state_evidence(evidence, direction, since, require_confirmation=False, commodity=False):
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
    if commodity:
        # The same primary instrument must govern promotion AND invalidation.
        # Equity breadth cannot stand in for a commodity-price counter signal.
        anchor = any(e["dimension"] == "COMMODITY_ANCHOR" and
                     e["impact"] in {"STRUCTURAL", "CRITICAL"} for e in fresh)
        corroboration = any(e["dimension"] in {"SUPPLY_DEMAND", "INDUSTRY_FUNDAMENTALS"}
                            for e in fresh)
        if direction == "COUNTER":
            return structural and anchor and (corroboration if require_confirmation else True)
        return structural and anchor and corroboration if require_confirmation else (
            structural and (anchor or corroboration))
    return structural and breadth and relative if require_confirmation else structural and (breadth or relative)


# Prospective research-decision audit. Checks provenance and internal consistency;
# it cannot verify real-world catalyst truth or profitability.
RESEARCH_GATE_FROM = "2026-10-27"
BEIJING = timezone(timedelta(hours=8))


def _research_audit_errors(item, day, prior=None):
    episode = item.get("episode_id")
    audit = item.get("confirmation_audit")
    errors = []
    if not isinstance(audit, dict) or audit.get("asof_trade_date") != day:
        return [f"{episode}:confirmation_audit_missing"]
    if audit.get("market_environment") not in {"NORMAL", "EVENT_LIQUIDITY_SHOCK",
                                                "RISK_OFF", "MIXED", "UNCERTAIN"}:
        errors.append(f"{episode}:environment_unclassified")
    environment_reason = audit.get("market_environment_reason")
    environment_source = audit.get("market_environment_source")
    if not isinstance(environment_reason, str) or len(environment_reason.strip()) < 12:
        errors.append(f"{episode}:environment_reason_missing")
    if not isinstance(environment_source, str) or SOURCE.fullmatch(environment_source) is None:
        errors.append(f"{episode}:environment_source_invalid")
    if audit.get("driver_type") not in {"INDUSTRIAL_GROWTH", "CONTENT_COMMERCIALIZATION",
                                      "COMMODITY", "DEFENSIVE", "OTHER"}:
        errors.append(f"{episode}:driver_unclassified")
    if (item.get("trend_basis") == "COMMODITY") != (audit.get("driver_type") == "COMMODITY"):
        errors.append(f"{episode}:driver_basis_mismatch")
    if audit.get("discovery_basis") not in {"ONE_DAY_SURGE", "CONTINUING_STRUCTURE",
                                           "SUSTAINED_FUNDAMENTAL", "COMMODITY_STRUCTURE"}:
        errors.append(f"{episode}:discovery_basis_missing")
    if (prior is None and audit.get("discovery_basis") == "ONE_DAY_SURGE"
            and item.get("market_state") != "观察"):
        errors.append(f"{episode}:one_day_surge_must_observe")
    if audit.get("catalyst_kind") not in {"EVENT", "SUSTAINED_DRIVER", "COMMODITY_SUPPLY",
                                         "UNVERIFIED"}:
        errors.append(f"{episode}:catalyst_kind_invalid")
    if not isinstance(audit.get("catalyst_fact"), str) or len(audit["catalyst_fact"].strip()) < 12:
        errors.append(f"{episode}:catalyst_fact_missing")
    if not isinstance(audit.get("strongest_counter"), str) or len(audit["strongest_counter"].strip()) < 12:
        errors.append(f"{episode}:counter_review_missing")
    if not isinstance(audit.get("decision_reason"), str) or len(audit["decision_reason"].strip()) < 12:
        errors.append(f"{episode}:confirmation_decision_reason_missing")
    if audit.get("decision_state") != item.get("market_state"):
        errors.append(f"{episode}:confirmation_decision_state_mismatch")
    src = audit.get("catalyst_source")
    if not isinstance(src, str) or SOURCE.fullmatch(src) is None:
        errors.append(f"{episode}:catalyst_source_invalid")
    # Exact publication / accessibility cutoff matters for Tesla and global oil.
    published = audit.get("catalyst_available_at")
    try:
        moment = datetime.fromisoformat(published)
        if moment.tzinfo is None or moment.utcoffset() is None or (
            moment.astimezone(BEIJING) > datetime.fromisoformat(day + "T18:30:00+08:00")):
            raise ValueError("future or naive")
    except (TypeError, ValueError, OverflowError):
        errors.append(f"{episode}:catalyst_not_available_at_close")
    core = audit.get("core_industry_codes")
    codes = item.get("industry_codes") or []
    if not isinstance(core, list) or not isinstance(codes, list) or (
            not all(isinstance(x, str) for x in core) or
            len(set(core)) != len(core) or any(x not in codes for x in core)):
        errors.append(f"{episode}:core_industry_identity_invalid")
    elif item.get("market_state") == "趋势确认" and item.get("trend_basis") != "COMMODITY" and not core:
        errors.append(f"{episode}:confirmed_core_missing")
    if item.get("market_state") in {"候选趋势", "趋势确认"}:
        if audit.get("catalyst_kind") == "UNVERIFIED":
            errors.append(f"{episode}:unverified_driver_cannot_progress")
        if audit.get("discovery_basis") == "ONE_DAY_SURGE":
            errors.append(f"{episode}:surge_alone_cannot_progress")
    if item.get("market_state") != "趋势确认":
        blocker = audit.get("specific_blocker")
        if not isinstance(blocker, str) or len(blocker.strip()) < 12:
            errors.append(f"{episode}:confirmation_blocker_missing")
    else:
        sufficient = audit.get("first_sufficient_evidence_trade_date")
        if not isinstance(sufficient, str) or not DAY.fullmatch(sufficient) or sufficient > day:
            errors.append(f"{episode}:first_sufficient_evidence_date_missing")
    return errors


# One-day-surges get a bounded research *decision*, never an automatic
# confirmation. The counter is made from actual completed registry-review
# sessions, not elapsed calendar days (weekends/holidays are excluded).
SURGE_DIMENSIONS = {"market_environment", "catalyst", "beneficiary_chain",
                    "funding_strength", "breadth", "relative_strength",
                    "price_structure", "counter_evidence"}
SURGE_STATUSES = {"SUPPORTED", "COUNTER", "INSUFFICIENT", "UNVERIFIED",
                  "ASSESSED", "NOT_APPLICABLE"}


def _surge_review_errors(item, previous, day):
    episode = item.get("episode_id")
    audit = item.get("confirmation_audit") or {}
    prior_review = previous.get("surge_followup") if isinstance(previous, dict) else None
    if prior_review is not None and not isinstance(prior_review, dict):
        return [f"{episode}:previous_surge_followup_invalid"]
    review = item.get("surge_followup")
    starts_now = (previous is None and
                  audit.get("discovery_basis") == "ONE_DAY_SURGE")
    if not starts_now and prior_review is None:
        # Pre-existing industry trends and non-surge discoveries are unaffected.
        if review is not None:
            return [f"{episode}:surge_followup_without_surge_origin"]
        return []
    if not isinstance(review, dict):
        return [f"{episode}:surge_followup_missing"]
    errors = []
    source_day = (day if starts_now else prior_review.get("trigger_trade_date"))
    if review.get("trigger_trade_date") != source_day:
        errors.append(f"{episode}:surge_trigger_date_changed")
    old_sessions = (prior_review.get("sessions") if prior_review else [])
    sessions = review.get("sessions")
    if not isinstance(sessions, list):
        return errors + [f"{episode}:surge_sessions_not_list"]
    if not isinstance(old_sessions, list):
        return errors + [f"{episode}:previous_surge_sessions_invalid"]
    if sessions[:len(old_sessions)] != old_sessions:
        errors.append(f"{episode}:surge_session_history_rewritten")
    if prior_review and prior_review.get("decision") in {"CONFIRMED", "NOT_CONFIRMED"}:
        # Initial three-session judgement is frozen. A later, independent
        # confirmation may still occur based on NEW evidence.
        if review != prior_review:
            errors.append(f"{episode}:surge_final_judgement_rewritten")
        return errors
    if len(sessions) != len(old_sessions) + 1:
        errors.append(f"{episode}:surge_review_not_updated_this_close")
    elif not isinstance(sessions[-1], dict) or sessions[-1].get("trade_date") != day:
        errors.append(f"{episode}:surge_review_trade_date_mismatch")
    if len(sessions) > 3:
        errors.append(f"{episode}:surge_review_overdue")
    for n, row in enumerate(sessions):
        if not isinstance(row, dict):
            errors.append(f"{episode}:surge_session_invalid")
            continue
        dt = row.get("trade_date")
        prior_dt = sessions[n-1].get("trade_date") if n and isinstance(sessions[n-1], dict) else None
        if (not isinstance(dt, str) or not DAY.fullmatch(dt) or dt > day or
                (n and (not isinstance(prior_dt, str) or dt <= prior_dt))):
            errors.append(f"{episode}:surge_session_date_invalid")
        dimensions = row.get("dimensions")
        if not isinstance(dimensions, dict) or set(dimensions) != SURGE_DIMENSIONS:
            errors.append(f"{episode}:surge_evidence_matrix_incomplete")
            continue
        for name, evidence in dimensions.items():
            if (not isinstance(evidence, dict) or
                evidence.get("status") not in SURGE_STATUSES or
                not isinstance(evidence.get("finding"), str) or
                len(evidence["finding"].strip()) < 12 or
                not isinstance(evidence.get("source"), str) or
                SOURCE.fullmatch(evidence["source"]) is None):
                errors.append(f"{episode}:{name}:surge_evidence_invalid")
        funding = dimensions.get("funding_strength")
        if isinstance(funding, dict):
            # Relative volume/turnover is a participation proxy, NOT proof of
            # net capital inflow or the identity of buyers.
            if (funding.get("measurement_basis") not in
                    {"PRICE_VOLUME_PROXY", "VERIFIED_NET_FLOW", "UNVERIFIED"} or
                    not isinstance(funding.get("observation_window"), str) or
                    len(funding["observation_window"].strip()) < 4 or
                    (funding.get("measurement_basis") == "UNVERIFIED" and
                     funding.get("status") == "SUPPORTED")):
                errors.append(f"{episode}:funding_strength_basis_invalid")
        breadth = dimensions.get("breadth")
        if isinstance(breadth, dict) and breadth.get("status") == "SUPPORTED":
            count = breadth.get("sample_size")
            rising = breadth.get("advancing_count")
            if (type(count) is not int or count <= 0 or
                    type(rising) is not int or rising < 0 or rising > count):
                errors.append(f"{episode}:breadth_sample_invalid")
    decision = review.get("decision")
    if decision not in {"PENDING", "CONFIRMED", "NOT_CONFIRMED"}:
        errors.append(f"{episode}:surge_decision_invalid")
    if len(sessions) == 1 and decision != "PENDING":
        errors.append(f"{episode}:surge_day_one_cannot_confirm")
    if len(sessions) >= 3 and decision == "PENDING":
        errors.append(f"{episode}:surge_third_close_decision_missing")
    if decision == "PENDING":
        if review.get("decision_trade_date") is not None:
            errors.append(f"{episode}:surge_pending_has_decision_date")
    else:
        if (not sessions or not isinstance(sessions[-1], dict) or
                review.get("decision_trade_date") != sessions[-1].get("trade_date")):
            errors.append(f"{episode}:surge_final_date_invalid")
        if decision == "CONFIRMED":
            if item.get("market_state") != "趋势确认":
                errors.append(f"{episode}:surge_confirmed_state_mismatch")
            # All real-world claims still require human/model evidence review.
            needed = {"catalyst", "price_structure"}
            if item.get("trend_basis") != "COMMODITY":
                needed |= {"beneficiary_chain", "funding_strength", "breadth",
                           "relative_strength"}
            latest = sessions[-1].get("dimensions") if sessions and isinstance(sessions[-1], dict) else {}
            if (audit.get("market_environment") == "EVENT_LIQUIDITY_SHOCK" and
                    (not isinstance(review.get("event_independent_evidence"), dict) or
                     review["event_independent_evidence"].get("status") != "SUPPORTED" or
                     not isinstance(review["event_independent_evidence"].get("finding"), str) or
                     len(review["event_independent_evidence"]["finding"].strip()) < 12 or
                     not isinstance(review["event_independent_evidence"].get("source"), str) or
                     SOURCE.fullmatch(review["event_independent_evidence"]["source"]) is None)):
                errors.append(f"{episode}:surge_event_without_independent_sector_evidence")
            for name in needed:
                if (not isinstance(latest, dict) or
                    not isinstance(latest.get(name), dict) or
                    latest[name].get("status") != "SUPPORTED"):
                    errors.append(f"{episode}:{name}:surge_confirmed_without_support")
        elif decision == "NOT_CONFIRMED" and item.get("market_state") == "趋势确认":
            errors.append(f"{episode}:surge_not_confirmed_state_mismatch")
    return errors


def _d123_stage_errors(item, previous, day):
    """Validate displayed D1/D2/D3 stage; never use it to confirm a market trend."""
    episode = item.get("episode_id", "unknown")
    stage = item.get("d123_stage")
    prior_stage = previous.get("d123_stage") if isinstance(previous, dict) else None
    if stage is None and prior_stage is None:
        return []
    errors = []
    allowed = {"D1", "D2", "D3", "POST_D3"}
    if stage not in allowed:
        return [f"{episode}:d123_stage_invalid"]
    trigger = item.get("d123_trigger_trade_date")
    if (not isinstance(trigger, str) or DAY.fullmatch(trigger) is None
            or trigger > day):
        errors.append(f"{episode}:d123_trigger_invalid")
    decision = item.get("d123_decision")
    if decision not in {"PENDING", "CONFIRMED", "NOT_CONFIRMED"}:
        errors.append(f"{episode}:d123_decision_invalid")
    if stage in {"D1", "D2"} and decision == "NOT_CONFIRMED":
        errors.append(f"{episode}:d123_early_negative_decision")
    if stage in {"D3", "POST_D3"} and decision == "PENDING":
        errors.append(f"{episode}:d123_final_decision_missing")
    if decision == "CONFIRMED" and item.get("market_state") != "趋势确认":
        errors.append(f"{episode}:d123_confirmation_state_mismatch")
    if stage == "D1" and trigger != day:
        errors.append(f"{episode}:d123_first_day_mismatch")
    if prior_stage is None:
        if stage != "D1":
            errors.append(f"{episode}:d123_missing_initial_stage")
    else:
        if trigger != previous.get("d123_trigger_trade_date"):
            errors.append(f"{episode}:d123_trigger_changed")
        expected = {"D1": "D2", "D2": "D3", "D3": "POST_D3",
                    "POST_D3": "POST_D3"}[prior_stage] if prior_stage in allowed else None
        if stage != expected:
            errors.append(f"{episode}:d123_progression_invalid")
        if prior_stage in {"D3", "POST_D3"} and decision != previous.get("d123_decision"):
            errors.append(f"{episode}:d123_final_decision_rewritten")
    return errors


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




def _same_day_revision_errors(previous, proposed, source_sha, snapshot=None, sector_audit=None):
    """Allow today's corrected publication, without replaying D1/D2 or erasing history.

    A revision is of today's *same* published episodes, not a new close or a
    second discovery run. Additions/exits need a new independent discovery
    checkpoint and are deliberately not covered by this correction path.
    """
    import copy
    errors = []
    day = previous.get("trade_date")
    if not isinstance(day, str) or DAY.fullmatch(day) is None:
        return ["same_day_invalid_trade_date"]
    if datetime.now(BEIJING).date().isoformat() != day:
        errors.append("same_day_revision_only_allowed_on_trade_date")
    if not isinstance(source_sha, str) or SHA.fullmatch(source_sha) is None:
        errors.append("invalid_previous_blob_sha")
    if (previous.get("schema_version") != 2 or proposed.get("schema_version") != 2 or
            previous.get("result_kind") != "a_share_trend_registry" or
            proposed.get("result_kind") != "a_share_trend_registry" or
            previous.get("status") != "COMPLETE" or proposed.get("status") != "COMPLETE"):
        errors.append("same_day_registry_contract_invalid")
    if snapshot is not None and (snapshot.get("trade_date") != day or
                                 snapshot.get("point_in_time_eligible") is not True or
                                 snapshot.get("auxiliary_only") is not True):
        errors.append("snapshot_invalid")
    if sector_audit is not None and not _optional_sector_audit_valid(sector_audit, day):
        errors.append("sector_audit_invalid")
    old_scan, new_scan = previous.get("scan_audit"), proposed.get("scan_audit")
    if not isinstance(old_scan, dict) or not isinstance(new_scan, dict):
        return errors + ["same_day_scan_audit_missing"]
    if old_scan.get("full_market_scan_completed") is not True:
        errors.append("full_market_scan_incomplete")
    if new_scan.get("full_market_scan_completed") is not True:
        errors.append("full_market_scan_incomplete")
    old_copy = copy.deepcopy(old_scan)
    new_copy = copy.deepcopy(new_scan)
    old_revisions = old_copy.pop("same_day_revisions", [])
    new_revisions = new_copy.pop("same_day_revisions", [])
    if new_copy != old_copy:
        errors.append("same_day_original_close_audit_rewritten")
    if (not isinstance(old_revisions, list) or not isinstance(new_revisions, list)
            or new_revisions[:-1] != old_revisions or len(new_revisions) != len(old_revisions) + 1
            or not isinstance(new_revisions[-1], dict)):
        return errors + ["same_day_revision_audit_missing_or_rewritten"]
    revision = new_revisions[-1]
    if revision.get("previous_registry_blob_sha") != source_sha:
        errors.append("same_day_revision_baseline_sha_mismatch")
    if revision.get("previous_generated_at") != previous.get("generated_at"):
        errors.append("same_day_revision_parent_time_mismatch")
    if not isinstance(revision.get("reason"), str) or len(revision["reason"].strip()) < 15:
        errors.append("same_day_revision_reason_missing")
    try:
        previous_time = datetime.fromisoformat(previous["generated_at"])
        revised_time = datetime.fromisoformat(proposed["generated_at"])
        reviewed_time = datetime.fromisoformat(revision["revised_at"])
        if (any(dt.tzinfo is None or dt.utcoffset() is None
                for dt in (previous_time, revised_time, reviewed_time))
                or reviewed_time.date() != datetime.fromisoformat(day + "T00:00:00+08:00").date()
                or reviewed_time.astimezone(BEIJING).date().isoformat() != day
                or revised_time.astimezone(BEIJING).date().isoformat() != day
                or reviewed_time <= previous_time or revised_time != reviewed_time
                or revised_time > datetime.now(BEIJING)):
            raise ValueError("time sequence")
    except (KeyError, TypeError, ValueError, OverflowError):
        errors.append("same_day_revision_time_invalid")
    prev_trends, new_trends = previous.get("trends"), proposed.get("trends")
    if not isinstance(prev_trends, list) or not isinstance(new_trends, list) or (
            not all(isinstance(t, dict) for t in prev_trends + new_trends)):
        return errors + ["same_day_trends_invalid"]
    prev_by_id = {t.get("episode_id"): t for t in prev_trends}
    new_by_id = {t.get("episode_id"): t for t in new_trends}
    if (len(prev_by_id) != len(prev_trends) or len(new_by_id) != len(new_trends)
            or set(prev_by_id) != set(new_by_id)
            or list(prev_by_id) != list(new_by_id)):
        return errors + ["same_day_episode_set_or_order_changed"]
    changes = revision.get("changes")
    if not isinstance(changes, list) or not changes or not all(isinstance(x, dict) for x in changes):
        return errors + ["same_day_changes_missing"]
    change_by_id = {x.get("episode_id"): x for x in changes}
    if len(change_by_id) != len(changes):
        errors.append("same_day_duplicate_changes")
    allowed_fields = {
        "market_state", "in_new_position_priority", "change_reason",
        "invalidation_condition", "last_verified_trade_date", "contrary_evidence",
        "supporting_evidence", "confirmation_audit", "industry_assessments",
        "state_history", "d123_stage", "d123_trigger_trade_date", "d123_decision",
    }
    changed_ids = set()
    for eid, old in prev_by_id.items():
        cur = new_by_id[eid]
        if old == cur:
            continue
        changed_ids.add(eid)
        if old.get("trend_name") != cur.get("trend_name") or (
                old.get("first_seen_trade_date") != cur.get("first_seen_trade_date")):
            errors.append(str(eid) + ":same_day_identity_changed")
        if any(old.get(key) != cur.get(key) for key in (set(old) | set(cur)) - allowed_fields):
            errors.append(str(eid) + ":same_day_protected_fields_changed")
        orig_history, now_history = old.get("state_history"), cur.get("state_history")
        if not isinstance(orig_history, list) or not isinstance(now_history, list) or (
                now_history[:len(orig_history)] != orig_history):
            errors.append(str(eid) + ":history_rewritten")
        elif (len(now_history) != len(orig_history) + 1
                or not isinstance(now_history[-1], dict)
                or now_history[-1].get("event") != "same_day_revision"
                or now_history[-1].get("trade_date") != day
                or now_history[-1].get("from") != old.get("market_state")
                or now_history[-1].get("to") != cur.get("market_state")):
            errors.append(str(eid) + ":same_day_history_event_missing")
        if (cur.get("market_state") not in TRACK or cur.get("lifecycle_status") == "已失效"
                or cur.get("market_state") == "观察" and cur.get("in_new_position_priority") is True
                or cur.get("market_state") != "趋势确认" and cur.get("in_new_position_priority") is True):
            errors.append(str(eid) + ":same_day_invalid_market_or_priority")
        if cur.get("trend_state") != old.get("trend_state"):
            errors.append(str(eid) + ":same_day_industry_stage_changed")
        audit = cur.get("confirmation_audit") or {}
        if audit.get("decision_state") != cur.get("market_state"):
            errors.append(str(eid) + ":same_day_research_decision_mismatch")
        errors.extend(_research_audit_errors(cur, day, old))
        if cur.get("d123_stage") != old.get("d123_stage") or cur.get("d123_trigger_trade_date") != old.get("d123_trigger_trade_date"):
            if old.get("d123_stage") is not None or cur.get("d123_stage") != "D1" or cur.get("d123_trigger_trade_date") != day:
                errors.append(str(eid) + ":same_day_d123_stage_invalid")
        errors.extend(_d123_stage_errors(cur, None if old.get("d123_stage") is None else old, day) if cur.get("d123_stage") != old.get("d123_stage") else [])
        assessments = cur.get("industry_assessments")
        if not isinstance(assessments, list) or (
                len(assessments) != len(cur.get("industry_codes") or [])):
            errors.append(str(eid) + ":same_day_sw3_assessments_invalid")
        else:
            for row in assessments:
                if not isinstance(row, dict) or row.get("evidence_trade_date") != day or (
                        row.get("market_state") not in TRACK):
                    errors.append(str(eid) + ":same_day_sw3_assessments_invalid")
                    break
        if cur.get("surge_followup") != old.get("surge_followup"):
            errors.append(str(eid) + ":same_day_surge_history_rewritten")
        info = change_by_id.get(eid)
        if not isinstance(info, dict) or info.get("from") != old.get("market_state") or (
                info.get("to") != cur.get("market_state")):
            errors.append(str(eid) + ":same_day_change_not_audited")
            continue
        evidence = info.get("evidence")
        if not isinstance(evidence, list) or len(evidence) < 2 or (
                not all(_valid_evidence(e, day) and e["trade_date"] == day
                        for e in evidence)):
            errors.append(str(eid) + ":same_day_revision_evidence_insufficient")
            continue
        if not isinstance(info.get("reason"), str) or len(info["reason"].strip()) < 15:
            errors.append(str(eid) + ":same_day_change_reason_missing")
        if cur.get("market_state") != old.get("market_state"):
            if STATES[cur["market_state"]] > STATES[old["market_state"]]:
                # An intraday correction to a stronger market state cannot
                # bypass the same independent structure/participation gate.
                if not _market_state_evidence(evidence, "SUPPORT", "0000-00-00",
                                              require_confirmation=cur["market_state"] == "趋势确认",
                                              commodity=cur.get("trend_basis") == "COMMODITY"):
                    errors.append(str(eid) + ":same_day_upgrade_without_market_evidence")
            elif old.get("market_state") == "趋势确认":
                if not _market_state_evidence(evidence, "COUNTER", "0000-00-00",
                                              commodity=old.get("trend_basis") == "COMMODITY"):
                    errors.append(str(eid) + ":same_day_confirmed_downgrade_without_market_counter")
            elif not (any(e["direction"] == "COUNTER" and e["dimension"] == "MARKET_STRUCTURE"
                          for e in evidence) and any(
                              e["direction"] == "COUNTER" and
                              e["dimension"] in {"INDUSTRY_FUNDAMENTALS", "SUPPLY_DEMAND",
                                                 "MARKET_BREADTH", "RELATIVE_STRENGTH"}
                              for e in evidence)):
                errors.append(str(eid) + ":same_day_candidate_downgrade_without_counter")
        if (cur.get("supporting_evidence") or [])[:len(old.get("supporting_evidence") or [])] != (
                old.get("supporting_evidence") or []):
            errors.append(str(eid) + ":same_day_original_evidence_rewritten")
    if set(change_by_id) != changed_ids:
        errors.append("same_day_audit_coverage_mismatch")
    if proposed.get("invalidated_history") != previous.get("invalidated_history") or (
            proposed.get("recheck_queue") != previous.get("recheck_queue")):
        errors.append("same_day_close_history_or_queue_rewritten")
    return errors


def validate(previous, proposed, source_sha, snapshot=None, sector_audit=None):
    """Fail closed on unsupported updates or unreviewed exits."""
    errors = []
    before, day = previous.get("trade_date"), proposed.get("trade_date")
    if isinstance(before, str) and before == day:
        return _same_day_revision_errors(previous, proposed, source_sha,
                                         snapshot=snapshot, sector_audit=sector_audit)
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
    scan = proposed.get("scan_audit") or {}
    if scan.get("full_market_scan_completed") is not True:
        errors.append("full_market_scan_incomplete")
    gate = scan.get("state_migration_gate") or {}
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
    if any(not tracking(item) for item in previous["trends"]):
        errors.append("previous_contains_nontracking_theme")
    reviews = gate.get("reviews", [])
    if not isinstance(reviews, list) or not all(isinstance(r, dict) for r in reviews):
        return errors + ["reviews_not_list"]
    by_id = {r.get("episode_id"): r for r in reviews}
    if len(by_id) != len(reviews):
        errors.append("duplicate_review_episode_id")
    exits = gate.get("exits", [])
    if not isinstance(exits, list) or not all(isinstance(r, dict) for r in exits):
        return errors + ["exits_not_list"]
    by_exit = {r.get("episode_id"): r for r in exits}
    if len(by_exit) != len(exits):
        errors.append("duplicate_exit_episode_id")
    prior_ids = set(prior_by_id)
    continued = prior_ids & set(curr_by_id)
    departing = prior_ids - set(curr_by_id)
    if set(by_id) != continued:
        errors.append("active_review_coverage_mismatch")
    if set(by_exit) != departing:
        errors.append("exit_review_coverage_mismatch")
    for episode in departing:
        prior = prior_by_id[episode]
        review = by_exit.get(episode)
        if review is None:
            errors.append(f"{episode}:active_silently_removed")
            continue
        if (review.get("decision") != "EXIT" or
                review.get("previous_market_state") != prior.get("market_state") or
                review.get("previous_trend_state") != prior.get("trend_state")):
            errors.append(f"{episode}:exit_review_state_mismatch")
        if review.get("proposed_market_state") not in MARKET - TRACK:
            errors.append(f"{episode}:exit_target_not_inactive")
        if not isinstance(review.get("reason"), str) or len(review["reason"].strip()) < 12:
            errors.append(f"{episode}:exit_reason_missing")
        evidence = review.get("evidence")
        if not isinstance(evidence, list):
            evidence = []
            errors.append(f"{episode}:exit_evidence_invalid")
        valid = [f for f in evidence if _valid_evidence(f, day)]
        if len(valid) != len(evidence):
            errors.append(f"{episode}:exit_evidence_invalid")
        if not _market_state_evidence(valid, "COUNTER", before,
                                      require_confirmation=prior.get("trend_basis") == "COMMODITY",
                                      commodity=prior.get("trend_basis") == "COMMODITY"):
            errors.append(f"{episode}:exit_without_independent_market_counter")
    for episode in continued:
        prior = prior_by_id[episode]
        now = curr_by_id[episode]
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
            if not _market_state_evidence(qualified, direction, before,
                                          require_confirmation=m1 == "趋势确认",
                                          commodity=(prior.get("trend_basis") == "COMMODITY"
                                                     if direction == "COUNTER" else
                                                     now.get("trend_basis") == "COMMODITY")):
                errors.append(f"{episode}:market_change_without_independent_evidence")
    # Every current observation/candidate/confirmed episode is reviewed at the
    # same Beijing cutoff. Existing 2026-10-26 registry is not rewritten.
    if day >= RESEARCH_GATE_FROM:
        for theme in proposed["trends"]:
            prior = prior_by_id.get(theme.get("episode_id"))
            errors.extend(_research_audit_errors(theme, day, prior))
            errors.extend(_surge_review_errors(theme, prior, day))
            errors.extend(_d123_stage_errors(theme, prior, day))
        for episode in continued:
            old, cur = prior_by_id[episode], curr_by_id[episode]
            old_assess = {x.get("industry_code"): x for x in
                          old.get("industry_assessments", []) if isinstance(x, dict)}
            current_assess = {x.get("industry_code"): x for x in
                              cur.get("industry_assessments", []) if isinstance(x, dict)}
            # An individually confirmed SW3 can be downgraded only on evidence
            # for THAT SW3, not on the weakness of an unrelated theme segment.
            for code, row in old_assess.items():
                if row.get("market_state") != "趋势确认":
                    continue
                now_ind = current_assess.get(code)
                if now_ind is None:
                    errors.append(f"{episode}:{code}:confirmed_core_disappeared")
                elif now_ind.get("market_state") != "趋势确认":
                    evidence = (by_id.get(episode) or {}).get("evidence", [])
                    if not isinstance(evidence, list) or not any(
                        e.get("direction") == "COUNTER" and
                        e.get("impact") in {"STRUCTURAL", "CRITICAL"} and
                        e.get("industry_code") == code and
                        e.get("trade_date") > before and
                        _valid_evidence(e, day)
                        for e in evidence if isinstance(e, dict)
                    ):
                        errors.append(f"{episode}:{code}:core_downgrade_without_own_counter")
    # Prospective SW3-level routing audit. No retroactive rewriting of 10/26.
    # This checks the presence, identity and provenance of each independent
    # industry decision; it does NOT automatically confirm stock-price trends.
    if day >= "2026-10-27":
        for theme in proposed["trends"]:
            episode = theme.get("episode_id")
            assessments = theme.get("industry_assessments")
            codes, names = theme.get("industry_codes"), theme.get("industry_names")
            if theme.get("market_state") == "观察" and not assessments:
                # First-day discovery can be researched without claiming that
                # tentative sector relationships are already verified.
                if theme.get("in_new_position_priority") is True:
                    errors.append(f"{episode}:observation_in_priority")
                continue
            if not isinstance(assessments, list) or not isinstance(codes, list) or not isinstance(names, list):
                errors.append(f"{episode}:sw3_assessments_missing")
                continue
            pairs = [(x.get("industry_code"), x.get("industry_name"))
                     for x in assessments if isinstance(x, dict)]
            if (len(pairs) != len(assessments) or len(pairs) != len(codes) or
                len(set(pairs)) != len(pairs) or
                set(pairs) != set(zip(codes, names))):
                errors.append(f"{episode}:sw3_route_or_identity_mismatch")
            confirmed = 0
            for row in assessments:
                if not isinstance(row, dict):
                    continue
                code = row.get("industry_code")
                if (row.get("benefit_level") not in {"CORE", "DIRECT", "RELATED", "UNVERIFIED"} or
                    row.get("market_state") not in TRACK or
                    row.get("evidence_trade_date") != day or
                    not isinstance(row.get("benefit_reason"), str) or
                    len(row["benefit_reason"].strip()) < 12 or
                    not isinstance(row.get("market_reason"), str) or
                    len(row["market_reason"].strip()) < 12):
                    errors.append(f"{episode}:{code}:sw3_independent_evidence_missing")
                if row.get("market_state") == "趋势确认":
                    if row.get("benefit_level") not in {"CORE", "DIRECT"}:
                        errors.append(f"{episode}:{code}:confirmed_without_direct_benefit")
                    else:
                        confirmed += 1
            if (theme.get("market_state") == "趋势确认" and confirmed < 1 and
                theme.get("trend_basis") != "COMMODITY"):
                errors.append(f"{episode}:confirmed_without_confirmed_sw3")

    for item in proposed["trends"]:
        episode = item.get("episode_id")
        if item.get("market_state") not in TRACK or item.get("lifecycle_status") == "已失效":
            errors.append(f"{episode}:nontracking_persisted")
        if item.get("market_state") == "观察" and item.get("in_new_position_priority") is True:
            errors.append(f"{episode}:observation_in_priority")
        if day >= RESEARCH_GATE_FROM and (item.get("in_new_position_priority") is True
                                          and item.get("market_state") != "趋势确认"):
            errors.append(f"{episode}:only_confirmed_priority")
        if item.get("trend_basis") not in (None, "A_SHARE", "COMMODITY"):
            errors.append(f"{episode}:invalid_trend_basis")
        if item.get("trend_basis") == "COMMODITY":
            anchor = item.get("commodity_anchor")
            if (not isinstance(anchor, dict) or
                not isinstance(anchor.get("instrument"), str) or
                not isinstance(anchor.get("price_basis"), str) or
                not isinstance(anchor.get("trade_date"), str) or
                not DAY.fullmatch(anchor["trade_date"]) or
                anchor["trade_date"] > day or
                not isinstance(anchor.get("source"), str) or
                not SOURCE.fullmatch(anchor["source"]) or
                not isinstance(anchor.get("trend_reason"), str) or
                len(anchor["trend_reason"].strip()) < 12):
                errors.append(f"{episode}:commodity_anchor_missing")
        if item.get("trend_state") not in T_STATES:
            errors.append(f"{episode}:invalid_state")
        if episode in prior_by_id:
            continue
        if item.get("trend_name") in {t.get("trend_name") for t in previous["trends"]}:
            errors.append(f"{episode}:active_cycle_restarted")
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
            if len(facts) != len(qualified) or not _market_state_evidence(
                    qualified, "SUPPORT", before, True, commodity=item.get("trend_basis") == "COMMODITY"):
                errors.append(f"{episode}:new_confirmation_without_independent_evidence")
    return errors
