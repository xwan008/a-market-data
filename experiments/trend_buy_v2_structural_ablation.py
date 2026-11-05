#!/usr/bin/env python3
"""V2.1 structural-continuation ABRATION, never a formal ranking.

Test the falsifiable hypothesis that a quick bounce during a still-falling
20-day average below MA60 is less actionable than a sustained recovery.
This is NOT tuned on future returns or the identity of a gold ticker.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from trend_buy_v2_relative_entry_shadow import (
    clip, numeric, positive, score_company, shadow_prescreen
)

ROOT=Path(__file__).resolve().parents[1]
VERSION="trend_buy_v21_structural_ablation_20261105"


def structural_penalty(row, scored, trade_date):
    ctx=row.get("technical_context") or {}
    ev=row.get("phase_evidence") or {}
    price=row.get("current_price")
    ma60=ctx.get("ma60")
    slope=ctx.get("ma20_slope_5d_pct")
    r3=ev.get("return_3d_pct")
    prev5=ev.get("previous_5d_return_pct")
    relative=ctx.get("relative_strength_20d_vs_market_pct")
    is_repair=row.get("trend_phase") == "REPAIRING"
    below60=positive(ma60) and positive(price) and price<ma60
    falling20=numeric(slope) and slope<0
    penalties={}
    penalties["falling_ma20_below_ma60"]=(
        .065*clip(-slope/5) if is_repair and below60 and falling20 else 0)
    penalties["below_ma60_gap"]=(
        .055*clip((ma60-price)/ma60/.15) if is_repair and below60 else 0)
    penalties["fast_rebound_after_drawdown"]=(
        .075*clip((r3-8)/12)*clip(-prev5/8)
        if is_repair and below60 and numeric(r3) and numeric(prev5)
            and r3>8 and prev5<0 else 0)
    penalties["negative_medium_term_relative_strength"]=(
        .045*clip(-relative/10)
        if is_repair and below60 and numeric(relative) and relative<0 else 0)
    overhead=scored.get("nearest_verified_resistance")
    headroom=((overhead["price"]/price-1)*100
              if overhead and positive(price) else None)
    penalties["near_verified_overhead_without_stop"]=(
        .055*clip((3-headroom)/3)
        if row.get("status")=="WAIT" and headroom is not None
            and 0<headroom<3 and scored.get("risk_reward_R") is None else 0)
    unavailable=[k for k,v in {
        "ma20_slope_5d_pct":slope, "return_3d_pct":r3,
        "previous_5d_return_pct":prev5,
        "relative_strength_20d_vs_market_pct":relative}.items() if not numeric(v)]
    return {k:round(v,6) for k,v in penalties.items()}, unavailable


def audited_earnings_penalty(disclosure, trade_date):
    """Optional prior-filing facts only, never inferred from company name."""
    if not disclosure:
        return 0.0,"NOT_IN_CORE_SCORING"
    date=disclosure.get("published_at")
    if not isinstance(date,str) or date>trade_date:
        raise ValueError("future_or_missing_disclosure_date")
    profit=disclosure.get("attributable_profit_cny")
    core=disclosure.get("deducted_attributable_profit_cny")
    q3=disclosure.get("q3_profit_yoy_pct")
    if not positive(profit) or not numeric(core) or core<0 or core>profit:
        return 0.0,"DISCLOSED_PROFIT_INCONSISTENT_NO_AUTOMATIC_PENALTY"
    nonrecurring=1-core/profit
    penalty=.065*clip((nonrecurring-.2)/.5)
    if numeric(q3) and q3<0:
        penalty+=.025*clip(-q3/80)
    return round(penalty,6),"AUDITED_NONRECURRING_AND_QUARTERLY"


def score_structural(row, trade_date, fundamental=None, disclosure=None):
    base=score_company(row,trade_date,fundamental)
    penalties,missing=structural_penalty(row,base,trade_date)
    earnings,earnings_basis=audited_earnings_penalty(disclosure,trade_date)
    total=round(clip(base["relative_entry_score"]-sum(penalties.values())-earnings),6)
    return {**base,
        "v21_structural_score":total,
        "v20_baseline_score":base["relative_entry_score"],
        "structural_penalties":penalties,
        "audited_earnings_penalty":earnings,
        "earnings_penalty_basis":earnings_basis,
        "incomplete_structural_fields":missing,
        "upgrade_to_ready":False,
        "not_in_formal_top5":False,
        "estimated_profit_quality_cannot_replace_formal_review":True
    }


def rerank_structural(formal, peers=None, disclosures=None):
    day=formal.get("trade_date")
    if not isinstance(day,str):
        raise ValueError("asof_trade_date_required")
    lookup={x["code"]:x for x in (formal.get("ready") or [])+(formal.get("wait") or [])}
    peers=peers or {}
    disclosures=disclosures or {}
    groups=[]
    for g in formal.get("top5_by_theme") or []:
        rows=[]
        for item in g["items"]:
            row=lookup[item["code"]]
            score=score_structural(row,day,peers.get(item["code"]),
                                   disclosures.get(item["code"]))
            rows.append(score)
        rows.sort(key=lambda x:(-x["v21_structural_score"],
                                -x["components"]["trend"],x["code"]))
        for i,r in enumerate(rows,1):
            r["rank"]=i
        groups.append({"trend_name":g.get("trend_name"),
                       "original_codes":[x["code"] for x in g["items"]],
                       "v21_codes":[x["code"] for x in rows],
                       "items":rows})
    return {"version":VERSION,"mode":"SHADOW_NO_TRADE_OR_FORMAL_UPGRADE",
            "trade_date":day,"groups":groups,
            "research_scope":"ORIGINAL_RESEARCHED_TOP5_ONLY",
            "disclosures_for_historical_replay":"NONE_UNLESS_SAME_DAY_AUDITED",
            "ready_contract_unchanged":True}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--formal",type=Path,default=ROOT/"research/trend_buy_formal_result.json")
    p.add_argument("--frozen-screen",type=Path)
    p.add_argument("--disclosures",type=Path)
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    formal=json.loads(a.formal.read_text(encoding="utf-8"))
    peer={}
    if a.frozen_screen:
        frozen=json.loads(a.frozen_screen.read_text(encoding="utf-8"))
        peer=shadow_prescreen(frozen,formal["trade_date"])["fundamental_scores"]
    disclosures=json.loads(a.disclosures.read_text(encoding="utf-8")) if a.disclosures else {}
    out=rerank_structural(formal,peer,disclosures)
    text=json.dumps(out,indent=2,ensure_ascii=False)+"\n"
    if a.output:
        path=a.output.resolve()
        if "shadow" not in str(path).lower() or any(p in str(path) for p in
              ("trend_buy_formal_result","trend_buy_handoff")):
            raise ValueError("shadow_only_output_required")
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(text,encoding="utf-8")
    print(json.dumps({"date":out["trade_date"],
                      "new_rankings":{g["trend_name"]:[x["company_name"] for x in g["items"]]
                                      for g in out["groups"]}},ensure_ascii=False))


if __name__=="__main__":
    main()
