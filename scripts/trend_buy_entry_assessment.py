"""Post-lock model entry assessment, independently verified against same-day structure.

No selection changes, no orders, no model-supplied executable price. Legacy dates
retain the original evaluator to protect locked results during recovery.
"""
try:
    from . import trend_buy_engine as engine
except ImportError:
    import trend_buy_engine as engine

CUTOVER_AFTER = "2026-11-27"
PHASES = {"INITIATING", "PULLBACK", "REACCELERATING", "REPAIRING",
          "COOLING", "FAILED", "TRANSITION"}
SOURCES = {
    "BREAKOUT": {"breakout_level", "first_effective_resistance.price",
                 "attention_resistance.price", "phase_evidence.prior_5d_high"},
    "PULLBACK": {"ma20", "current_day_low", "phase_evidence.recent_3d_low"},
}
TEXT_FIELDS = ("entry_basis", "failure_basis", "confirmation_condition", "avoid_condition")

def text_ok(v):
    return isinstance(v, str) and bool(v.strip()) and len(v) <= 1000

def anchor_value(s, source, day):
    if source in ("first_effective_resistance.price", "attention_resistance.price"):
        key = source.split(".")[0]
        pivot = s.get(key) or {}
        if not isinstance(pivot, dict):
            return None
        date = pivot.get("date")
        if not isinstance(date, str) or len(date) != 10 or date > day:
            return None
        if key == "attention_resistance" and (
                pivot.get("status") != "VERIFIED" or
                pivot.get("source") != "asof_180bar_confirmed_pivot" or
                not engine.val(pivot.get("history_points")) or pivot["history_points"] < 120):
            return None
        return pivot.get("price")
    if source.startswith("phase_evidence."):
        return (s.get("phase_evidence") or {}).get(source.split(".")[1])
    return s.get(source)

def validate_assessment(review, s, code, day):
    if not isinstance(review, dict):
        return None, "ENTRY_ASSESSMENT_MISSING"
    if (review.get("code") != code or review.get("as_of_date") != day
            or not isinstance(review.get("phase"), str) or review["phase"] not in PHASES
            or not all(text_ok(review.get(k)) for k in TEXT_FIELDS)):
        return None, "ENTRY_ASSESSMENT_INVALID"
    mode = review.get("mode")
    confirmation = review.get("confirmation")
    source, proposed = review.get("anchor_source"), review.get("anchor_price")
    if mode == "NO_SETUP":
        if confirmation != "PENDING" or source is not None or proposed is not None:
            return None, "ENTRY_ASSESSMENT_INVALID"
        return None, "NO_SETUP"
    if (not isinstance(mode, str) or mode not in SOURCES or
            not isinstance(source, str) or source not in SOURCES[mode] or
            confirmation not in ("PENDING", "CONFIRMED")):
        return None, "ENTRY_ASSESSMENT_INVALID"
    if (not isinstance(s, dict) or s.get("data_status") != "verified" or s.get("data_date") != day
            or not engine.val(s.get("history_points")) or s["history_points"] < 65
            or s.get("low_risk_eligible") is not True):
        return None, "ENTRY_STRUCTURE_UNVERIFIED"
    actual = anchor_value(s, source, day)
    p = s.get("current_price")
    if not (engine.pos(actual) and engine.pos(proposed) and engine.pos(p)) or abs(actual-proposed) > .001:
        return None, "ENTRY_ANCHOR_UNVERIFIED"
    # Observation must be close enough to matter; never substitute remote MA60.
    if abs(actual / p - 1) > engine.MAX_MA20_DISTANCE_PCT / 100:
        return None, "ENTRY_ANCHOR_TOO_DISTANT"
    if confirmation == "PENDING" and mode == "BREAKOUT" and actual < p:
        return None, "ENTRY_BREAKOUT_ALREADY_PASSED"
    if confirmation == "CONFIRMED":
        expected = "breakout_level" if mode == "BREAKOUT" else "current_day_low"
        if source != expected:
            return None, "ENTRY_CONFIRMED_ANCHOR_MISMATCH"
    return engine.price(actual), "VERIFIED"

