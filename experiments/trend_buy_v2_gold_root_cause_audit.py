#!/usr/bin/env python3
"""Gold industry as-of diagnostic, isolated from the formal Top5 publisher.

Inspect ALL hard-eligible members of the same frozen SW3 cohort, including
excluded breakout leaders; do not create an investment recommendation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from build_trend_buy_manual_research import hard_reason, scores, compact_opportunity

INDUSTRY="S240401"

def run(root=ROOT, trade_date="2026-11-05", structure_provider=None):
    path=root/"data/low_risk/by_industry"/(INDUSTRY+".json")
    industry=json.loads(path.read_text(encoding="utf-8"))
    if industry.get("trade_date")!=trade_date or industry.get("industry_code")!=INDUSTRY:
        raise ValueError("frozen_industry_date_or_identity_mismatch")
    eligible=[r for r in industry.get("companies") or [] if hard_reason(r) is None]
    if len(eligible)!=len(industry.get("companies") or []):
        rejected=[{"code":r.get("code"),"reason":hard_reason(r)}
                  for r in industry.get("companies") or [] if hard_reason(r)]
    else: rejected=[]
    if structure_provider is None:
        from price_inputs import SelectedStockStructures
        structure_provider=SelectedStockStructures(trade_date)
    audit=[]
    for r, f in zip(eligible,scores(eligible)):
        context=structure_provider.get(r["code"],r)
        opportunity, reason=compact_opportunity(context,trade_date)
        match=abs(r["price"]-context.get("current_price",0))<=max(.011,r["price"]*.001)
        if not match:
            opportunity=None
            reason="FROZEN_PRICE_MISMATCH"
        score=.70*opportunity["opportunity_score"]+.30*f[0] if opportunity else None
        breakdown={
          "code":r["code"],"name":r["name"],"price":r["price"],
          "market_trend_state":r.get("trend_state"),"break_state":r.get("break_state"),
          "ma20":r.get("ma20"),"ma60":r.get("ma60"),
          "return_5d_pct_working_set":r.get("close_change_5d_pct"),
          "return_20d_pct_working_set":r.get("close_change_20d_pct"),
          "financial": {"revenue_yoy":r.get("revenue_yoy"),
                        "net_profit_yoy":r.get("net_profit_yoy"),
                        "deduct_basic_eps_yoy":r.get("deduct_basic_eps_yoy"),
                        "deduct_basic_eps":r.get("deduct_basic_eps"),
                        "operating_cashflow_per_share":r.get("operating_cashflow_per_share"),
                        "pe_ttm":r.get("pe_ttm"),"pb":r.get("pb"),"roe":r.get("roe"),
                        "financial_warning":r.get("fundamental_warnings")},
          "fundamental_score":f[0],"growth_score":f[1],"quality_score":f[2],
          "valuation_match":f[3],"trend_health_score":f[4],
          "growth_anomaly_flag":f[5],
          "bullish_break_wrongly_zeroed":("bullish" in str(r.get("break_state") or "")
              and "break_confirmed" in str(r.get("break_state") or "")
              and f[4]==0),
          "structure": {"phase":context.get("trend_phase"),
                        "eligible":context.get("low_risk_eligible"),
                        "data_status":context.get("data_status"),
                        "phase_evidence":context.get("phase_evidence"),
                        "ma20_slope_5d_pct":context.get("ma20_slope_5d_pct"),
                        "chase_risk":context.get("chase_risk"),
                        "distance_to_ma20_pct":context.get("distance_to_ma20_pct"),
                        "relative_strength_20d_vs_market_pct":context.get("relative_strength_20d_vs_market_pct"),
                        "volume_ratio_1d_vs_20d":context.get("volume_ratio_1d_vs_20d"),
                        "close_location_pct":context.get("close_location_pct")},
          "opportunity":opportunity,"prescreen_exclusion":reason,
          "prescreen_score":round(score,6) if score is not None else None}
        audit.append(breakdown)
    audit.sort(key=lambda x:(-(x["prescreen_score"] if x["prescreen_score"] is not None else -100),x["code"]))
    return {"mode":"FROZEN_GOLD_CANDIDATE_AUDIT_NO_FORMAL_CHANGE",
            "trade_date":trade_date,"industry_code":INDUSTRY,
            "complete_industry_count":len(industry.get("companies") or []),
            "hard_eligible":len(eligible),"hard_rejected":rejected,
            "scanned":audit,
            "bullish_break_penalty_candidates":[x["code"] for x in audit
                  if x["bullish_break_wrongly_zeroed"]],
            "no_real_trade_or_predicted_return":True}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--date",default="2026-11-05")
    parser.add_argument("--output",type=Path)
    opts=parser.parse_args()
    out=run(trade_date=opts.date)
    value=json.dumps(out,ensure_ascii=False,indent=2)+"\n"
    if opts.output:
        path=opts.output.resolve()
        if "shadow" not in str(path).lower() or any(z in str(path) for z in
                  ("trend_buy_formal_result","trend_buy_handoff")):
            raise ValueError("shadow_only_path_required")
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(value,encoding="utf-8")
    print(json.dumps({
        "date":out["trade_date"],
        "industry_count":out["complete_industry_count"],
        "hard_eligible":out["hard_eligible"],
        "bullish_break_zeroed":out["bullish_break_penalty_candidates"],
        "candidates":[{"code":x["code"],"name":x["name"],
                       "score":x["prescreen_score"],
                       "rejected":x["prescreen_exclusion"],
                       "phase":x["structure"]["phase"],
                       "break":x["break_state"],
                       "trend_health":x["trend_health_score"]}
                       for x in out["scanned"]]},ensure_ascii=False))

if __name__=="__main__":
    main()
