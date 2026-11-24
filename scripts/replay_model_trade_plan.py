#!/usr/bin/env python3
"""Offline model-proposal validation experiment. No publication or handoff.

The model owns order, interpretation, and proposed prices. This validator
checks the frozen scope and evidence; it never invents a substitute trade,
changes the research rank, or upgrades an observation to READY.
"""
from __future__ import annotations
import argparse
from datetime import date
import json
import math
from pathlib import Path

RISK_LIMIT_PCT=6.0
MIN_REWARD_R=1.5
MAX_SLIPPAGE_PCT=1.2
# Retain production guardrails until their replacement is independently tested.
MAX_MA20_DISTANCE_PCT=8.0
STOP_BUFFER_PCT=0.5
FIELDS={"open","high","low","close"}


def number(x):
    return type(x) in (int,float) and math.isfinite(x)


def positive(x):
    return number(x) and x>0


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def valid_date(x):
    return isinstance(x,str) and date.fromisoformat(x).isoformat()==x


def history_rows(stock,day,price):
    rows=stock.get("history")
    if not isinstance(rows,list) or len(rows)<65:
        raise ValueError("HISTORY_INSUFFICIENT")
    if any(not isinstance(r,dict) or not valid_date(r.get("date")) for r in rows):
        raise ValueError("HISTORY_DATE_INVALID")
    # This offline trial requires an immutable snapshot, not a today's
    # history series silently truncated at a past date.
    dates=[r["date"] for r in rows]
    if dates!=sorted(set(dates)) or dates[-1]!=day:
        raise ValueError("HISTORY_NOT_FROZEN_ASOF")
    if any(not all(positive(r.get(k)) for k in FIELDS|{"volume"})
           or r["low"]>min(r["open"],r["close"])
           or r["high"]<max(r["open"],r["close"])
           for r in rows):
        raise ValueError("OHLCV_INVALID")
    if not positive(price) or abs(rows[-1]["close"]-price)>max(.011,price*.001):
        raise ValueError("FROZEN_CLOSE_MISMATCH")
    return rows


def anchor(ref,by_date,day):
    """An assertion is a dated OHLC field, not an untraceable model price."""
    if not isinstance(ref,dict) or ref.get("field") not in FIELDS:
        raise ValueError("ANCHOR_FIELD_INVALID")
    stamp=ref.get("date")
    value=ref.get("price")
    if not valid_date(stamp) or stamp>day or stamp not in by_date:
        raise ValueError("ANCHOR_DATE_INVALID")
    actual=by_date[stamp][ref["field"]]
    if not positive(value) or abs(value-actual)>1e-6:
        raise ValueError("ANCHOR_PRICE_MISMATCH")
    return actual


def nearest_resistance(rows):
    # Grounded 3-left/3-right pivots, only completed bars, no future targets.
    current=rows[-1]["close"]
    past=rows[-180:]
    if len(past)<120:
        return None
    levels=[]
    for i in range(3,len(past)-3):
        x=past[i]
        if x["high"]>current and all(x["high"]>=r["high"] for r in past[i-3:i+4]):
            levels.append({"date":x["date"],"price":x["high"],"field":"high"})
    # Also include observed near-term overhead, not only confirmed pivots.
    # The highest point of the last 5 completed sessions before signal day
    # is a conservative obstacle when it remains above today's close.
    near=max(rows[-6:-1],key=lambda x:x["high"])
    if near["high"]>current:
        levels.append({"date":near["date"],"price":near["high"],"field":"high"})
    return min(levels,key=lambda x:x["price"]) if levels else None