def scenario(review, s, code, day):
    """Research-only conditional arithmetic; never an executable plan."""
    anchor, verification = validate_assessment(review, s, code, day)
    if verification not in ("VERIFIED", "NO_SETUP"):
        return {"verification": verification, "not_buy_order": True}
    out = {"verification": verification, "not_buy_order": True,
           "mode": review["mode"], "confirmation": review["confirmation"],
           "anchor_source": review.get("anchor_source"), "anchor_price": anchor,
           "entry_basis": review["entry_basis"], "failure_basis": review["failure_basis"],
           "confirmation_condition": review["confirmation_condition"],
           "avoid_condition": review["avoid_condition"],
           "hypothetical_entry_zone": None, "hypothetical_failure_price": None,
           "hypothetical_risk_pct": None, "hypothetical_reward_R": None,
           "verified_overhead_price": None, "observation_zone": None,
           "calculation_status": "AWAIT_REAL_STRUCTURE"}
    if verification == "NO_SETUP":
        out["calculation_status"] = "NO_GROUNDED_SETUP"
        return out
    mode = review["mode"]
    current = s["current_price"]
    # If the current completed candle really confirms the proposed shape, use
    # existing arithmetic, including its independently grounded stop, as research.
    confirmed = (mode == "BREAKOUT" and s.get("structure_type") == "breakout"
                 and s.get("breakout_confirmed") is True and current > anchor
                 and review["anchor_source"] == "breakout_level")
    if mode == "PULLBACK":
        confirmed = (s.get("structure_type") == "pullback"
                     and review["anchor_source"] == "current_day_low"
                     and anchor == engine.price(s.get("current_day_low")))
    plan = engine.build_plan(mode, s, current, confirmed=True, trade_date=day) if confirmed else None
    if plan is not None:
        zone, stop = plan["entry_zone"], plan["invalidation_price"]
        overhead = engine.verified_overhead(s, current, day)
        out["calculation_status"] = "CONFIRMED_STRUCTURE_RESEARCH_ONLY"
    elif mode == "BREAKOUT" and anchor >= current:
        # Counterfactual breakout at a known boundary: use the existing
        # boundary-relative 0.2%..2.5% entry band and 0.5% failure buffer.
        # Recalculate from actual completed confirmation before any order.
        zone = engine.pair(anchor * 1.002, anchor * 1.025)
        stop = engine.price(anchor * .995)
        overhead = engine.verified_overhead(s, anchor, day)
        out["calculation_status"] = "HYPOTHETICAL_BREAKOUT_ONLY"
    else:
        if mode == "PULLBACK" and review["anchor_source"] == "ma20":
            out["observation_zone"] = engine.pair(anchor * .97, anchor * 1.02)
        return out
    if zone is None or not engine.pos(stop) or stop >= zone[0]:
        out["calculation_status"] = "INVALID_PRICE_GEOMETRY"
        return out
    cap = zone[1]
    risk = (cap-stop)/cap*100
    target = overhead["price"] if overhead else None
    rr = (target-cap)/(cap-stop) if engine.pos(target) else None
    out.update(hypothetical_entry_zone=zone, hypothetical_failure_price=stop,
               hypothetical_risk_pct=round(risk,2),
               hypothetical_reward_R=round(rr,2) if rr is not None else None,
               verified_overhead_price=target,
               hypothetical_risk_gate=("RISK_TOO_HIGH" if risk > engine.MAX_ENTRY_RISK_PCT
                 else "OVERHEAD_UNKNOWN" if rr is None else
                 "REWARD_TOO_LOW" if rr < engine.MIN_UPSIDE_R else "ARITHMETIC_ONLY_PASS"))
    return out


def research_scenarios(review, s, code, day):
    """Primary plus at most one alternate; neither can change the locked TOP1."""
    primary = scenario(review, s, code, day)
    results = [primary]
    if isinstance(review, dict) and "alternate" in review:
        alt = review["alternate"]
        if (isinstance(alt, dict) and alt.get("mode") in ("BREAKOUT", "PULLBACK")
                and alt.get("mode") != review.get("mode")):
            results.append(scenario(alt, s, code, day))
        else:
            results.append({"verification": "ALTERNATE_INVALID", "not_buy_order": True})
    return results


def evaluate(c, s, day, review):
    row = engine.evaluate_candidate(c, s, day)
    if day <= CUTOVER_AFTER:
        return row, engine.early_watch_reference(row) if row["status"] == "WAIT" else None
    code = row["code"]
    anchor, verification = validate_assessment(review, s, code, day)
    # Existing engine remains an independent gate. Model can veto READY,
    # never grant it. Its proposed confirmed shape must agree with the
    # independently confirmed shape and stop evidence.
    proposal = review if isinstance(review, dict) else {}
    stop = row.get("setup_stop_evidence") or {}
    agrees = (verification == "VERIFIED" and proposal.get("confirmation") == "CONFIRMED"
              and proposal.get("mode") == row.get("setup_type")
              and engine.pos(stop.get("anchor_price"))
              and abs(stop["anchor_price"] - anchor) <= .001)
    if row["status"] == "READY" and not agrees:
        row.update(status="WAIT", wait_reason="WAIT_CONFIRMATION",
                   decision_reason="模型入场形态/依据未确认或与独立风控不一致；不得执行")
        row.pop("setup_stop_evidence", None)
    row["entry_assessment_verification"] = verification
    row["entry_research_scenarios"] = (research_scenarios(review, s, code, day)
                                       if row["status"] in ("READY", "WAIT") else [])
    if row["status"] != "WAIT":
        return row, None
    # Only verified anchor values reach the price fields. An invalid or
    # missing assessment cannot silently fall back to MA60 or become READY.
    trusted = verification in {"VERIFIED", "NO_SETUP"}
    ref = {
        "stage": "PRE_TREND_WATCH" if trusted else "EVIDENCE_PENDING",
        "setup_mode": ("BREAKOUT_CONFIRMATION" if proposal.get("mode") == "BREAKOUT"
                       else "PULLBACK_HOLD" if proposal.get("mode") == "PULLBACK"
                       else "SETUP_REASSESSMENT") if trusted else None,
        "conditional_trigger": proposal.get("confirmation_condition") if trusted else "入场研判或近端价格依据未通过核验，等待重新确认",
        "reference_trigger_price": anchor, "reference_zone": None,
        "invalidation_price": None, "estimated_price_risk_pct": None,
        "risk_threshold_pct": engine.EARLY_WATCH_MAX_PLAN_RISK_PCT,
        "price_basis": "同日冻结结构核验的观察参考，不是入场、止损或自动升级条件",
        "entry_assessment_verification": verification,
        "model_phase": proposal.get("phase") if trusted else None,
        "entry_basis": proposal.get("entry_basis") if trusted else None,
        "failure_basis": proposal.get("failure_basis") if trusted else None,
        "avoid_condition": proposal.get("avoid_condition") if trusted else None,
        "research_scenarios": row["entry_research_scenarios"],
    }
    return row, ref
