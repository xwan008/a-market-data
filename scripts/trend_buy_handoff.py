#!/usr/bin/env python3
"""Versioned trend-entry handoff projection and semantic validation.

Projects validated READY/WAIT trade plans into a versioned handoff.
Published handoffs require an eligible, completed formal research result.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

WAIT_REASONS={"WAIT_BREAKOUT","WAIT_PULLBACK","WAIT_CONFIRMATION","WAIT_RISK_REWARD"}
SETUPS={"BREAKOUT","PULLBACK"}
PROJECT_FIELDS=(
    "code","company_name","trend_name","industry_code","industry_name","current_price",
    "market_state","trend_state","status","wait_reason","setup_type","entry_zone",
    "entry_trigger","max_entry_price","invalidation_price","invalidation_rule",
    "initial_risk_pct","upside_to_resistance_R","exit_plan","decision_reason",
    "transmission","research_falsifier",
)
ALLOWED_ITEM_FIELDS=set(PROJECT_FIELDS)|{"rank","trade_date"}

def positive(v):
    return type(v) in (int,float) and v>0

def validate_items(handoff):
    if handoff.get("schema_version")!="trend_buy_handoff_v2" or handoff.get("status")!="COMPLETE":
        raise ValueError("trend_handoff_invalid_envelope")
    rows=handoff.get("items")
    if not isinstance(rows,list):
        raise ValueError("trend_handoff_items_invalid")
    seen=set()
    for i,item in enumerate(rows):
        code=str(item.get("code") or "")
        if len(code)!=6 or not code.isdigit() or code in seen:
            raise ValueError("trend_handoff_duplicate_or_invalid_code")
        seen.add(code)
        status,reason=item.get("status"),item.get("wait_reason")
        if status not in ("WAIT","READY"):
            raise ValueError("trend_handoff_invalid_status")
        if status=="READY" and reason is not None:
            raise ValueError("trend_handoff_ready_reason")
        if status=="READY" and item.get("market_state")!="趋势确认":
            raise ValueError("trend_handoff_ready_requires_confirmed_sector")
        if status=="WAIT" and reason not in WAIT_REASONS:
            raise ValueError("trend_handoff_invalid_wait_reason")
        if item.get("rank")!=i+1:
            raise ValueError("trend_handoff_rank_mismatch")
        if item.get("trade_date")!=handoff.get("trade_date"):
            raise ValueError("trend_handoff_date_mismatch")
        if not set(item).issubset(ALLOWED_ITEM_FIELDS):
            raise ValueError("invalid_handoff_item_fields")
        zone=item.get("entry_zone")
        stop=item.get("invalidation_price")
        if zone is not None:
            if not isinstance(zone,list) or len(zone)!=2 or not all(positive(x) for x in zone) or zone[0]>zone[1]:
                raise ValueError("invalid_entry_zone")
            if not positive(item.get("max_entry_price")) or item["max_entry_price"]!=zone[1]:
                raise ValueError("invalid_entry_ceiling")
            if not positive(stop) or stop>=zone[0]:
                raise ValueError("invalid_structure_stop")
            if item.get("setup_type") not in SETUPS:
                raise ValueError("invalid_setup_type")
        if status=="READY" and (zone is None or not item.get("entry_trigger")
                                  or not isinstance(item.get("exit_plan"),dict)
                                  or not isinstance(item.get("invalidation_rule"),str)
                                  or not positive(item.get("initial_risk_pct"))):
            raise ValueError("ready_without_complete_trade_contract")
        if status=="WAIT" and reason!="WAIT_CONFIRMATION" and zone is None:
            raise ValueError("wait_missing_conditional_trade_plan")
    return rows

def project(result, formal_sha, *, shadow=False):
    if result.get("schema_version")!="trend_buy_result_v2" or result.get("status")!="COMPLETE":
        raise ValueError("not_completed_trend_result")
    if result.get("production_eligible") is not True and not shadow:
        raise ValueError("shadow_model_not_promoted")
    if not formal_sha or not isinstance(formal_sha,str):
        raise ValueError("source_blob_sha_required")
    ready=result.get("ready") or []
    wait=result.get("wait") or []
    rows=[]
    for rank,x in enumerate(ready+wait,1):
        rows.append({k:x.get(k) for k in PROJECT_FIELDS}|{"rank":rank,"trade_date":result["trade_date"]})
    payload={
        "schema_version":"trend_buy_handoff_v2","status":"COMPLETE",
        "trade_date":result["trade_date"],
        "source_run_id":result.get("run_id"),
        "source_formal_blob_sha":formal_sha,
        "shadow":shadow,"items":rows
    }
    validate_items(payload)
    return payload

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--result",required=True)
    ap.add_argument("--result-blob-sha",required=True)
    ap.add_argument("--output",required=True)
    ap.add_argument("--shadow",action="store_true")
    args=ap.parse_args()
    inp=Path(args.result).resolve()
    out=Path(args.output).resolve()
    if inp==out:
        raise ValueError("input_and_output_must_differ")
    if not args.shadow and out.name!="trend_buy_handoff.json":
        raise ValueError("formal handoff filename mismatch")
    data=project(json.loads(inp.read_text(encoding="utf-8")),args.result_blob_sha,shadow=args.shadow)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"shadow":args.shadow,"trade_date":data["trade_date"],"count":len(data["items"])}))

if __name__=="__main__":
    main()
