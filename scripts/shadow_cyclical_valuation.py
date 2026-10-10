#!/usr/bin/env python3
"""Independent, fail-closed CYCLICAL PB/ROE shadow sensitivity.

Not a production buy-point model. Never touches formal data/handoff.
Requires reported attributable equity and issued shares from dated filing.
Discount rate and terminal growth are HYPOTHESES, not researched prices.
"""
from __future__ import annotations
import argparse
import json
import math
from datetime import date
from pathlib import Path


def num(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
def pos(v):
    return num(v) and v>0
def day(s):
    return date.fromisoformat(s).isoformat()

def run(payload):
    if payload.get("model")!="CYCLICAL_PB_ROE_SHADOW_V1":
        raise ValueError("unsupported model")
    asof=day(payload["as_of_date"])
    companies=payload.get("companies")
    if not isinstance(companies,list) or not companies:
        raise ValueError("companies required")
    results=[]
    seen=set()
    for co in companies:
        code=str(co.get("code") or "")
        if not code or code in seen:
            raise ValueError("invalid/duplicate code")
        seen.add(code)
        result={"code":code,"name":co.get("name"),"original_formal_status":co.get("formal_status"),
                "status":"INSUFFICIENT_EVIDENCE","flags":[],"book_value_per_share":None,
                "implied_pb_at_current_price":None,"market_implied_sustainable_roe":None,
                "forward_scenario_value":None,"source":co.get("source"),
                "note":"Conditional Gordon P/B sensitivity, not formal fair value or a buy signal."}
        results.append(result)
        try:
            if day(co.get("price_date"))!=asof or not pos(co.get("current_price")):
                result["flags"].append("PRICE_DATE_MISMATCH");continue
            source=co.get("source") or {}
            if day(source.get("published_at"))>asof or day(source.get("report_date"))>asof:
                result["flags"].append("FUTURE_SOURCE");continue
            if not (isinstance(source.get("url"),str) and source["url"].startswith(("https://","http://"))):
                result["flags"].append("NO_SOURCE");continue
            eq=co.get("attributable_equity"),shares=co.get("issued_shares")
            if not pos(eq) or not pos(shares):
                result["flags"].append("BOOK_VALUE_MISSING");continue
            bvps=eq/shares
            result["book_value_per_share"]=round(bvps,6)
            result["implied_pb_at_current_price"]=round(co["current_price"]/bvps,6)
        except (TypeError,ValueError):
            result["flags"].append("INVALID_DATE");continue
        ass=co.get("assumptions") or {}
        r,g=ass.get("required_return"),ass.get("long_term_growth")
        if not(num(r) and num(g) and 0<r<.5 and -0.1<=g<r):
            result["flags"].append("MISSING_CONDITIONAL_ASSUMPTIONS");continue
        # Justified P/B=(ROE-g)/(r-g); assumes steady state and consistent
        # payout/reinvestment. If terminal book value unknown, no price target.
        implied= g + (co["current_price"]/bvps)*(r-g)
        result["market_implied_sustainable_roe"]={
            "status":"CONDITIONAL_ONLY","roe_fraction":round(implied,6),
            "required_return":r,"long_term_growth":g,
            "assumptions":"steady-state justified P/B; risk/capital/payout assumptions unverified"
        }
        scenarios=co.get("scenarios")
        if scenarios is None:
            result["status"]="CONDITIONAL_SENSITIVITY_ONLY";continue
        if not isinstance(scenarios,list) or len(scenarios)!=3 or {v.get("kind") for v in scenarios if isinstance(v,dict)}!={"bear","base","bull"}:
            result["flags"].append("INVALID_SCENARIOS");continue
        weights=[c.get("probability") for c in scenarios]
        if not all(num(p) and 0<=p<=1 for p in weights) or abs(sum(weights)-1)>1e-9:
            result["flags"].append("INVALID_PROBABILITIES");continue
        horizon=ass.get("horizon_years")
        if not num(horizon) or not .25<=horizon<=5:
            result["flags"].append("INVALID_HORIZON");continue
        vals=[]
        for c in scenarios:
            roe,bv=c.get("forward_roe"),c.get("forward_bvps")
            ev=c.get("evidence") or []
            if not (num(roe) and g<=roe<.5 and pos(bv) and isinstance(ev,list)
                    and ev and all(isinstance(e.get("url"),str) and e["url"].startswith(("https://","http://"))
                     and day(e["published_at"])<=asof for e in ev)
                    and isinstance(c.get("assumption_rationale"),str) and len(c["assumption_rationale"])>=12
                    and isinstance(c.get("falsifier"),str) and len(c["falsifier"])>=6):
                result["flags"].append("SCENARIO_EVIDENCE_INCOMPLETE");break
            terminal_pb=(roe-g)/(r-g)
            # no dividend credited: conservative conditional analytical output,
            # not a claim that dividends are zero. Analysts must audit payout.
            vals.append({"kind":c["kind"],"probability":c["probability"],
                         "terminal_pb":round(terminal_pb,5),
                         "discounted_value_ex_dividends":round(bv*terminal_pb/(1+r)**horizon,4)})
        if len(vals)==3:
            result["forward_scenario_value"]={
                "status":"ASSUMPTION_SENSITIVITY_NOT_APPROVED",
                "cases":vals,
                "expected_value_ex_dividends":round(sum(v["discounted_value_ex_dividends"]*v["probability"] for v in vals),4),
                "warning":"Justified P/B steady-state, forward book value, payout and scenario ROE unverified. Not a price recommendation."
            }
            result["status"]="SCENARIO_ASSUMPTIONS_TO_VERIFY"
    return {"model":"CYCLICAL_PB_ROE_SHADOW_V1","production_effect":"NONE","as_of_date":asof,
            "companies":results}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",required=True)
    ap.add_argument("--output",required=True)
    args=ap.parse_args()
    src=Path(args.input).resolve()
    dst=Path(args.output).resolve()
    if src==dst or dst.name in {"latest_formal_result.json","low_risk_handoff.json","trend_handoff.json"}:
        raise ValueError("refusing write to formal dataset")
    out=run(json.loads(src.read_text(encoding="utf-8")))
    dst.parent.mkdir(parents=True,exist_ok=True)
    dst.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"production_effect":"NONE","company_count":len(out["companies"]),"output":str(dst)}))

if __name__=="__main__":
    main()
