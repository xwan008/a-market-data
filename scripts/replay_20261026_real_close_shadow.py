#!/usr/bin/env python3
"""Oct 26 retrospective replay using actual closed-day stored market data.

Never turns post-published registry identity into forged pre-state discovery.
Strict gate is intentionally BLOCKED absent original frozen identity evidence.
Independently recomputes objective SW-code scoped market evidence. No model T
or market-state assigned, and no concept is inferred from price performance.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_mapped_hotspot_market_evidence import summarize
from build_sector_discovery import build
from route_hotspot_themes import is_main_board
from price_inputs import load_momentum_shards


DAY="2026-10-26"


def read(name):
    return json.loads(Path(name).read_text(encoding="utf-8"))


def replay(index, latest, structure, registry, discovery, original_handoff):
    if not (registry.get("trade_date")==latest.get("trade_date")==
            structure.get("reference_trade_date")==DAY):
        raise ValueError("REAL_CLOSE_DATE_INVALID")
    if (latest.get("market_status")!="closed" or
            not (index.get("companies") or {}) or
            not (structure.get("companies") or {})):
        raise ValueError("CLOSE_MARKET_OR_SW_STRUCTURES_MISSING")
    if discovery.get("result_kind")!="sector_discovery_snapshot" or discovery.get("trade_date")!=DAY:
        raise ValueError("ORIGINAL_SECTOR_DISCOVERY_MISSING")
    if original_handoff.get("trade_date")!=DAY:
        raise ValueError("ORIGINAL_TREND_HANDOFF_DATE_MISMATCH")
    if (original_handoff.get("source") or {}).get("identity_verified_before_state") is True:
        raise ValueError("THIS_IS_NOT_A_PRESTATE_IDENTITY_HANDOFF")
    cases=[]
    for index_in_registry,trend in enumerate(registry.get("trends") or []):
        codes=trend.get("industry_codes") or []
        if not codes:
            raise ValueError("UPSTREAM_TREND_WITHOUT_SW_CODES")
        hit={code for code,x in index["companies"].items()
             if (x.get("mapping_status")=="mapped" and
                 x.get("industry_code") in codes and is_main_board(str(code).zfill(6)))}
        if not hit:
            raise ValueError("REAL_UPSTREAM_SW_BASKET_EMPTY")
        cases.append({
            "hotspot_id":"RETROSPECTIVE:"+str(index_in_registry+1),
            "hotspot_name":trend["trend_name"],
            "mapping_status":"VERIFIED",
            # VERIFIED here means the historic SW stock ownership is
            # verified, NOT historic industry-vs-theme type.
            "board_type":"INDUSTRY",
            "board_code":codes[0],
            "industry_codes":codes,
            "driver_kind":"UNKNOWN",
            "basket_scope":"CONDITIONAL_SW_CODE_PROXY_NOT_PRESTATE_IDENTITY",
            "retrospective_as_published_market_state":trend["market_state"],
            "retrospective_as_published_T_stage":trend["trend_state"],
            "market_scope":"SH_SZ_MAINBOARD_ONLY",
        })
    identity={
        "result_kind":"hotspot_identity_snapshot",
        "trade_date":DAY,"market_scope":"SH_SZ_MAINBOARD_ONLY",
        "status":"CONDITIONAL_SCOPED_SW_PROXY_ONLY",
        "identities":cases,
    }
    market=summarize(identity,index,latest,structure)
    # Reference discovery is the stored EXACT 10/26 sector file; it is
    # NOT the original eight independently frozen model discoveries.
    old_metrics={x["id"]:x for x in (read("data/research/sector_discovery_audit.json").get("sectors") or [])}
    evidence=[]
    for case,signal in zip(cases,market["hotspots"]):
        matched_old=[old_metrics.get("industry:"+code) for code in case["industry_codes"]]
        evidence.append({
            "name":case["hotspot_name"],
            "type_proven_as_of_original_freeze":False,
            "conditional_board_type":"INDUSTRY",
            "sw_code_basket":case["industry_codes"],
            "market_status_recomputed_by_model":False,
            "previously_published_market_state":case["retrospective_as_published_market_state"],
            "previously_published_T_stage":case["retrospective_as_published_T_stage"],
            "measured_evidence":signal,
            "original_industry_component_metrics":[
                {k:v for k,v in row.items() if k in (
                    "id","name","member_count","usable_count","median_1d_pct",
                    "advance_ratio","breadth_3d","breadth_5d","median_3d_pct",
                    "median_5d_pct","relative_1d_vs_market_median_pct",
                    "median_volume_ratio_vs_20d")}
                for row in matched_old if row],
        })
    research_candidates=discovery.get("model_research_candidates") or []
    return {
        "schema_version":1,"result_kind":"real_20261026_retrospective_shadow_replay",
        "trade_date":DAY,
        "input_scope":"ORIGINAL_REAL_20261026_CLOSE_3138_MAINBOARD_QUOTES",
        "status":"BLOCKED_BEFORE_FINAL_NEW_RANKING",
        "production_result_modified":False,
        "strict_workflow_gates":{
            "independent_eight_hotspots_frozen_original_record":
                "MISSING_ORIGINAL_FROZEN_RECORD",
            "historical_identity_resolution_before_market_state":
                "NOT_PROVEN_FROM_RECORDED_FILES",
            "historical_concept_member_snapshot_before_market_state":
                "NOT_PROVEN",
            "model_rejudged_market_state_on_verified_identity":
                "NOT_RUN",
            "officially_eligible_new_trend_ranking":"BLOCKED",
            "officially_eligible_new_top5":"BLOCKED",
        },
        "observed_published_trends":evidence,
        "stored_industry_discovery_shortlist":research_candidates[:20],
        "notes":[
            "REAL saved October 26 quotes and current 3d/5d historical structure were used.",
            "Previous trend registry supplies retrospective name/CODE observations ONLY. The original 8 frozen independent candidate identity records are not in repo.",
            "The post-state SW code basket is a CONDITIONAL comparison, NOT proof that the original hotspot was INDUSTRY rather than THEME.",
            "Do not call a returned 10/26 model state freshly recomputed by Python: evidence builder never assigns status.",
            "10/26 humanoid concept code 886069 was known afterward; no original source establishes that generic 工业自动化/机器人 refers to humanoid robot.",
        ],
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",required=True)
    p.add_argument("--structure",default="data/research/full_market_price_structure.json")
    args=p.parse_args()
    original=read("data/research/sector_discovery_snapshot.json")
    report=replay(
        read("data/research/company_industry_index.json"),
        read("data/latest.json"),
        read(args.structure),
        read("research/trend_registry.json"),
        original,
        read("research/trend_handoff.json"))
    dst=Path(args.output)
    dst.parent.mkdir(parents=True,exist_ok=True)
    dst.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print("OCT26_RETROSPECTIVE_REPLAY",json.dumps({
        "status":report["status"],
        "trend_cases":[{"name":x["name"],
            "coverage":x["measured_evidence"].get("quote_coverage"),
            "breadth":x["measured_evidence"].get("r1_advance_ratio"),
            "r3_breadth":x["measured_evidence"].get("r3_breadth"),
            "r5_breadth":x["measured_evidence"].get("r5_breadth"),
            "r1_median":x["measured_evidence"].get("r1_median_pct"),
            "known_state":x["previously_published_market_state"]}
            for x in report["observed_published_trends"]],
        "strict_gates":report["strict_workflow_gates"]
    },ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
