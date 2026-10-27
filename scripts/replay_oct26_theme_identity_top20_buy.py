#!/usr/bin/env python3
"""Reproduce Oct26 theme identity -> real concept members -> Top20 -> Top5 research.

This is explicitly TWO separate tests:
(A) actual original INDUSTRIAL_AUTOMATION/ROBOT original-hotspot identity
    MUST stay unresolved without a genuine pre-state origin concept index.
(B) exact-match HUMANOID ROBOT 886069 directly specified as a LATE postclose
    standalone WHAT-IF theme, not the originally discovered market hotspot.
Preserves old THS 2026-10-26 archived exact membership (482, mainboard 227);
never fabricates original Oct26 freeze or model re-reviewed market state.
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import resolve_hotspot_identities as resolver
import route_hotspot_themes as router
import build_mapped_hotspot_market_evidence as market
import build_trend_buy_manual_research as research_module
import trend_buy_engine as engine

DAY="2026-10-26"
PREFIX=("600","601","603","605","000","001","002","003")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path,obj):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


def at(source,seconds):
    return (datetime.fromisoformat(source)+timedelta(seconds=seconds)).isoformat()


def exact_history_theme(source,registry,idx,quotes,structure,outdir):
    codes=source["full_member_codes"]
    captured=source["source_captured_at"]
    assert source["concept_index_code"]=="886069"
    assert source["concept_name"]=="人形机器人"
    assert source["trade_date"]==DAY
    assert len(codes)==482
    assert len([c for c in codes if c.startswith(PREFIX)])==227
    assert source["status"]=="STABLE_WITHIN_ONE_TRADING_DAY"
    concept={"schema_version":1,"source":"THS_ADATA",
             "as_of_trade_date":DAY,"source_observed_at":captured,
             "concepts":[{"concept_id":"886069","name":"人形机器人",
                          "source":"THS_ADATA","member_codes":codes}]}
    bases={"schema_version":1,
           "result_kind":"independent_hotspot_discovery_frozen",
           "trade_date":DAY,
           "frozen_at":at(captured,1),
           "discovery_stage":"FROZEN_BEFORE_HISTORICAL_REVIEW"}
    evidence=[{"source":"https://news.10jqka.com.cn/20260928/c680311981.shtml",
               "published_at":"2026-09-28",
               "claim":"THS concept member of exact named 人形机器人 886069; source does not establish original 工业自动化/机器人 hotspot identity."}]
    exact={
        "hotspot_id":"WHATIF_HUMANOID_886069_POSTCLOSE",
        "hotspot_name":"人形机器人",
        "industry_seed_codes":[],
        "representative_codes":[],
        "origin":{"board_type":"THEME","board_code":"886069","source":"THS_ADATA"},
        "driver":{"kind":"TECHNOLOGY_CATALYST","target_board_code":"886069",
                  "sources":evidence}}
    synthetic={**bases,"hotspots":[exact]}
    identity=resolver.resolve(synthetic,registry,concept,idx,
                              resolved_at=at(captured,2))
    save(outdir+"/humanoid_identity.json",identity)
    assert identity["identities"][0]["mapping_status"]=="VERIFIED",identity
    benchmark=market.summarize(identity,idx,quotes,structure,concept)
    save(outdir+"/humanoid_market_evidence.json",benchmark)
    row=benchmark["hotspots"][0]
    assert row["member_count"]==227 and row["usable_count"]>=215
    print("HUMANOID_20261026_SOURCE_METRICS",json.dumps({
        k:row.get(k) for k in ["member_count","usable_count","quote_coverage",
                               "r1_advance_ratio","r1_median_pct",
                               "r3_breadth","r3_median_pct",
                               "r5_breadth","r5_median_pct"]},ensure_ascii=False),flush=True)
    handoff={
        "schema_version":1,"result_kind":"a_share_trend_handoff",
        "trade_date":DAY,
        "generated_at":at(captured,3),
        "source":{"identity_verified_before_state":True,
                  "test_fixture_not_actual_trend_state":True,
                  "origin":"WHATIF_EXACT_HUMANOID_AFTER_REAL_20261026_CLOSE"},
        "signals":[{
            "rank":1,"trend_name":"人形机器人",
            "board_type":"THEME","board_code":"886069",
            "concept_code":"886069",
            "industry_codes":[],
            "trend_state":"T1","market_state":"候选趋势"
        }]
    }
    save(outdir+"/hypothetical_theme_handoff_DO_NOT_PUBLISH.json",handoff)
    route=router.build_verified_routes(handoff,idx,quotes,structure,
                                       identity,concept,cap=20)
    save(outdir+"/humanoid_real_members_top20.json",route)
    one=route["routes"][0]
    assert one["hotspot_type"]=="THEME"
    assert one["concept_member_count"]==482
    assert one["concept_mainboard_member_count"]==227
    assert len(one["candidate_stocks"])==20
    top20=[{"rank":x["rank"],"code":x["stock_code"],
            "name":x["stock_name"],"industry_code":x["industry_code"],
            "opportunity_score":x["opportunity_score"]}
           for x in one["candidate_stocks"]]
    print("HUMANOID_REAL_20261026_TOP20",json.dumps(top20,ensure_ascii=False),flush=True)
    save(outdir+"/humanoid_top20_flat.json",top20)
    research_module.TREND=Path(outdir+"/hypothetical_theme_handoff_DO_NOT_PUBLISH.json")
    research_file=Path(outdir+"/humanoid_real_technical_buy_research.json")
    selected_structure=Path(outdir+"/humanoid_selected_company_structures.json")
    result=research_module.build(
        Path("research/trend_buy_company_reviews/latest.json"),
        structure_path="data/research/full_market_price_structure.json",
        structure_output_path=selected_structure,
        theme_candidates_path=outdir+"/humanoid_real_members_top20.json")
    save(research_file,result)
    final=engine.generate(result,read(selected_structure))
    save(outdir+"/humanoid_technical_buy_engine_result.json",final)
    researched=[{"rank":i+1,"code":x["code"],"name":x["company_name"],
                 "transmission":x["transmission"],
                 "review_basis":x.get("evidence_basis")} for i,x in enumerate(result["companies"])]
    print("HUMANOID_BUY_RESEARCH",json.dumps({
        "mode":result["mode"],"top5_company_research":researched,
        "pending_company_evidence":result["screen_audit"].get("source_review_pending_codes"),
        "final_summary":final["summary"],
        "final_top5_by_theme":[{"theme":x["trend_name"],
            "items":[{"code":y["code"],"name":y["company_name"],
                      "status":y["status"]} for y in x["items"]]}
            for x in final["top5_by_theme"]]},ensure_ascii=False),flush=True)
    return {
        "identity":identity["identities"][0],
        "source_capture":captured,
        "actual_full_members":482,
        "actual_mainboard_members":227,
        "real_market_evidence":row,
        "top20":top20,
        "top5_research_candidates":researched,
        "missing_review_evidence":result["screen_audit"].get("source_review_pending_codes"),
        "final_buy_status_counts":final["summary"],
        "final_engine_top5":final["top5_by_theme"],
        "model_rejudged_status":False,
        "buy_eligible":False,
    }


def unresolved_original(registry,idx,source):
    captured=source["source_captured_at"]
    # Claims come from actual original 2026-10-26 trend registry
    # citing NBS industrial robotics growth, not humanoid market catalysts.
    original={
        "hotspot_id":"ORIGINAL_INDUSTRIAL_AUTOMATION_ROBOT",
        "hotspot_name":"工业自动化/机器人",
        "industry_seed_codes":["S640701","S640702","S640703","S640704"],
        "representative_codes":[],
        "origin":{"board_type":"UNSPECIFIED","board_code":"","source":""},
        "driver":{"kind":"INDUSTRY_ECONOMICS","target_board_code":"",
                  "sources":[{"source":"https://www.stats.gov.cn/sj/zxfb/202610/t20261020_1972579.html",
                              "published_at":"2026-10-20",
                              "claim":"Industrial robots and industrial auto-control output growth; not specific humanoid robotics."}]}
    }
    d={"schema_version":1,"result_kind":"independent_hotspot_discovery_frozen",
       "trade_date":DAY,"frozen_at":at(captured,1),
       "discovery_stage":"FROZEN_BEFORE_HISTORICAL_REVIEW",
       "hotspots":[original]}
    result=resolver.resolve(d,registry,industry_index=idx,resolved_at=at(captured,2))
    item=result["identities"][0]
    assert item["mapping_status"]=="MAPPING_UNRESOLVED",item
    assert item["board_type"] is None
    print("ORIGINAL_HOTSPOT_IDENTITY_CHECK",json.dumps(item,ensure_ascii=False),flush=True)
    return item


def live_general_robot_oct27(quotes,structure):
    # Not an Oct26 point-in-time membership source. Never feed to identity
    # publication gate for historical trend state.
    result={"concept_name":"机器人概念","concept_code":"885517",
            "status":"NOT_CHECKED","member_capture_day":"2026-10-27",
            "historical_asof_membership":"NOT_AVAILABLE",
            "not_a_historical_oct26_result":True}
    try:
        import adata
        import requests
        from concurrent.futures import ThreadPoolExecutor, TimeoutError
        def fetch():
            return adata.stock.info.concept_constituent_ths(index_code="885517")
        with ThreadPoolExecutor(max_workers=1) as pool:
            data=pool.submit(fetch).result(timeout=75)
        codes=sorted(set(str(x).zfill(6) for x in data["stock_code"].tolist()))
        if not codes or any(len(x)!=6 or not x.isdigit() for x in codes):
            raise ValueError("THS_885517_MEMBER_CODE_INVALID")
        provider_n=None
        provider_validation_error=None
        try:
            uri="https://d.10jqka.com.cn/v2/blockrank/885517/8/d15.js"
            http=requests.get(uri,timeout=12,headers={
                "User-Agent":"Mozilla/5.0","Referer":"https://q.10jqka.com.cn/"})
            http.raise_for_status()
            body=http.text
            provider_n=int(json.loads(body[body.find("{"):body.rfind("}")+1])["block"]["subcodeCount"])
        except Exception as ex:
            provider_validation_error=str(ex)[:150]
        mainboard=[c for c in codes if c.startswith(PREFIX)]
        quote_covered=[c for c in mainboard if router.get_return((quotes.get("stocks") or {}).get(c) or {}) is not None]
        result.update({
            "source_observed_at":datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
            "provider_expected_count":provider_n,"actual_returned_count":len(codes),
            "provider_validation_error":provider_validation_error,
            "mainboard_members_from_LIVE_membership":len(mainboard),
            "oct26_quote_coverage_on_oct27_membership":
                round(len(quote_covered)/len(mainboard),4) if mainboard else None,
        })
        valid=[]
        for c in quote_covered:
            opportunity,_=research_module.compact_opportunity(
                (structure.get("companies") or {}).get(c),DAY)
            if opportunity is not None:
                valid.append((opportunity["opportunity_score"],c,
                             (quotes["stocks"].get(c) or {}).get("name")))
        valid.sort(key=lambda x:(-x[0],x[1]))
        result["status"]=(
            "CURRENT_MEMBERSHIP_TECHNICAL_SIMULATION_ONLY"
            if provider_n==len(codes)
            else "CURRENT_CONSTITUENTS_UNVERIFIED_COUNT_SENSITIVITY_ONLY"
        )
        result["non_historical_technical_top20"]=[
            {"rank":i+1,"code":code,"name":name,
             "opportunity_score":round(score,6)}
            for i,(score,code,name) in enumerate(valid[:20])]
    except Exception as ex:
        result["status"]="LIVE_PROVIDER_UNAVAILABLE"
        result["failure"]=str(ex)[:250]
    print("GENERAL_ROBOT_CONCEPT_885517_CHECK",json.dumps(result,ensure_ascii=False),flush=True)
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",required=True)
    p.add_argument("--output-dir",required=True)
    args=p.parse_args()
    out=args.output_dir
    source=read(args.source)
    registry=read("research/hotspot_identity_registry.json")
    idx=read("data/research/company_industry_index.json")
    quotes=read("data/latest.json")
    structure=read("data/research/full_market_price_structure.json")
    assert quotes["trade_date"]==DAY and structure["reference_trade_date"]==DAY
    original=unresolved_original(registry,idx,source)
    exact=exact_history_theme(source,registry,idx,quotes,structure,out)
    robot=live_general_robot_oct27(quotes,structure)
    report={"schema_version":1,"result_kind":"oct26_theme_identity_top20_buy_replay",
            "trade_date":DAY,"scope":"SH_SZ_MAINBOARD_ONLY",
            "original_hotspot_identity":original,
            "original_independent_prestate_frozen_records":"NOT_AVAILABLE",
            "scenario_real_oct26_exact_humanoid_concept":exact,
            "scenario_live_next_day_broader_robot_concept":robot,
            "official_new_theme_top5_status":"NOT_VERIFIED_IDENTITY_AND_FRESH_COMPANY_RESEARCH",
            "no_official_trend_or_buy_publication":True}
    save(out+"/theme_identity_top20_buy_comparison.json",report)


if __name__=="__main__":
    main()
