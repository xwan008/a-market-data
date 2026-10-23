#!/usr/bin/env python3
"""Read-only, as-of shadow study of *current* 1–3 day trend-entry acceptance.

NOT an implementation of official Top5, READY/WAIT, handoff or stop orders.
No assumption that the observed local support is the true first trend retest.
Do not use the resulting conditional R as an executable trade R.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CODES = ("603416", "002979", "603275", "603583", "603025")
MAX_RISK_PCT = 6.0
MIN_R = 1.5


def finite_positive(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v > 0


def round3(v):
    return round(v + 1e-12, 3)


def nearest_resistance(ctx, asof, current):
    """Historical pressure is relevant ONLY as an as-of, nearby obstacle.

    A months-old pivot may still matter ABOVE today's price. It is never
    allowed to supply the stop or replace the 1–3 day acceptance structure.
    """
    found = []
    local = ctx.get("first_effective_resistance") or {}
    if isinstance(local, dict) and finite_positive(local.get("price")) and local["price"] > current:
        if not local.get("date") or local["date"] <= asof:
            found.append((local["price"], local.get("source") or "same_day_price_structure"))
    ext = ctx.get("attention_resistance") or {}
    if (isinstance(ext, dict) and ext.get("status") == "VERIFIED"
            and ext.get("source") == "asof_180bar_confirmed_pivot"
            and finite_positive(ext.get("price")) and ext["price"] > current
            and isinstance(ext.get("date"), str) and ext["date"] <= asof
            and ext.get("history_points", 0) >= 120):
        found.append((ext["price"], "verified_history_pivot"))
    return min(found, key=lambda r: r[0]) if found else None


def evaluate_recent_acceptance(history, row, asof, lookback=3):
    """Inspect only the completed as-of bar and 1–3 preceding trading bars.

    Comparison price is the completed day's CLOSE (zero slippage), never
    a claimed next-day fill. Structure stop is a separate OBSERVATION proxy.
    """
    if lookback not in (1, 2, 3):
        raise ValueError("lookback_must_be_1_2_3")
    bars = sorted([b for b in history if isinstance(b.get("date"), str)
                   and b["date"] <= asof], key=lambda b: b["date"])
    if len(bars) < max(11, lookback + 1) or bars[-1]["date"] != asof:
        raise ValueError("asof_bar_missing_or_history_short")
    day, previous = bars[-1], bars[-(lookback + 1):-1]
    for b in previous + [day]:
        if not all(finite_positive(b.get(k)) for k in ("close", "high", "low", "volume")):
            raise ValueError("invalid_ohlcv")
        if b["high"] < b["low"] or not b["low"] <= b["close"] <= b["high"]:
            raise ValueError("inconsistent_bar")
    price = day["close"]
    frozen = row.get("current_price")
    if not finite_positive(frozen) or abs(frozen - price) > max(.011, .001 * price):
        raise ValueError("frozen_price_mismatch")
    ctx = row.get("technical_context") or {}
    baseline = min(x["low"] for x in previous)
    today_low = day["low"]
    close_location = ((price - today_low) / (day["high"] - today_low) * 100
                      if day["high"] > today_low else 50.0)
    positive = price > previous[-1]["close"]
    ratio = ctx.get("volume_ratio_1d_vs_20d")
    verified_volume = finite_positive(ratio) and ratio >= 1.3
    strong_close = close_location >= 65
    sweep_pct = max(0.0, (baseline - today_low) / baseline * 100)
    close_reclaimed = price > baseline

    # HOLD = tested existing 3-day minimum within 0.5% and recovered.
    # SWEEP_RECLAIM = punctured by >0.5%, closed back above it strongly.
    # These are observations, not a proof of first touch or future follow-through.
    if (today_low >= baseline * .995 and today_low <= baseline * 1.005
            and close_reclaimed and positive and strong_close):
        mode = "LOCAL_SUPPORT_HOLD"
        anchor = min(baseline, today_low)
    elif (today_low < baseline * .995 and close_reclaimed
          and positive and strong_close):
        mode = "SAME_DAY_SWEEP_RECLAIM"
        anchor = today_low  # old support already pierced; no stale anchor stop
    else:
        mode = "UNCONFIRMED_LOCAL_ACCEPTANCE"
        anchor = None

    stop = round3(anchor * .995) if anchor is not None else None
    # Price risk is a snapshot comparison from the as-of CLOSE, not
    # risk on an unobserved future order.
    price_risk = ((price - stop) / price * 100 if stop is not None else None)
    obstacle = nearest_resistance(ctx, asof, price)
    resistance = obstacle[0] if obstacle else None
    conditional_r = ((resistance - price) / (price - stop)
                     if resistance is not None and stop is not None and stop < price
                     else None)
    # A cap is NOT a recommended bid; it is the mathematical ceiling if this
    # exact historical stop and resistance remained valid in a future setup.
    max_risk_entry = stop / (1 - MAX_RISK_PCT / 100) if stop is not None else None
    max_rr_entry = ((resistance + MIN_R * stop) / (1 + MIN_R)
                    if resistance is not None and stop is not None else None)
    reasons = []
    if mode == "UNCONFIRMED_LOCAL_ACCEPTANCE":
        reasons.append("no_1to3d_acceptance_pattern")
    if not verified_volume:
        reasons.append("volume_confirmation_missing")
    if price_risk is not None and price_risk > MAX_RISK_PCT:
        reasons.append("asof_close_risk_above_6pct")
    if conditional_r is None:
        reasons.append("resistance_or_stop_missing")
    elif conditional_r < MIN_R:
        reasons.append("first_resistance_below_1_5R")
    # A shallow sweep is better grounded than a deep undercut but still
    # does NOT prove a retest succeeded on later days.
    evidence = ("DEEP_SWEEP_UNCERTAIN" if sweep_pct > 2 else
                "ASOF_SINGLE_BAR_ONLY" if anchor is not None else
                "INSUFFICIENT")
    return {
        "code": row["code"], "name": row.get("company_name"),
        "asof_date": asof, "lookback_trading_days": lookback,
        "stage": "SHADOW_OBSERVATION_NOT_EXECUTABLE",
        "observed_pattern": mode,
        "first_acceptance_proven": False,
        "acceptance_evidence": evidence,
        "prior_support_low": round3(baseline),
        "asof_low": round3(today_low),
        "asof_close": round3(price),
        "sweep_depth_pct": round(sweep_pct, 2),
        "close_location_pct": round(close_location, 2),
        "volume_ratio_1d_vs_20d": round(ratio, 3) if finite_positive(ratio) else None,
        "observation_anchor": round3(anchor) if anchor is not None else None,
        "observation_stop": stop,
        "close_to_stop_risk_pct": round(price_risk, 2) if price_risk is not None else None,
        "first_verified_resistance": round3(resistance) if resistance else None,
        "conditional_close_R": round(conditional_r, 2) if conditional_r is not None else None,
        "max_entry_for_6pct_risk": round3(max_risk_entry) if max_risk_entry else None,
        "max_entry_for_1_5R": round3(max_rr_entry) if max_rr_entry else None,
        "observation_passes_screen": not reasons,
        "study_blocks": reasons,
        "quote_basis": "completed_asof_close_no_slippage_not_real_order",
        "official_status_unmodified": row.get("status"),
    }


def run(root, asof, codes=DEFAULT_CODES, lookback=3):
    formal = json.loads((root / "research/trend_buy_formal_result.json").read_text(encoding="utf-8"))
    if formal.get("trade_date") != asof:
        raise ValueError("historical_date_requires_matching_asof_formal_snapshot")
    current = {x["code"]: x for x in (formal.get("ready") or []) + (formal.get("wait") or [])}
    result = []
    cache = {}
    for code in codes:
        if code not in current:
            raise ValueError("missing_selected_code:" + code)
        prefix = code[:4]
        if prefix not in cache:
            cache[prefix] = json.loads((root / "data/history_shards" / (prefix + ".json")).read_text(encoding="utf-8"))
        rows = cache[prefix]["stocks"][code]["history"]
        result.append(evaluate_recent_acceptance(rows, current[code], asof, lookback))
    return {
        "mode": "SHADOW_ONLY_NO_FORMAL_TOP5_CHANGE",
        "asof_date": asof, "lookback": lookback,
        "official_ready_wait_unchanged": True,
        "official_trade_plan_not_recomputed": True,
        "candidate_count": len(result),
        "tradeable_candidate_count": 0,  # study never issues READY
        "passing_observation_count": sum(x["observation_passes_screen"] for x in result),
        "no_forced_ranking": True,
        "items": result,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--asof", required=True, help="Frozen formal date, YYYY-MM-DD")
    parser.add_argument("--lookback", type=int, default=3, choices=(1, 2, 3))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, help="Optional shadow JSON output path; never formal")
    args = parser.parse_args()
    result = run(args.root, args.asof, lookback=args.lookback)
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        target = args.output.resolve()
        if target == (args.root / "research/trend_buy_formal_result.json").resolve():
            raise ValueError("cannot_overwrite_formal_result")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
