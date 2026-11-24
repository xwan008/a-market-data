"""Historical replay only: the Nov 23 one-off cutover and earlier forward baseline.

The only permissible same-day change is recording each *already published*
industry market state plus its parent-theme D1-D3 provenance. It cannot revise
prices, theme/industry state, discovery, ranking, or stock handoff membership.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

DAY = "2026-11-23"
ORIGINAL_REGISTRY_BLOB_SHA = "9ff8d1afb4281b378b92d5d1f4cc8b1aaec423fb"
ORIGINAL_HANDOFF_BLOB_SHA = "b11ce8635d27ef3d20b604316767d6374c27ea08"
CONTRACT = "SW3_V1"
BEIJING = timezone(timedelta(hours=8))
STATES = {"趋势确认", "候选趋势", "观察"}
PHASE = {"D1", "D2", "D3"}

OLD_NOTE = "SW3_NOT_ACTIVATED：缺少完整历史归档链，不伪造行业D1-D3。"
NEW_NOTE = ("SW3_V1：依据本日已发布正式行业状态完成同日切换；"
            "三级行业继承主题D阶段上下文，未伪造独立历史D1-D3。")


def phase_snapshot(theme):
    return {
        "source_theme_episode_id": theme.get("episode_id"),
        "d123_stage": theme.get("d123_stage"),
        "d123_decision": theme.get("d123_decision"),
        "d123_trigger_trade_date": theme.get("d123_trigger_trade_date"),
        "d123_decision_trade_date": theme.get("d123_decision_trade_date"),
    }


def note_after_cutover(note):
    if not isinstance(note, str) or note.count(OLD_NOTE) != 1:
        raise ValueError("legacy SW3 note required exactly once")
    return note.replace(OLD_NOTE, NEW_NOTE)


def build(previous, old_handoff, source_sha, handoff_sha, revised_at):
    """Produce an exact same-session revision; never generate a market judgement."""
    result, handoff = deepcopy(previous), deepcopy(old_handoff)
    if previous.get("trade_date") != DAY or old_handoff.get("trade_date") != DAY:
        raise ValueError("only Nov 23 formal close can be switched")
    if (source_sha != ORIGINAL_REGISTRY_BLOB_SHA
            or handoff_sha != ORIGINAL_HANDOFF_BLOB_SHA):
        raise ValueError("cutover must use the exact frozen Nov 23 formal pair")
    if previous.get("scan_audit", {}).get("sw3_lifecycle_contract") is not None:
        raise ValueError("already opted in")
    result["generated_at"] = revised_at
    handoff["generated_at"] = revised_at
    scan = result["scan_audit"]
    scan["notes"] = note_after_cutover(scan["notes"])
    scan["sw3_lifecycle_contract"] = CONTRACT
    scan["sw3_same_day_cutover"] = {
        "mode": "ASOF_2026_11_23",
        "source_trade_date": DAY,
        "source_registry_blob_sha": source_sha,
        "source_handoff_blob_sha": handoff_sha,
        "revised_at": revised_at,
        "industry_count": sum(len(t.get("industry_assessments", []))
                              for t in previous["trends"]),
        "inheritance_policy": "INDUSTRY_MARKET_STATE_PLUS_THEME_PHASE_CONTEXT",
    }
    scan.setdefault("same_day_revisions", []).append({
        "previous_registry_blob_sha": source_sha,
        "previous_generated_at": previous["generated_at"],
        "revised_at": revised_at,
        "reason": ("仅将11月23日已发布的三级行业状态和原主题D阶段上下文"
                   "写入新生命周期，所有市场结论、优先排名和候选名单不变"),
        "changes": [
            {"episode_id": t["episode_id"],
             "from": t["market_state"], "to": t["market_state"],
             "reason": "同日记录原有行业状态与主题D阶段出处，不改变已发布的市场判断"}
            for t in previous["trends"]
        ],
    })
    for theme in result["trends"]:
        for row in theme.get("industry_assessments", []):
            if "industry_lifecycle" in row:
                raise ValueError("cannot overwrite existing independent industry history")
            state = row["market_state"]
            base = {
                "basis": "FORMAL_ASOF_SW3_CUTOVER",
                "asof_trade_date": DAY,
                "source_registry_blob_sha": source_sha,
                "industry_code": row["industry_code"],
                "initial_market_state": state,
                "state_history": [],
                "phase_origin": "LEGACY_THEME_D123",
                "legacy_theme_d123": phase_snapshot(theme),
                "d123_stage": theme["d123_stage"],
                "d123_decision": ("INHERITED_CONFIRMED" if state == "趋势确认"
                                   else "INHERITED_UNCONFIRMED"),
                "d123_decision_trade_date": None,
            }
            row["industry_lifecycle"] = {"episodes": [], "cutover_baseline": base}
        if theme["trend_name"] == "白色家电":
            theme["priority_exclusion_reason"] = (
                "空调三级行业沿用已发布确认状态，但今日原正式前三优先仍为"
                "高端PCB、电子化学品和国有大行；本次仅切换合同，不追加优先名额或重排")
    for signal in handoff["signals"]:
        theme = next(t for t in result["trends"]
                     if t["trend_name"] == signal["trend_name"])
        from scripts.industry_lifecycle import (
            cutover_route_lifecycle, industry_route_confirmed
        )
        allowed = [r for r in theme["industry_assessments"]
                   if industry_route_confirmed(r)]
        if [r["industry_code"] for r in allowed] != signal["industry_codes"]:
            raise ValueError("cutover cannot change the existing formal route")
        signal["market_state"] = "趋势确认"
        signal["theme_market_state"] = theme["market_state"]
        signal["industry_display_names"] = [
            theme["trend_name"] + " - " + r["industry_name"] for r in allowed
        ]
        signal["industry_lifecycles"] = [
            cutover_route_lifecycle(r) for r in allowed
        ]
    return result, handoff


def validate(previous, proposed, source_sha):
    """Replay the exact historical same-day snapshot-only cutover; not a live gate."""
    from scripts.industry_lifecycle import validate_industry_lifecycle
    import re
    errors = []
    if previous.get("trade_date") != DAY or proposed.get("trade_date") != DAY:
        return ["sw3_cutover_wrong_date"]
    if (previous.get("schema_version") != 2 or proposed.get("schema_version") != 2
            or previous.get("status") != "COMPLETE"
            or proposed.get("status") != "COMPLETE"):
        errors.append("sw3_cutover_registry_contract_invalid")
    if (previous.get("scan_audit") or {}).get("sw3_lifecycle_contract") is not None:
        errors.append("sw3_cutover_previous_already_enabled")
    if (proposed.get("scan_audit") or {}).get("sw3_lifecycle_contract") != CONTRACT:
        errors.append("sw3_cutover_missing_opt_in")
    if source_sha != ORIGINAL_REGISTRY_BLOB_SHA:
        errors.append("sw3_cutover_unapproved_original_registry_sha")
    old_scan = previous.get("scan_audit") or {}
    new_scan = proposed.get("scan_audit") or {}
    audit = new_scan.get("sw3_same_day_cutover") or {}
    revision = (new_scan.get("same_day_revisions") or [None])[-1]
    if (audit.get("mode") != "ASOF_2026_11_23"
            or audit.get("source_trade_date") != DAY
            or audit.get("source_registry_blob_sha") != source_sha
            or audit.get("source_handoff_blob_sha") != ORIGINAL_HANDOFF_BLOB_SHA
            or audit.get("inheritance_policy") != "INDUSTRY_MARKET_STATE_PLUS_THEME_PHASE_CONTEXT"):
        errors.append("sw3_cutover_provenance_invalid")
    if audit.get("industry_count") != sum(
            len(t.get("industry_assessments", []))
            for t in previous.get("trends", [])
            if isinstance(t, dict)):
        errors.append("sw3_cutover_count_invalid")
    left, right = deepcopy(old_scan), deepcopy(new_scan)
    for key in ("notes", "same_day_revisions", "sw3_lifecycle_contract",
                "sw3_same_day_cutover"):
        left.pop(key, None)
        right.pop(key, None)
    if left != right:
        errors.append("sw3_cutover_frozen_scan_rewritten")
    try:
        if new_scan.get("notes") != note_after_cutover(old_scan["notes"]):
            errors.append("sw3_cutover_note_mismatch")
    except (ValueError, KeyError):
        errors.append("sw3_cutover_note_mismatch")
    old_revisions = old_scan.get("same_day_revisions", [])
    new_revisions = new_scan.get("same_day_revisions", [])
    if (not isinstance(old_revisions, list) or not isinstance(new_revisions, list)
            or len(new_revisions) != len(old_revisions) + 1
            or new_revisions[:-1] != old_revisions
            or not isinstance(revision, dict)):
        errors.append("sw3_cutover_revision_chain_invalid")
        revision = {}
    if (revision.get("previous_registry_blob_sha") != source_sha
            or revision.get("previous_generated_at") != previous.get("generated_at")
            or revision.get("revised_at") != proposed.get("generated_at")
            or audit.get("revised_at") != proposed.get("generated_at")):
        errors.append("sw3_cutover_revision_provenance_invalid")
    try:
        a = datetime.fromisoformat(previous["generated_at"])
        b = datetime.fromisoformat(proposed["generated_at"])
        if (a.utcoffset() is None or b.utcoffset() is None
                or b <= a
                or b.astimezone(BEIJING).date().isoformat() != DAY
                or b > datetime.now(BEIJING)
                or datetime.now(BEIJING).date().isoformat() != DAY):
            errors.append("sw3_cutover_revision_time_invalid")
    except (ValueError, TypeError, KeyError):
        errors.append("sw3_cutover_revision_time_invalid")
    for key in set(previous) | set(proposed):
        if key not in ("generated_at", "scan_audit", "trends") and previous.get(key) != proposed.get(key):
            errors.append("sw3_cutover_top_level_rewritten:" + key)
    before, after = previous.get("trends"), proposed.get("trends")
    if (not isinstance(before, list) or not isinstance(after, list)
            or len(before) != len(after)):
        return errors + ["sw3_cutover_trend_list_changed"]
    if not all(isinstance(x, dict) for x in before + after):
        return errors + ["sw3_cutover_trend_invalid"]
    if ([t.get("episode_id") for t in before] !=
            [t.get("episode_id") for t in after]):
        errors.append("sw3_cutover_episode_identity_changed")
    changed = []
    seen_codes = {}
    for old, now in zip(before, after):
        eid = old.get("episode_id")
        old_fields = {k: v for k, v in old.items()
                      if k not in ("industry_assessments", "priority_exclusion_reason")}
        new_fields = {k: v for k, v in now.items()
                      if k not in ("industry_assessments", "priority_exclusion_reason")}
        if old_fields != new_fields:
            errors.append(str(eid) + ":sw3_cutover_theme_rewritten")
        if old.get("priority_exclusion_reason") != now.get("priority_exclusion_reason"):
            if (old.get("priority_exclusion_reason") is not None
                    or now.get("in_new_position_priority") is True
                    or not isinstance(now.get("priority_exclusion_reason"), str)
                    or len(now["priority_exclusion_reason"].strip()) < 15):
                errors.append(str(eid) + ":sw3_cutover_priority_reason_invalid")
        a, b = old.get("industry_assessments"), now.get("industry_assessments")
        if not isinstance(a, list) or not isinstance(b, list) or len(a) != len(b):
            errors.append(str(eid) + ":sw3_cutover_industries_changed")
            continue
        for original, row in zip(a, b):
            if original.get("industry_lifecycle") is not None:
                errors.append(str(eid) + ":sw3_cutover_cannot_overwrite_lifecycle")
            if {k:v for k,v in original.items() if k != "industry_lifecycle"} != {
                    k:v for k,v in row.items() if k != "industry_lifecycle"}:
                errors.append(str(eid) + ":sw3_cutover_industry_state_rewritten")
            expected_phase = phase_snapshot(old)
            base = (row.get("industry_lifecycle") or {}).get("cutover_baseline") or {}
            if (base.get("legacy_theme_d123") != expected_phase
                    or base.get("d123_stage") != old.get("d123_stage")
                    or base.get("phase_origin") != "LEGACY_THEME_D123"):
                errors.append(str(eid) + ":sw3_cutover_theme_phase_mismatch")
            errors.extend(validate_industry_lifecycle(
                row, original, DAY, same_day=True, source_sha=source_sha
            ))
            code = row.get("industry_code")
            if code in seen_codes and (
                    seen_codes[code].get("market_state") != row.get("market_state")
                    or seen_codes[code].get("industry_lifecycle") != row.get("industry_lifecycle")):
                errors.append(str(code) + ":sw3_cutover_cross_theme_mismatch")
            seen_codes[code] = row
        changed.append(eid)
    changes = revision.get("changes") or []
    if (not isinstance(changes, list)
            or [x.get("episode_id") for x in changes if isinstance(x, dict)] != changed
            or not isinstance(revision.get("reason"), str)
            or len(revision["reason"]) < 20):
        errors.append("sw3_cutover_revision_coverage_invalid")
    return errors


def validate_historical_forward_baseline(current, previous, day, *, same_day=False, source_sha=None):
    """Replay-only alternative forward baseline contract from November 23.

    D1-D3 is a fresh, explicitly labeled validation window only for still-pending
    legacy industries. An already confirmed legacy industry carries its published
    state WITHOUT forging a D1 or a historical confirmation date.
    """
    from scripts.industry_lifecycle import (
        _valid_day, _valid_evidence, CUTOVER_BASELINE_BASIS, CUTOVER_BASELINE_DATE, SHA, TRACK,
    )
    code = current.get("industry_code", "unknown")
    errors = []
    life = current.get("industry_lifecycle") or {}
    base = life.get("cutover_baseline")
    if not isinstance(base, dict):
        return [f"{code}:cutover_baseline_missing"]
    if life.get("episodes") not in (None, []):
        errors.append(f"{code}:cutover_cannot_forge_historical_episodes")
    initial = base.get("initial_market_state")
    sha = base.get("source_registry_blob_sha")
    asof = base.get("asof_trade_date")
    if (base.get("basis") != CUTOVER_BASELINE_BASIS
            or asof != CUTOVER_BASELINE_DATE or day <= asof
            or base.get("industry_code") != code
            or initial not in TRACK
            or not isinstance(sha, str) or SHA.fullmatch(sha) is None):
        errors.append(f"{code}:cutover_identity_invalid")
    if previous is None:
        errors.append(f"{code}:cutover_requires_published_previous_industry")
        return errors
    prior_base = ((previous.get("industry_lifecycle") or {}).get("cutover_baseline")
                  if isinstance(previous, dict) else None)
    if prior_base is None:
        if (previous.get("market_state") != initial
                or previous.get("industry_code") != code
                or previous.get("industry_lifecycle") is not None
                or source_sha != sha
                or asof != "2026-11-23"):
            errors.append(f"{code}:cutover_provenance_mismatch")
    else:
        immutable = ("basis", "asof_trade_date", "source_registry_blob_sha",
                     "industry_code", "initial_market_state")
        if any(base.get(key) != prior_base.get(key) for key in immutable):
            errors.append(f"{code}:cutover_baseline_rewritten")

    history = base.get("state_history")
    if not isinstance(history, list) or not history:
        return errors + [f"{code}:cutover_review_history_missing"]
    prev_state, prev_day, days = initial, asof, []
    for row in history:
        if (not isinstance(row, dict) or not _valid_day(row.get("trade_date"))
                or row["trade_date"] > day or row["trade_date"] <= asof
                or row.get("from") != prev_state or row.get("to") not in TRACK
                or row["trade_date"] < prev_day
                or (row["trade_date"] == prev_day and row.get("event") != "same_day_revision")):
            errors.append(f"{code}:cutover_review_history_invalid")
            continue
        if row["trade_date"] not in days:
            days.append(row["trade_date"])
        prev_day, prev_state = row["trade_date"], row["to"]
    if history[-1].get("trade_date") != day or prev_state != current.get("market_state"):
        errors.append(f"{code}:cutover_current_state_mismatch")

    decision, stage, decision_day = (base.get("d123_decision"),
                                     base.get("d123_stage"),
                                     base.get("d123_decision_trade_date"))
    if initial == "趋势确认":
        if (decision != "INHERITED_CONFIRMED" or stage is not None
                or decision_day is not None):
            errors.append(f"{code}:cutover_legacy_confirmation_must_remain_unstaged")
    else:
        stages = {"D1": 1, "D2": 2, "D3": 3}
        if stage not in stages:
            errors.append(f"{code}:cutover_review_stage_invalid")
        elif stages[stage] > len(days) or (
                decision == "PENDING" and stages[stage] != len(days)):
            errors.append(f"{code}:cutover_review_session_mismatch")
        if decision == "PENDING":
            if decision_day is not None or stage == "D3":
                errors.append(f"{code}:cutover_d3_requires_final_verdict")
        elif decision in {"CONFIRMED", "NOT_CONFIRMED"}:
            index = stages.get(stage, 0) - 1
            if (index < 0 or index >= len(days)
                    or decision_day != days[index]
                    or (decision == "CONFIRMED") != (
                        any(h.get("trade_date") == decision_day
                            and h.get("to") == "趋势确认" for h in history))
                    or (decision == "NOT_CONFIRMED" and stage != "D3")):
                errors.append(f"{code}:cutover_verdict_invalid")
        else:
            errors.append(f"{code}:cutover_review_decision_invalid")

    # No automatic confirmation: a newly confirmed or re-confirmed legacy
    # industry needs its OWN market structure, breadth and relative-strength facts.
    changed_to_confirmed = (current.get("market_state") == "趋势确认"
                            and previous.get("market_state") != "趋势确认")
    if changed_to_confirmed:
        evidence = base.get("confirmation_evidence")
        supported = {
            fact.get("dimension") for fact in evidence
            if isinstance(fact, dict)
            and _valid_evidence(fact, day)
            and fact.get("industry_code") == code
            and (fact.get("dimension") != "MARKET_STRUCTURE"
                 or fact.get("impact") in {"STRUCTURAL", "CRITICAL"})
        } if isinstance(evidence, list) else set()
        if not {"MARKET_STRUCTURE", "MARKET_BREADTH", "RELATIVE_STRENGTH"}.issubset(supported):
            errors.append(f"{code}:cutover_new_confirmation_evidence_incomplete")

    if prior_base is not None:
        old_history = prior_base.get("state_history")
        if not isinstance(old_history, list) or history[:len(old_history)] != old_history:
            errors.append(f"{code}:cutover_history_rewritten")
        else:
            tail = history[len(old_history):]
            if same_day:
                if len(tail) > 1 or (tail and (
                        tail[0].get("event") != "same_day_revision"
                        or tail[0].get("trade_date") != day)):
                    errors.append(f"{code}:cutover_same_day_revision_invalid")
            elif (len(tail) != 1 or tail[0].get("trade_date") != day):
                errors.append(f"{code}:cutover_daily_review_missing")
        if prior_base.get("d123_decision") != "PENDING" and any(
                prior_base.get(key) != base.get(key)
                for key in ("d123_stage", "d123_decision", "d123_decision_trade_date")):
            errors.append(f"{code}:cutover_frozen_verdict_rewritten")
        if prior_base.get("d123_decision") == "PENDING" and not same_day:
            expected = {"D1": "D2", "D2": "D3"}.get(prior_base.get("d123_stage"))
            if stage != expected:
                errors.append(f"{code}:cutover_stage_progression_invalid")
        if same_day and any(prior_base.get(key) != base.get(key)
                            for key in ("d123_stage", "d123_decision",
                                        "d123_decision_trade_date")):
            errors.append(f"{code}:cutover_same_day_verdict_changed")
    return errors
