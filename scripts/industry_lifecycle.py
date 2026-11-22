"""Independent SW3 D1-D3 lifecycle validation.

The lifecycle belongs to the independently assessed SW3 industry, not to the
broader theme that happens to contain the industry-benefit relationship.
"""
from __future__ import annotations

import re

DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SHA = re.compile(r"^[0-9a-f]{40}$")
TRACK = {"趋势确认", "候选趋势", "观察"}
DISCOVERY_BASES = {
    "ONE_DAY_SURGE", "CONTINUING_STRUCTURE",
    "SUSTAINED_FUNDAMENTAL", "COMMODITY_STRUCTURE",
}
DIMENSIONS = {
    "MARKET_STRUCTURE", "MARKET_BREADTH", "RELATIVE_STRENGTH",
    "INDUSTRY_FUNDAMENTALS", "SUPPLY_DEMAND", "MAJOR_CATALYST",
    "COMMODITY_ANCHOR",
}
SOURCE = re.compile(r"^(https?://\S+|(?:data|research|validation)/[\w./-]+)$")


def _valid_day(value):
    return isinstance(value, str) and DAY.fullmatch(value) is not None


def _valid_evidence(value, trade_date):
    return (
        isinstance(value, dict)
        and value.get("trade_date") == trade_date
        and value.get("direction") == "SUPPORT"
        and value.get("dimension") in DIMENSIONS
        and value.get("impact") in {"NORMAL", "STRUCTURAL", "CRITICAL"}
        and isinstance(value.get("source"), str)
        and SOURCE.fullmatch(value["source"]) is not None
        and isinstance(value.get("finding"), str)
        and len(value["finding"].strip()) >= 12
    )


def _history_errors(episode, code, day, *, require_current=True):
    errors = []
    history = episode.get("state_history")
    prefix = f"{code}:{episode.get('episode_id', 'unknown')}"
    if not isinstance(history, list) or not history:
        return [f"{prefix}:industry_history_missing"], [], {}
    sessions = []
    state_by_date = {}
    previous_state = None
    previous_date = None
    for index, event in enumerate(history):
        if (
            not isinstance(event, dict)
            or not _valid_day(event.get("trade_date"))
            or event.get("trade_date") > day
            or event.get("to") not in TRACK
        ):
            errors.append(f"{prefix}:industry_history_invalid")
            continue
        date = event["trade_date"]
        if index == 0:
            if event.get("from") is not None:
                errors.append(f"{prefix}:industry_history_initial_from_invalid")
            if date != episode.get("trigger_trade_date"):
                errors.append(f"{prefix}:industry_history_trigger_mismatch")
        else:
            if event.get("from") != previous_state:
                errors.append(f"{prefix}:industry_history_chain_broken")
            if previous_date is not None and date < previous_date:
                errors.append(f"{prefix}:industry_history_date_order_invalid")
            if date == previous_date and event.get("event") != "same_day_revision":
                errors.append(f"{prefix}:industry_history_duplicate_date")
        if date not in sessions:
            sessions.append(date)
        previous_state = event.get("to")
        previous_date = date
        state_by_date[date] = event.get("to")
    if require_current and history and isinstance(history[-1], dict):
        if history[-1].get("trade_date") != day:
            errors.append(f"{prefix}:industry_history_not_current")
    return errors, sessions, state_by_date


