#!/usr/bin/env python3
"""Compute objective market evidence AFTER identity resolution, not trend state.

Model-led 18:30 independent trend research consumes these dated facts and decides
market state using the existing protocol; this program never upgrades/downrates
a state or creates an entry recommendation.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from statistics import median

from route_hotspot_themes import get_return, is_main_board, validate_memberships, read, safe_number

def summarize(identity, index, latest, structure, catalog=None):
    trade_date = identity.get("trade_date")
    if (identity.get("result_kind") != "hotspot_identity_snapshot" or
            latest.get("trade_date") != trade_date or latest.get("market_status") != "closed" or
            structure.get("reference_trade_date") != trade_date or
            identity.get("market_scope") != "SH_SZ_MAINBOARD_ONLY"):
        raise ValueError("MARKET_EVIDENCE_DATE_SCOPE_INVALID")
    companies = index.get("companies") or {}
    stocks = latest.get("stocks") or {}
    structures = structure.get("companies") or {}
    if not companies or not stocks or not structures:
        raise ValueError("MARKET_EVIDENCE_SOURCES_INCOMPLETE")
    concept_by_code = {}
    if catalog is not None:
        if catalog.get("as_of_trade_date") != trade_date:
            raise ValueError("MARKET_EVIDENCE_CONCEPT_ASOF_MISMATCH")
        validate_memberships(catalog, trade_date)
        concept_by_code = {x["concept_id"]: x for x in catalog["concepts"]}
    market_returns = [value for x in stocks.values()
                      if (value := get_return(x)) is not None]
    if not market_returns:
        raise ValueError("NO_VALID_MARKET_RETURN_DATA")
    market_med = median(market_returns)
    out = []
    for entry in identity.get("identities", []):
        evidence = {
            "hotspot_id": entry["hotspot_id"],
            "hotspot_name": entry["hotspot_name"],
            "board_type": entry["board_type"],
            "board_code": entry["board_code"],
            "mapping_status": entry["mapping_status"],
            "driver_kind": entry["driver_kind"],
            "market_state": None,
            "trend_state": None,
            "state_assigned_by_program": False,
            "market_scope": "SH_SZ_MAINBOARD_ONLY",
        }
        if entry["mapping_status"] != "VERIFIED":
            evidence.update({"evaluation_status":"BLOCKED_IDENTITY_UNRESOLVED",
                             "reason":entry["mapping_reason"]})
            out.append(evidence)
            continue
        if entry["board_type"] == "INDUSTRY":
            wanted = set(entry["industry_codes"])
            members = {
                str(code).zfill(6) for code, info in companies.items()
                if is_main_board(str(code).zfill(6)) and
                info.get("mapping_status") == "mapped" and
                info.get("industry_code") in wanted
            }
        else:
            concept = concept_by_code.get(entry["concept_code"])
            if concept is None:
                evidence.update({"evaluation_status":"BLOCKED_CONCEPT_MEMBERSHIP_MISSING"})
                out.append(evidence)
                continue
            members = {c for c in concept["member_codes"] if is_main_board(c)}
        daily = []
        recent = {3:[],5:[]}
        volumes = []
        for code in members:
            q = stocks.get(code) or {}
            value = get_return(q)
            if value is None:
                continue
            daily.append((code,value))
            record = structures.get(code) or {}
            if (record.get("data_status") != "verified" or
                    record.get("data_date") != trade_date):
                continue
            phase = record.get("phase_evidence") or {}
            for window in (3,5):
                v = safe_number(phase.get(f"return_{window}d_pct"))
                if v is not None:
                    recent[window].append((code,v))
            v = safe_number(phase.get("volume_ratio_1d"))
            if v is not None and v > 0:
                volumes.append(v)
        quote_coverage = len(daily)/len(members) if members else 0
        result = {"member_count":len(members),"usable_count":len(daily),
                  "quote_coverage":round(quote_coverage,4),
                  "r1_advance_ratio":round(sum(v>0 for _,v in daily)/len(daily),4)
                                        if daily else None,
                  "r1_median_pct":round(median(v for _,v in daily),3)
                                  if daily else None,
                  "r1_relative_to_market_median_pct":
                    round(median(v for _,v in daily)-market_med,3) if daily else None,
                  "market_median_1d_pct":round(market_med,3),
                  "volume_ratio_median":
                    round(median(volumes),3) if len(volumes)>=max(3,len(daily)//2) else None}
        for window in (3,5):
            usable = len(recent[window])
            ok = usable >= max(3,int(len(daily)*.8))
            result[f"r{window}_usable"] = usable
            result[f"r{window}_breadth"] = (
                round(sum(v>0 for _,v in recent[window])/usable,4) if ok else None)
            result[f"r{window}_median_pct"] = (
                round(median(v for _,v in recent[window]),3) if ok else None)
        evidence.update(result)
        evidence["evaluation_status"] = ("READY_FOR_INDEPENDENT_STATE_REVIEW"
                                          if len(daily)>=5 and quote_coverage>=.95
                                          else "BLOCKED_QUOTE_COVERAGE_INSUFFICIENT")
        out.append(evidence)
    return {"schema_version":1,"result_kind":"mapped_hotspot_market_evidence",
            "trade_date":trade_date,"market_scope":"SH_SZ_MAINBOARD_ONLY",
            "purpose":"Evidence for independent market-state adjudication after identity",
            "may_assign_trend_or_market_state":False,
            "hotspots":out}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--identity",required=True)
    p.add_argument("--industry-index",default="data/research/company_industry_index.json")
    p.add_argument("--latest",default="data/latest.json")
    p.add_argument("--structure",default="data/research/full_market_price_structure.json")
    p.add_argument("--concept-file",default=None)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    result=summarize(read(a.identity),read(a.industry_index),read(a.latest),
                     read(a.structure),read(a.concept_file) if a.concept_file else None)
    target=Path(a.output)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"result":str(target),"status":[(x["hotspot_name"],
                         x["evaluation_status"]) for x in result["hotspots"]]},ensure_ascii=False))


if __name__=="__main__":
    main()