def validate_plan(proposal,row,rows,day):
    result={"code":row["code"],"model_rank":proposal["model_rank"],
            "model_reason":proposal["model_reason"],"model_setup":proposal["setup"],
            "status":"WAIT","entry_zone":None,"invalidation_price":None,
            "initial_risk_pct":None,"upside_to_resistance_R":None,
            "watch_reference":None,"checks":[],"not_trade_permission":True}
    by_date={r["date"]:r for r in rows}
    current=rows[-1]["close"]
    def check(condition,reason):
        if not condition:
            raise ValueError(reason)
        result["checks"].append(reason.replace("_FAILED","")+"_PASS")
    try:
        if proposal.get("decision") not in {"WAIT","PROPOSE_ENTRY"}:
            raise ValueError("MODEL_DECISION_INVALID")
        if proposal["decision"]=="WAIT":
            # Observation only: the model must not smuggle an executable plan.
            check(proposal.get("entry_zone") is None and proposal.get("invalidation_price") is None,
                  "WAIT_HAS_EXECUTABLE_PLAN_FAILED")
            watch=proposal.get("watch_anchor")
            if watch is not None:
                anchor(watch,by_date,day)
                check(isinstance(proposal.get("watch_condition"),str) and bool(proposal["watch_condition"].strip()),
                      "WATCH_CONDITION_FAILED")
                result["watch_reference"]={"anchor":watch,"condition":proposal["watch_condition"],
                                           "observation_only":True}
            result["decision_reason"]="MODEL_WAITS_FOR_CONFIRMATION"
            return result

        check(row.get("market_state")=="趋势确认" and row.get("transmission")=="SUPPORTED",
              "CONFIRMED_SCOPE_FAILED")
        check(proposal["setup"] in {"BREAKOUT","PULLBACK","CONTINUATION","REPAIR","DIVERGENCE_RECOVERY"},
              "UNSUPPORTED_SETUP_FAILED")
        boundary=proposal.get("structure_anchor")
        failure=proposal.get("failure_anchor")
        boundary_price=anchor(boundary,by_date,day)
        failure_price=anchor(failure,by_date,day)
        # Mechanical verification of the model's claim, not a separate
        # selection score. Two fact patterns are currently testable.
        pattern=proposal.get("confirmation_pattern")
        if pattern=="CLOSE_ABOVE_PREVIOUS_HIGH":
            check(boundary["field"]=="high" and boundary["date"]<day
                  and current>boundary_price and failure==boundary,
                  "BREAKOUT_FACT_FAILED")
            # A single close above a random old high is not a fresh break.
            between=[r for r in rows if boundary["date"]<r["date"]<day]
            check(len(between)<=20 and all(r["close"]<=boundary_price for r in between),
                  "FRESH_BOUNDARY_FACT_FAILED")
        elif pattern=="TOUCH_SUPPORT_AND_REBOUND":
            check(boundary["field"] in {"high","low","close"} and boundary["date"]<day
                  and failure["field"]=="low" and failure["date"]==day,
                  "PULLBACK_ANCHORS_FAILED")
            # The price must actually test the proposed local level, not
            # a distant unrelated low. ATR is a tolerance, not a buy signal.
            last=rows[-1]
            tr=[max(b["high"]-b["low"],abs(b["high"]-a["close"]),abs(b["low"]-a["close"]))
                for a,b in zip(rows[-15:-1],rows[-14:])]
            atr=sum(tr)/len(tr)
            check(abs(last["low"]-boundary_price)<=.5*atr and current>boundary_price
                  and current>rows[-2]["close"],"REBOUND_FACT_FAILED")
        else:
            raise ValueError("CONFIRMATION_PATTERN_UNSUPPORTED")
        last=rows[-1]
        loc=(last["close"]-last["low"])/(last["high"]-last["low"]) if last["high"]>last["low"] else .5
        check(loc>=.55,"CLOSE_CONFIRMATION_FAILED")
        check(isinstance(proposal.get("entry_trigger"),str) and bool(proposal["entry_trigger"].strip())
              and isinstance(proposal.get("invalidation_rule"),str) and bool(proposal["invalidation_rule"].strip()),
              "PLAN_CONDITIONS_FAILED")
        zone,stop=proposal.get("entry_zone"),proposal.get("invalidation_price")
        check(isinstance(zone,list) and len(zone)==2 and all(positive(x) for x in zone)
              and positive(stop) and stop<zone[0]<=zone[1],"PRICE_ORDER_FAILED")
        check(zone[0]>=boundary_price and zone[1]<=current*(1+MAX_SLIPPAGE_PCT/100)+1e-9,
              "ENTRY_LOCATION_FAILED")
        check(stop<=failure_price*(1-STOP_BUFFER_PCT/100)+1e-9,
              "STOP_ANCHOR_BUFFER_FAILED")
        risk=100*(zone[1]-stop)/zone[1]
        result["audit_proposed_risk_pct"]=round(risk,4)
        check(risk<=RISK_LIMIT_PCT,"STRUCTURAL_RISK_FAILED")
        resistance=nearest_resistance(rows)
        result["audit_resistance"]=resistance
        check(resistance is not None,"OVERHEAD_UNVERIFIED_FAILED")
        reward=(resistance["price"]-zone[1])/(zone[1]-stop)
        result["audit_proposed_reward_R"]=round(reward,4)
        check(reward>=MIN_REWARD_R,"RISK_REWARD_FAILED")
        # Existing chase/repair protections retained solely for research safety.
        ctx=row.get("technical_context") or {}
        ma20=sum(x["close"] for x in rows[-20:])/20
        ma60=sum(x["close"] for x in rows[-60:])/60
        check((current/ma20-1)*100<=MAX_MA20_DISTANCE_PCT and ctx.get("chase_risk") in {"low","medium"},
              "CURRENT_CHASE_GUARD_FAILED")
        check(current>=ma60 and row.get("trend_phase") not in {"FAILED","COOLING","REPAIRING"},
              "CURRENT_PHASE_GUARD_FAILED")
        result.update(status="READY",entry_zone=zone,invalidation_price=stop,
                      initial_risk_pct=round(risk,4),upside_to_resistance_R=round(reward,4),
                      decision_reason="PROPOSED_PLAN_VALIDATED_OFFLINE_ONLY",
                      entry_trigger=proposal["entry_trigger"],invalidation_rule=proposal["invalidation_rule"])
    except (ValueError,TypeError,KeyError) as exc:
        result["decision_reason"]=str(exc)
    return result