def _episode_errors(episode, code, day, *, require_backfill=False, require_current=True):
    errors = []
    if not isinstance(episode, dict):
        return [f"{code}:industry_episode_invalid"]
    trigger = episode.get("trigger_trade_date")
    episode_id = episode.get("episode_id")
    prefix = f"{code}:{episode_id or 'unknown'}"
    if not _valid_day(trigger) or trigger > day:
        errors.append(f"{prefix}:industry_trigger_date_invalid")
    if episode_id != f"{code}#{trigger}":
        errors.append(f"{prefix}:industry_episode_identity_invalid")
    if episode.get("initial_discovery_basis") not in DISCOVERY_BASES:
        errors.append(f"{prefix}:industry_discovery_basis_invalid")
    if not _valid_evidence(episode.get("trigger_evidence"), trigger):
        errors.append(f"{prefix}:industry_trigger_evidence_invalid")

    history_errors, sessions, state_by_date = _history_errors(
        episode, code, day, require_current=require_current
    )
    errors.extend(history_errors)
    stage = episode.get("d123_stage")
    decision = episode.get("d123_decision")
    decision_date = episode.get("d123_decision_trade_date")
    if stage not in {"D1", "D2", "D3"}:
        errors.append(f"{prefix}:industry_d123_stage_invalid")
    if decision not in {"PENDING", "CONFIRMED", "NOT_CONFIRMED"}:
        errors.append(f"{prefix}:industry_d123_decision_invalid")
    if decision == "PENDING":
        if decision_date is not None:
            errors.append(f"{prefix}:industry_pending_has_decision_date")
        if stage == "D3":
            errors.append(f"{prefix}:industry_d3_pending_invalid")
        expected_sessions = {"D1": 1, "D2": 2}.get(stage)
        if expected_sessions is not None and len(sessions) != expected_sessions:
            errors.append(f"{prefix}:industry_pending_stage_session_mismatch")
    else:
        if not _valid_day(decision_date) or decision_date not in sessions:
            errors.append(f"{prefix}:industry_decision_date_invalid")
        required_index = {"D1": 0, "D2": 1, "D3": 2}.get(stage)
        if required_index is not None and (
            len(sessions) <= required_index or sessions[required_index] != decision_date
        ):
            errors.append(f"{prefix}:industry_decision_stage_date_mismatch")
        if stage in {"D1", "D2"} and decision != "CONFIRMED":
            errors.append(f"{prefix}:industry_early_negative_verdict_invalid")
        if stage == "D1" and (
            episode.get("initial_discovery_basis") == "ONE_DAY_SURGE"
            or state_by_date.get(decision_date) != "趋势确认"
        ):
            errors.append(f"{prefix}:industry_d1_confirmation_unsubstantiated")
        if stage == "D2" and state_by_date.get(decision_date) != "趋势确认":
            errors.append(f"{prefix}:industry_d2_confirmation_unsubstantiated")
        if stage == "D3":
            confirmed_on_decision = state_by_date.get(decision_date) == "趋势确认"
            if (decision == "CONFIRMED") != confirmed_on_decision:
                errors.append(f"{prefix}:industry_d3_verdict_state_mismatch")
        if stage == "D3" and len(sessions) < 3:
            errors.append(f"{prefix}:industry_d3_sessions_insufficient")
        # Forward-only D1/D2/D3 confirmation must be supported by independent
        # CURRENT SW3 structure + breadth + relative-strength evidence.
        # Imported historical closes are checked against archived provenance
        # rather than retroactively fabricated session-level evidence.
        if decision == "CONFIRMED" and episode.get("backfill_audit") is None:
            facts = episode.get("confirmation_evidence")
            supported = {
                x.get("dimension") for x in facts
                if isinstance(x, dict) and _valid_evidence(x, decision_date)
                and x.get("industry_code") == code
                and (x.get("dimension") != "MARKET_STRUCTURE" or x.get("impact") in {"STRUCTURAL", "CRITICAL"})
            } if isinstance(facts, list) else set()
            if not {"MARKET_STRUCTURE", "MARKET_BREADTH", "RELATIVE_STRENGTH"}.issubset(supported):
                errors.append(f"{prefix}:industry_confirmation_evidence_incomplete")


    backfill = episode.get("backfill_audit")
    if require_backfill or (trigger and trigger < day and backfill is not None):
        if not isinstance(backfill, dict):
            errors.append(f"{prefix}:industry_backfill_audit_missing")
        else:
            paths = backfill.get("source_paths")
            shas = backfill.get("source_blob_shas")
            if (
                not _valid_day(backfill.get("asof_trade_date"))
                or backfill.get("asof_trade_date") > day
                or (require_backfill and backfill.get("asof_trade_date") != day)
                or backfill.get("basis") != "ARCHIVED_FORMAL_SW3_ASSESSMENTS"
                or backfill.get("first_formal_trade_date") != trigger
                or not isinstance(paths, list) or not paths
                or not isinstance(shas, list) or len(shas) != len(paths)
                or not all(
                    isinstance(path, str)
                    and re.fullmatch(r"validation/archive/\d{4}-\d{2}-\d{2}/trend_registry\.json", path)
                    for path in paths
                )
                or not all(isinstance(sha, str) and SHA.fullmatch(sha) for sha in shas)
                or not isinstance(backfill.get("review_gap"), str)
                or len(backfill["review_gap"].strip()) < 12
            ):
                errors.append(f"{prefix}:industry_backfill_audit_invalid")
            if decision != "PENDING":
                decision_sha = backfill.get("decision_registry_blob_sha")
                decision_is_historical = (
                    _valid_day(decision_date)
                    and _valid_day(backfill.get("asof_trade_date"))
                    and decision_date < backfill["asof_trade_date"]
                )
                if (
                    backfill.get("decision_market_state") != state_by_date.get(decision_date)
                    or (decision == "CONFIRMED") != (
                        backfill.get("decision_market_state") == "趋势确认"
                    )
                    or (decision_is_historical and (
                        not isinstance(decision_sha, str)
                        or SHA.fullmatch(decision_sha) is None
                        or decision_sha not in (shas or [])
                    ))
                ):
                    errors.append(f"{prefix}:industry_backfill_decision_provenance_invalid")
    elif trigger == day:
        if backfill is not None:
            errors.append(f"{prefix}:new_industry_episode_must_not_backfill")
        if len(sessions) != 1 or sessions[0] != day:
            errors.append(f"{prefix}:new_industry_episode_history_invalid")
    return errors


