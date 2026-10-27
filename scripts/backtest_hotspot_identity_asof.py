#!/usr/bin/env python3
"""14-session immutable-SHA industry path replay for PR#60 (NO live concepts).

REAL: use each dated quote/industry snapshot + 3/5d prior snapshot-only values.
CONTRACT TEST: board_type INDUSTRY -> code-only routing without trend mutation.
NOT TESTED: historical full concept members, independent discovery drivers,
model-assigned candidate/confirmed market states, company Top5 executions.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

from backtest_sector_discovery_asof import asof_features, load, load_days, replay
from build_sector_discovery import build as old_discovery
from build_mapped_hotspot_market_evidence import summarize as mapped_evidence
from route_hotspot_themes import build_verified_routes


def digest(obj):
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def sector_identity(day, sector_rows):
    """An as-of SW index *identity fixture*; not an independent discovery."""
    return {
        "schema_version": 1,
        "result_kind": "hotspot_identity_snapshot",
        "trade_date": day, "market_scope": "SH_SZ_MAINBOARD_ONLY",
        "status": "COMPLETE",
        "proof_scope": "ASOF_SW_MEMBERSHIP_IDENTITY_ONLY_NOT_FROZEN_ORIGINAL_DRIVER",
        "identities": [
            {"hotspot_id": row["id"],"hotspot_name": row["name"],
             "board_type": "INDUSTRY", "board_code": row["id"].split(":",1)[1],
             "industry_codes": [row["id"].split(":",1)[1]],
             "mapping_status": "VERIFIED",
             "driver_kind": "UNKNOWN"}
            for row in sector_rows
        ]
    }


def industry_quote_parity(old_rows, market_rows):
    mapped = {x["hotspot_id"]: x for x in market_rows}
    errors, covered, checked = [], [], 0
    for old in old_rows:
        new = mapped.get(old["id"])
        if new is None:
            errors.append({"id": old["id"], "field": "missing_identity"})
            continue
        checked += 1
        for old_key, new_key, tolerance in [
            ("member_count","member_count",0),
            ("usable_count","usable_count",0),
            ("coverage","quote_coverage",0.00011),
            ("advance_ratio","r1_advance_ratio",0.00011),
            ("median_1d_pct","r1_median_pct",0.0011),
        ]:
            a,b = old.get(old_key), new.get(new_key)
            if a is None and b is None:
                continue
            if a is None or b is None or abs(float(a)-float(b)) > tolerance:
                errors.append({"id":old["id"],"field":old_key,
                               "old":a,"new":b})
        covered.append(new["evaluation_status"])
    return {"old_sector_count":len(old_rows), "new_sector_count":checked,
            "mismatch_count":len(errors), "mismatch_examples":errors[:16],
            "status_counts":dict(Counter(covered))}


def routing_contract(day, industry, latest, structure, identity):
    """Use the same handoff fields as post-state; fake status is *test-only*.

    It verifies only that identity/routing copies a code and doesn't add
    company members or upgrade the phase. It does not validate model decisions.
    """
    rows = identity["identities"]
    if not rows:
        raise ValueError("NO_ASOF_INDUSTRIES")
    stamp=day+"T18:30:30+08:00"
    sample=rows[:min(len(rows),20)]
    snapshot={**identity,"resolved_at":stamp}
    handoff={
        "result_kind":"a_share_trend_handoff","trade_date":day,
        "generated_at":day+"T18:35:00+08:00",
        "source":{"identity_verified_before_state":True,
                  "test_fixture_not_actual_formal_state":True},
        "signals":[
            {"rank":i,"trend_name":entry["hotspot_name"],
             "board_type":"INDUSTRY","board_code":entry["board_code"],
             "industry_codes":entry["industry_codes"],
             "trend_state":"T1","market_state":"候选趋势"}
            for i,entry in enumerate(sample,1)]
    }
    result=build_verified_routes(handoff,industry,latest,structure,snapshot)
    if len(result["routes"])!=len(sample):
        raise AssertionError("INDUSTRY_ROUTING_COUNT_CHANGED")
    for input_,output in zip(handoff["signals"],result["routes"]):
        if (output["hotspot_type"]!="INDUSTRY" or output["candidate_stocks"] or
                output["industry_codes"]!=input_["industry_codes"] or
                output["trend_state"]!=input_["trend_state"] or
                output["market_state"]!=input_["market_state"] or
                output["board_code"]!=input_["board_code"]):
            raise AssertionError("INDUSTRY_ROUTING_PARITY_FAILED")
    return {"sampled_industries":len(sample),
            "result":"CODE_ONLY_NO_NEW_MEMBERS_NO_STATE_CHANGE"}


def single_day(days,index):
    day,sha,latest,industry=days[index]
    structure=asof_features(days,index)
    old,old_audit=old_discovery(latest,industry,structure,review_cap=20)
    old_rows=[r for r in old_audit["sectors"] if r["kind"]=="industry"]
    identity=sector_identity(day,old_rows)
    evidence=mapped_evidence(identity,industry,latest,structure)
    parity=industry_quote_parity(old_rows,evidence["hotspots"])
    routed=routing_contract(day,industry,latest,structure,identity)
    return {
        "date":day,"commit":sha,
        "identity_basis":"ASOF_SW_MEMBER_INDEX_ONLY",
        "original_discovery_eligible":old_audit["eligible_count"],
        "original_discovery_selected":old_audit["selected_count"],
        "quote_parity":parity,
        "routing_contract":routed,
        "identity_count":len(identity["identities"]),
        "market_evidence_consumer_was_inert":all(
            x["trend_state"] is None and x["market_state"] is None
            for x in evidence["hotspots"]),
        "asof_input_hash":digest({"latest":latest,"industry":industry}),
        "observable_market_evidence_hash":digest(evidence["hotspots"]),
        "routing_output_hash":digest(routed),
    }


def replay_identity_layer(root,manifest, repeat=True):
    days=load_days(root,manifest)
    rows=[single_day(days,i) for i in range(len(days))]
    repeats=[single_day(days,i) for i in range(len(days))] if repeat else []
    if repeats:
        for a,b in zip(rows,repeats):
            if a!=b:
                raise AssertionError("NON_DETERMINISTIC_REPLAY:"+a["date"])
    # Negative controls: forward-day *prices* MUST never reach signal calculations.
    if len(days)>=8:
        start_i=len(days)-2
        previous=single_day(days,start_i)
        poisoned=copy.deepcopy(days)
        if poisoned[start_i+1][2]["stocks"]:
            for quote in poisoned[start_i+1][2]["stocks"].values():
                quote["price"]=9999999
                quote["change_pct"]=99
        previous_again=single_day(poisoned,start_i)
        if previous!=previous_again:
            raise AssertionError("FUTURE_DATA_LEAKAGE_IN_PRIOR_DAY")
    total=sum(x["quote_parity"]["old_sector_count"] for x in rows)
    mismatch=sum(x["quote_parity"]["mismatch_count"] for x in rows)
    route_total=sum(x["routing_contract"]["sampled_industries"] for x in rows)
    return {
        "schema_version":1, "result_kind":"identity_first_industry_asof_replay",
        "dates":[days[0][0],days[-1][0]],"sessions":len(days),
        "scope":"SH_SZ_MAINBOARD_ONLY",
        "historical_source":"DAY_EXACT_IMMUTABLE_GIT_COMMIT",
        "historical_concept_membership_available":False,
        "historical_original_model_discovery_available":False,
        "historical_independent_driver_evidence_available":False,
        "historical_candidate_confirmed_state_reproduced":False,
        "market_state_inferred_by_python":False,
        "forward_data_mutation_test":"PASSED" if len(days)>=8 else "NOT_RUN",
        "identical_second_run":"PASSED" if repeat else "NOT_RUN",
        "sector_observations":total,
        "mismatched_original_vs_new_market_quote_metrics":mismatch,
        "industry_code_only_routes_tested":route_total,
        "by_day":rows,
        "limitations":[
            "The original model discovery identity, original driver/catalyst and official 18:30 adjudication records were NOT recreated.",
            "We replay genuine as-of SW membership only; routing status T1/candidate inside isolated contract test is synthetic and NOT a historical signal.",
            "Historical point-in-time concept membership is unavailable; do not use the current 886069 membership for earlier dates.",
            "This does not evaluate verified theme detection, historical theme Top20/Top5, or newly determined market confirmation.",
        ],
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",required=True)
    p.add_argument("--manifest",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--legacy-output",required=True)
    args=p.parse_args()
    manifest=load(args.manifest)
    report=replay_identity_layer(args.root,manifest)
    legacy=replay(args.root,manifest,horizon=2)
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    Path(args.legacy_output).write_text(json.dumps(legacy,ensure_ascii=False,indent=2)+"\n")
    print("IDENTITY_ASOF_REPLAY_RESULT",json.dumps({
        k:report[k] for k in ("sessions","sector_observations",
            "mismatched_original_vs_new_market_quote_metrics",
            "industry_code_only_routes_tested","identical_second_run",
            "forward_data_mutation_test","historical_concept_membership_available",
            "historical_candidate_confirmed_state_reproduced")},ensure_ascii=False),flush=True)
    print("ORIGINAL_REPLAY_FORWARD_OUTCOMES",json.dumps(legacy["summary"],
                                                      ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