def replay(formal,proposals,history_root,theme):
    day=formal["trade_date"]
    if not valid_date(day) or formal.get("status")!="COMPLETE" or formal.get("mode")!="FORMAL":
        raise ValueError("COMPLETE_FROZEN_ARCHIVE_REQUIRED")
    if proposals.get("asof_date")!=day or proposals.get("theme")!=theme:
        raise ValueError("PROPOSAL_SCOPE_DATE_MISMATCH")
    # This first experiment is restricted to a single theme with <=5 frozen
    # eligible names. No use of past model or opportunity rank as input.
    source=[r for r in formal["ready"]+formal["wait"] if r["trend_name"]==theme]
    if not 1<=len(source)<=5 or any(r.get("data_date")!=day for r in source):
        raise ValueError("FROZEN_COHORT_UNSUPPORTED")
    rows={r["code"]:r for r in source}
    picks=proposals["proposals"]
    if (len(rows)!=len(source) or len(picks)!=len(rows)
        or {x["code"] for x in picks}!=set(rows)
        or any(type(x.get("model_rank")) is not int for x in picks)
        or sorted(x["model_rank"] for x in picks)!=list(range(1,len(rows)+1))
        or any(not isinstance(x.get("model_reason"),str) or len(x["model_reason"].strip())<24
               or not isinstance(x.get("setup"),str) for x in picks)):
        raise ValueError("MODEL_SCOPE_OR_RANK_INVALID")
    cache={}
    output=[]
    for proposal in sorted(picks,key=lambda x:x["model_rank"]):
        code=proposal["code"]
        if code[:4] not in cache:
            cache[code[:4]]=read(Path(history_root)/(code[:4]+".json"))
        stock=cache[code[:4]]["stocks"][code]
        bars=history_rows(stock,day,rows[code]["current_price"])
        output.append(validate_plan(proposal,rows[code],bars,day))
    return {"kind":"OFFLINE_MODEL_PROPOSAL_VALIDATION_ONLY","trade_date":day,
            "theme":theme,"model_rank_preserved":True,"production_eligible":False,
            "risk_limits":{"max_risk_pct":RISK_LIMIT_PCT,"min_known_reward_R":MIN_REWARD_R},
            "items":output}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--formal",type=Path,required=True)
    parser.add_argument("--proposals",type=Path,required=True)
    parser.add_argument("--history-root",type=Path,required=True)
    parser.add_argument("--theme",required=True)
    args=parser.parse_args()
    print(json.dumps(replay(read(args.formal),read(args.proposals),args.history_root,args.theme),
                     ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