def validate_industry_lifecycle(current, previous, day, *, same_day=False):
    """Validate an assessment's independent lifecycle against its prior record."""
    code = current.get("industry_code", "unknown")
    errors = []
    life = current.get("industry_lifecycle")
    if not isinstance(life, dict) or not isinstance(life.get("episodes"), list) or not life["episodes"]:
        return [f"{code}:industry_lifecycle_missing"]
    episodes = life["episodes"]
    if not all(isinstance(x, dict) for x in episodes):
        return [f"{code}:industry_episodes_invalid"]

    trigger_dates = [x.get("trigger_trade_date") for x in episodes]
    if (
        any(not _valid_day(x) or x > day for x in trigger_dates)
        or trigger_dates != sorted(trigger_dates)
        or len(set(trigger_dates)) != len(trigger_dates)
    ):
        errors.append(f"{code}:industry_episode_order_invalid")
    if any(x.get("d123_decision") == "PENDING" for x in episodes[:-1]):
        errors.append(f"{code}:industry_nonterminal_episode_pending")
    for index, episode in enumerate(episodes):
        errors.extend(_episode_errors(
            episode, code, day,
            require_backfill=(previous is not None and
                              not (previous.get("industry_lifecycle") or {}).get("episodes")),
            require_current=(index == len(episodes) - 1)
        ))

    latest = episodes[-1]
    history = latest.get("state_history") or []
    if not history or history[-1].get("to") != current.get("market_state"):
        errors.append(f"{code}:industry_current_state_history_mismatch")
    if current.get("market_state") == "趋势确认" and latest.get("d123_decision") != "CONFIRMED":
        errors.append(f"{code}:industry_confirmed_state_without_confirmed_lifecycle")
    if current.get("benefit_level") not in {"CORE", "DIRECT"} and current.get("market_state") == "趋势确认":
        errors.append(f"{code}:industry_confirmed_without_direct_benefit")

    old_life = (previous or {}).get("industry_lifecycle") or {}
    old_episodes = old_life.get("episodes")
    if not isinstance(old_episodes, list) or not old_episodes:
        if previous is None:
            if (
                len(episodes) != 1
                or latest.get("trigger_trade_date") != day
                or latest.get("d123_stage") != "D1"
            ):
                errors.append(f"{code}:new_industry_must_start_d1")
        else:
            # One-time migration from historical per-theme assessments. The
            # archive audit is the only accepted basis for reconstructing D1-D3.
            if any(
                not isinstance(x.get("backfill_audit"), dict)
                for x in episodes
            ):
                errors.append(f"{code}:industry_lifecycle_migration_audit_missing")
        return errors

    if same_day:
        if len(episodes) != len(old_episodes):
            errors.append(f"{code}:same_day_industry_episode_count_changed")
            return errors
        if episodes[:-1] != old_episodes[:-1]:
            errors.append(f"{code}:same_day_industry_episode_history_rewritten")
        old, new = old_episodes[-1], episodes[-1]
        immutable = (
            "episode_id", "trigger_trade_date", "initial_discovery_basis",
            "trigger_evidence", "backfill_audit",
        )
        if any(old.get(key) != new.get(key) for key in immutable):
            errors.append(f"{code}:same_day_industry_episode_identity_changed")
        if any(old.get(key) != new.get(key) for key in (
            "d123_stage", "d123_decision", "d123_decision_trade_date"
        )):
            errors.append(f"{code}:same_day_industry_d123_changed")
        old_history, new_history = old.get("state_history"), new.get("state_history")
        if not isinstance(old_history, list) or not isinstance(new_history, list) or (
            new_history[:len(old_history)] != old_history
        ):
            errors.append(f"{code}:same_day_industry_history_rewritten")
        elif current.get("market_state") == previous.get("market_state"):
            if new_history != old_history:
                errors.append(f"{code}:same_day_industry_unnecessary_history_event")
        elif (
            len(new_history) != len(old_history) + 1
            or new_history[-1].get("trade_date") != day
            or new_history[-1].get("event") != "same_day_revision"
            or new_history[-1].get("from") != previous.get("market_state")
            or new_history[-1].get("to") != current.get("market_state")
        ):
            errors.append(f"{code}:same_day_industry_revision_event_missing")
        return errors

    if len(episodes) not in {len(old_episodes), len(old_episodes) + 1}:
        errors.append(f"{code}:industry_episode_count_changed")
        return errors
    if episodes[:len(old_episodes) - 1] != old_episodes[:len(old_episodes) - 1]:
        errors.append(f"{code}:industry_closed_episode_rewritten")
    old_last = old_episodes[-1]
    if len(episodes) == len(old_episodes) + 1:
        if old_last.get("d123_decision") == "PENDING":
            errors.append(f"{code}:industry_new_episode_before_prior_verdict")
        if episodes[:len(old_episodes)] != old_episodes:
            errors.append(f"{code}:industry_prior_episode_rewritten")
        new = episodes[-1]
        if (
            new.get("trigger_trade_date") != day
            or new.get("d123_stage") != "D1"
            or len(new.get("state_history") or []) != 1
            or new.get("d123_decision") not in {"PENDING", "CONFIRMED"}
        ):
            errors.append(f"{code}:industry_new_episode_invalid")
        return errors

    new_last = episodes[-1]
    immutable = (
        "episode_id", "trigger_trade_date", "initial_discovery_basis",
        "trigger_evidence", "backfill_audit",
    )
    if any(old_last.get(key) != new_last.get(key) for key in immutable):
        errors.append(f"{code}:industry_episode_identity_rewritten")
    old_history, new_history = old_last.get("state_history"), new_last.get("state_history")
    if not isinstance(old_history, list) or not isinstance(new_history, list) or (
        new_history[:len(old_history)] != old_history
    ):
        errors.append(f"{code}:industry_history_rewritten")
    elif (
        len(new_history) != len(old_history) + 1
        or new_history[-1].get("trade_date") != day
        or new_history[-1].get("from") != previous.get("market_state")
        or new_history[-1].get("to") != current.get("market_state")
    ):
        errors.append(f"{code}:industry_daily_history_event_missing")

    old_decision = old_last.get("d123_decision")
    if old_decision in {"CONFIRMED", "NOT_CONFIRMED"}:
        for key in ("d123_stage", "d123_decision", "d123_decision_trade_date"):
            if old_last.get(key) != new_last.get(key):
                errors.append(f"{code}:industry_final_d123_rewritten")
    else:
        expected_stage = {"D1": "D2", "D2": "D3"}.get(old_last.get("d123_stage"))
        if new_last.get("d123_stage") != expected_stage:
            errors.append(f"{code}:industry_d123_progression_invalid")
        if new_last.get("d123_decision") in {"CONFIRMED", "NOT_CONFIRMED"} and (
            new_last.get("d123_decision_trade_date") != day
        ):
            errors.append(f"{code}:industry_new_verdict_date_invalid")
    return errors
