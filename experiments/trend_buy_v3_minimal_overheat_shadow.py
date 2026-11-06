#!/usr/bin/env python3
"""Single-cause, falsifiable A-share Top5 ranking ablation (SHADOW ONLY).

Do not confuse near-term entry attractiveness and READY trade authorization.
Keep official Top5 membership, published evidence, READY/WAIT state and hard
6%/1.5R/8% execution gates untouched. Remove the *lexicographic* "overheated
always loses" ranking veto, replacing it with a continuous risk cost.
The penalty constant is an ex-ante research hypothesis, not a fitted optimum.
"""
from __future__ import annotations
import importlib.util
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
_spec=importlib.util.spec_from_file_location(
    "trend_buy_engine_for_v3_shadow",ROOT/"scripts/trend_buy_engine.py")
engine=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(engine)
VERSION="V3_SOFT_OVERHEAT"
PENALTY_PER_MA20_PCT_OVER_8=0.01
MAX_PENALTY=0.15


def eligibility_and_key(row, trade_date):
    if row.get("status") not in ("READY","WAIT"):
        raise ValueError("unresearchable_status")
    if row.get("data_date") != trade_date:
        raise ValueError("stale_or_future_company_structure")
    details=engine.top5_rank_details(row)
    base=details["ranking_key"]
    if len(base)!=9:
        raise ValueError("unexpected_rank_key_schema")
    ctx=row.get("technical_context") or {}
    gap=ctx.get("distance_to_ma20_pct")
    if not engine.val(gap) and engine.pos(ctx.get("ma20")) and engine.pos(row.get("current_price")):
        gap=100*(row["current_price"]/ctx["ma20"]-1)
    # Only above-MA20 overextension is "chasing". A stock trading far BELOW
    # MA20 is a recovery/downtrend issue, not a high-price extension.
    # Unverified data cannot be assumed safe.
    excess=max(0.,gap-engine.MAX_MA20_DISTANCE_PCT) if engine.val(gap) else 15.
    cost=min(MAX_PENALTY, PENALTY_PER_MA20_PCT_OVER_8*excess)
    adjusted_strength=round(details["volume_strength"]-cost, 6)
    # Preserve published tiers: READY gate, positive five-day trend, verified
    # fresh break/support; move binary overheat from second to a continuous
    # cost applied to price/volume strength. This changes ONE ranking mechanism.
    adjusted=(base[0],base[2],base[3],-adjusted_strength,
              base[5],base[6],base[7],base[8])
    return {
        "code":row["code"],"company_name":row.get("company_name"),
        "status":row["status"],"ranking_key":adjusted,
        "original_key":base,"signal":details["follow_signal"],
        "overextended":details["overextended"],
        "ma20_distance_pct":gap,
        "strength_before_penalty":details["volume_strength"],
        "continuous_overheat_cost":round(cost,5),
        "strength_after_penalty":adjusted_strength,
        "trade_permission_unchanged":True,
    }


def rerank_formal(formal, peer_scores=None):
    """Interface parity with historical replay; peers unused intentionally."""
    day=formal.get("trade_date")
    if not isinstance(day,str) or not day:
        raise ValueError("valid_trade_date_required")
    lookup={r["code"]:r for r in (formal.get("ready") or [])+(formal.get("wait") or [])}
    groups=[]
    for group in formal.get("top5_by_theme") or []:
        items=[]
        for x in group.get("items") or []:
            code=x["code"]
            if code not in lookup:
                raise ValueError("published_top5_without_researched_company:"+code)
            items.append(eligibility_and_key(lookup[code],day))
        items.sort(key=lambda x:x["ranking_key"])
        for rank,item in enumerate(items,1):
            item["rank"]=rank
        groups.append({
            "trend_name":group.get("trend_name"),
            "baseline_codes":[x["code"] for x in group.get("items") or []],
            "shadow_codes":[x["code"] for x in items],
            "items":items,
        })
    return {
        "version":VERSION,"mode":"SHADOW_ONLY_NO_PRODUCTION_OUTPUT",
        "trade_date":day,"scope":"PUBLISHED_RESEARCHED_TOP5_ONLY",
        "changed_mechanism":"OVEREXTENSION_LEXICOGRAPHIC_VETO_TO_CONTINUOUS_SOFT_COST",
        "risk_gate_changed":False,"status_changed":False,
        "pre_screen_membership_changed":False,
        "new_unresearched_companies_added":False,
        "groups":groups,
    }
