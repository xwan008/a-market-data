#!/usr/bin/env python3
"""V2 relative-entry shadow experiment. Does NOT publish trade recommendations.

The published Top5 and READY/WAIT admission are immutable inputs. This module
orders the researched names by a proxy for current relative entry attractiveness,
even if every name is WAIT. No missing stop, historical pivot, or hypothetical
future retest is turned into a tradeable R or an entry order.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

WEIGHTS = {"trend": .30, "entry": .30, "space": .25, "fundamental": .15}
VERSION = "relative_entry_shadow_v2_20261105"


def numeric(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def positive(x):
    return numeric(x) and x > 0


def clip(x):
    return max(0.0, min(1.0, x))


def norm(value, floor, span, missing=.5):
    return clip((value - floor) / span) if numeric(value) else missing


def dual_channel_select(rows, limit=5, trend_slots=3, tie=.03):
    """Shadow pre-screen: independent leader and nearer-entry coverage.

    Each row is a frozen, hard-eligible, lightweight-scored observation with
    code, leader_score and entry_score. Entries missing either score are excluded.
    Slot 6 is ONLY a near tie in entry_score to the lowest selected member.
    Verified thematic rejection must be removed by the caller before selection.
    """
    if limit < 1 or not 0 <= trend_slots <= limit or tie < 0:
        raise ValueError("invalid_dual_channel_settings")
    candidates = []
    seen = set()
    for row in rows:
        code = row.get("code")
        if not isinstance(code, str) or not code or code in seen:
            raise ValueError("missing_or_duplicate_company_code")
        seen.add(code)
        if not (numeric(row.get("leader_score")) and numeric(row.get("entry_score"))):
            continue
        if row.get("excluded_reason") or row.get("transmission") == "NOT_SUPPORTED":
            continue
        candidates.append(row)
    leaders = sorted(candidates, key=lambda x: (-x["leader_score"], x["code"]))
    entries = sorted(candidates, key=lambda x: (-x["entry_score"], x["code"]))
    picks, included = [], set()

    def take(row, channel):
        if row["code"] not in included:
            picks.append({**row, "selection_channel": channel})
            included.add(row["code"])

    for row in leaders[:trend_slots]:
        take(row, "TREND_LEADER")
    for row in entries:
        if len(picks) >= limit:
            break
        take(row, "ENTRY_OPPORTUNITY")
    if len(picks) == limit and limit >= 5:
        next_candidates = [x for x in entries if x["code"] not in included]
        if next_candidates:
            threshold = min(x["entry_score"] for x in picks)
            if next_candidates[0]["entry_score"] >= threshold - tie:
                take(next_candidates[0], "NEAR_TIE_SIXTH")
    return picks


def nearest_overhead(ctx, price, trade_date):
    """Read a verified historical pivot as a ceiling proxy, NOT a target."""
    candidates = []
    for key in ("first_effective_resistance", "attention_resistance"):
        obj = ctx.get(key)
        if not isinstance(obj, dict):
            continue
        level, date = obj.get("price"), obj.get("date")
        if not (positive(level) and level > price):
            continue
        if isinstance(date, str) and date > trade_date:
            continue
        if key == "attention_resistance" and (
            obj.get("status") != "VERIFIED" or
            obj.get("source") != "asof_180bar_confirmed_pivot" or
            (not numeric(obj.get("history_points")) or obj["history_points"] < 120)
        ):
            continue
        candidates.append((level, date, obj.get("source") or "asof_structure"))
    if not candidates:
        return None
    level, date, source = min(candidates)
    return {"price": round(level, 4), "date": date, "source": source}


def score_company(row, trade_date, fundamental=None):
    if row.get("status") not in ("WAIT", "READY"):
        raise ValueError("not_researched_eligible_company")
    if not positive(row.get("current_price")):
        raise ValueError("non_positive_current_price")
    if row.get("data_date") not in (None, trade_date):
        raise ValueError("future_or_mismatched_technical_date")
    ctx, ev = row.get("technical_context") or {}, row.get("phase_evidence") or {}
    p = row["current_price"]
    gap = ctx.get("distance_to_ma20_pct")
    if not numeric(gap) and positive(ctx.get("ma20")):
        gap = 100 * (p / ctx["ma20"] - 1)
    if not numeric(gap):
        gap = None
    close = ctx.get("close_location_pct")
    v1, v5 = ctx.get("volume_ratio_1d_vs_20d"), ctx.get("volume_ratio_5d_vs_20d")
    rs = ctx.get("relative_strength_20d_vs_market_pct")
    ret3, ret5, up5 = ev.get("return_3d_pct"), ev.get("return_5d_pct"), ev.get("positive_days_5d")
    fresh = ev.get("fresh_break") is True
    strong_break = fresh and numeric(v1) and v1 >= 1.3 and numeric(close) and close >= 65
    weak = ev.get("weak_close_high_volume") is True

    volume = (.24 * norm(v1, 1, 2) + .16 * norm(v5, 1, 1.5)
              + .20 * norm(close, 50, 50) + .31 * norm(rs, 0, 15)
              + .09 * norm(up5, 2, 3))
    phase = {"REACCELERATING": 1, "INITIATING": .95, "PULLBACK": .82,
             "REPAIRING": .63, "TRANSITION": .35, "COOLING": .1}.get(
                 row.get("trend_phase"), .4)
    trend = clip(.64 * volume + .16 * phase
                 + .10 * (1 if numeric(ret5) and ret5 > 0 else 0)
                 + .10 * int(strong_break))
    recent = ctx.get("recent_acceptance") or {}
    valid_recent = (recent.get("data_date") == trade_date
                    and recent.get("lookback_trading_days") in (1, 2, 3))
    pattern = recent.get("pattern") if valid_recent else None
    held = pattern == "LOCAL_SUPPORT_HOLD"
    swept = pattern == "SAME_DAY_SWEEP_RECLAIM"

    # Penalties are CONTINUOUS: overextended leaders remain eligible to rank.
    # The shadow still never changes formal overheat/6%/1.5R READY gates.
    extension = clip(max(0, (gap or 0) - 4) / 12) if gap is not None else .5
    rush = clip(max(0, ret3 - 6) / 10) if numeric(ret3) else .5
    entry = clip(.75 - .34 * extension - .14 * rush
                 - .32 * int(weak)
                 - .18 * int(numeric(close) and close < 40)
                 + .12 * int(held) + .05 * int(swept)
                 + .08 * int(strong_break))
    # Risk/space: a resistance distance is only a proxy, not R when no stop.
    ceiling = nearest_overhead(ctx, p, trade_date)
    zone = row.get("entry_zone")
    stop = row.get("invalidation_price")
    verified_stop = (isinstance(zone, list) and len(zone) == 2
                     and all(positive(x) for x in zone)
                     and positive(stop) and stop < zone[0] <= zone[1])
    r = None
    if verified_stop and ceiling:
        r = (ceiling["price"] - zone[1]) / (zone[1] - stop)
    if r is not None:
        space = clip(r / 2.5)
        space_basis = "CONFIRMED_ENTRY_STOP_AND_HISTORICAL_RESISTANCE"
    elif ceiling:
        space = clip(.35 + .35 * ((ceiling["price"] / p - 1) / .10))
        space_basis = "HISTORICAL_RESISTANCE_DISTANCE_ONLY_NO_R"
    else:
        space = .40
        space_basis = "RESISTANCE_UNVERIFIED_NEUTRAL_NO_R"
    # Fundamental neutral only when no frozen peer score is supplied.
    verified_fundamental = numeric(fundamental) and 0 <= fundamental <= 1
    f = fundamental if verified_fundamental else .5
    total = (WEIGHTS["trend"] * trend + WEIGHTS["entry"] * entry
             + WEIGHTS["space"] * space + WEIGHTS["fundamental"] * f)

    setup_hypotheses = []
    if strong_break and numeric(ret5) and ret5 > 0 and numeric(up5) and up5 >= 3:
        setup_hypotheses.append("TREND_FOLLOW_SHADOW_UNCONFIRMED")
    if held and numeric(v5) and v5 >= 1:
        setup_hypotheses.append("CONSOLIDATION_OR_SUPPORT_HOLD_SHADOW_UNCONFIRMED")
    return {
        "code": row["code"], "company_name": row.get("company_name"),
        "status": row["status"], "current_price": p,
        "relative_entry_score": round(total, 6),
        "components": {k: round(v, 5) for k, v in
                       (("trend", trend), ("entry", entry),
                        ("space", space), ("fundamental", f))},
        "fundamental_source": "FROZEN_PEER_SCORE" if verified_fundamental else "NEUTRAL_UNVERIFIED",
        "distance_to_ma20_pct": round(gap, 3) if gap is not None else None,
        "nearest_verified_resistance": ceiling,
        "risk_reward_R": round(r, 3) if r is not None else None,
        "space_basis": space_basis,
        "weak_close_high_volume": weak,
        "setup_hypotheses_not_buy_signals": setup_hypotheses,
        "tradeable_under_formal_rules": row["status"] == "READY",
        "ranking_not_order": True
    }


def rerank_formal(formal, peer_scores=None):
    """Shadow rerank existing published Top5: membership is frozen."""
    day = formal.get("trade_date")
    if not isinstance(day, str) or not day:
        raise ValueError("trade_date_required")
    peers = peer_scores or {}
    lookup = {r["code"]: r for r in (formal.get("ready") or []) + (formal.get("wait") or [])}
    groups = []
    for g in formal.get("top5_by_theme") or []:
        scored = []
        for item in g.get("items") or []:
            code = item["code"]
            if code not in lookup:
                raise ValueError("formal_top5_member_without_research:" + code)
            score = score_company(lookup[code], day, peers.get(code))
            scored.append(score)
        scored.sort(key=lambda x: (-x["relative_entry_score"],
                                   -x["components"]["entry"],
                                   -x["components"]["trend"], x["code"]))
        for idx, x in enumerate(scored, 1):
            x["rank"] = idx
        groups.append({"trend_name": g.get("trend_name"), "items": scored,
                       "baseline_codes": [x["code"] for x in g.get("items") or []],
                       "shadow_codes": [x["code"] for x in scored]})
    return {"version": VERSION, "mode": "SHADOW_ONLY_NO_FORMAL_PUBLICATION",
            "trade_date": day, "weights": WEIGHTS,
            "scope": "ALREADY_RESEARCHED_FORMAL_TOP5_ONLY",
            "does_not_change_ready_or_wait": True,
            "candidate_pre_screen_not_recomputed": True,
            "groups": groups}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--formal", type=Path,
                    default=Path(__file__).resolve().parents[1] /
                    "research/trend_buy_formal_result.json")
    ap.add_argument("--peer-scores", type=Path,
                    help="Optional frozen same-day map code to peer score [0,1]")
    ap.add_argument("--output", type=Path,
                    help="Optional SHADOW path, NEVER a formal output path")
    args = ap.parse_args()
    formal = json.loads(args.formal.read_text(encoding="utf-8"))
    scores = json.loads(args.peer_scores.read_text(encoding="utf-8")) if args.peer_scores else {}
    result = rerank_formal(formal, scores)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        path = args.output.resolve()
        forbidden = {
            (args.formal.resolve()),
            (Path(__file__).resolve().parents[1] / "research/trend_buy_handoff.json").resolve(),
            (Path(__file__).resolve().parents[1] / "research/trend_buy_formal_result.json").resolve()
        }
        if path in forbidden or "shadow" not in str(path).lower():
            raise ValueError("shadow_output_path_required")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
