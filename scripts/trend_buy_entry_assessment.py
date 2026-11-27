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
            or review.get("phase") not in PHASES
            or not all(text_ok(review.get(k)) for k in TEXT_FIELDS)):
        return None, "ENTRY_ASSESSMENT_INVALID"
    mode = review.get("mode")
    confirmation = review.get("confirmation")
    source, proposed = review.get("anchor_source"), review.get("anchor_price")
    if mode == "NO_SETUP":
        if confirmation != "PENDING" or source is not None or proposed is not None:
            return None, "ENTRY_ASSESSMENT_INVALID"
        return None, "NO_SETUP"
    if mode not in SOURCES or source not in SOURCES[mode] or confirmation not in {"PENDING", "CONFIRMED"}:
        return None, "ENTRY_ASSESSMENT_INVALID"
    if not isinstance(s, dict) or s.get("data_status") != "verified" or s.get("data_date") != day:
        return None, "ENTRY_STRUCTURE_UNVERIFIED"
    actual = anchor_value(s, source, day)
    p = s.get("current_price")
    if not (engine.pos(actual) and engine.pos(proposed) and engine.pos(p)) or abs(actual-proposed) > .001:
        return None, "ENTRY_ANCHOR_UNVERIFIED"
    # Observation must be close enough to matter; never substitute remote MA60.
    if abs(actual / p - 1) > engine.MAX_MA20_DISTANCE_PCT / 100:
        return None, "ENTRY_ANCHOR_TOO_DISTANT"
    if confirmation == "CONFIRMED":
        expected = "breakout_level" if mode == "BREAKOUT" else "current_day_low"
        if source != expected:
            return None, "ENTRY_CONFIRMED_ANCHOR_MISMATCH"
    return engine.price(actual), "VERIFIED"

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
    }
    return row, ref
