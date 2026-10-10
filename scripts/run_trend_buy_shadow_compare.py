#!/usr/bin/env python3
"""Reproduce Oct-09 screening cohort against genuinely completed-session bars.

Retained prior Company Transmission is labelled inherited and never fresh.
This research-only comparison cannot publish production-ready signals.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import trend_buy_engine as engine

def build_research(snapshot):
    day=snapshot.get("trade_date")
    selected=snapshot.get("all_selected")
    if not isinstance(selected,list) or len(selected)!=42 or day!="2026-10-09":
        raise ValueError("shadow_cohort_not_verified")
    codes={r["code"] for r in selected}
    if len(codes)!=42:
        raise ValueError("shadow_cohort_duplicate")
    items=[]
    for x in selected:
        bucket=x["comparison_bucket"]
        state=x["transmission_assessment"]
        direct=state in {"SUPPORTED","EARLY_EVIDENCE"}
        items.append({
            "code":x["code"],"company_name":x["name"],
            "trend_name":("固态电池" if x["industry_code"] in {"S630701","S630702","S630703","S240603","S240504"}
                          else "煤炭" if x["industry_code"] in {"S740101","S740102"} else "黄金/贵金属"),
            "industry_code":x["industry_code"],"asof_price":x["price_2026_10_09"],
            "transmission":state,"theme_link_verified":direct,
            "filter_passed":True,
            "material_risk_unresolved":bucket=="NEW_UNCERTAIN_RISK_REWARD",
            "early_evidence_risk_review_passed":False,
            "source_review":"Oct 9 old formal status INHERITED or Oct 10 initial review; research-only, not a fresh Oct 9 research run.",
            "research_falsifier":"归因业务断裂、趋势失效、经营质量或交易结构被证伪"
        })
    return {"schema_version":"trend_buy_research_v2","mode":"SHADOW_HISTORICAL",
            "trade_date":day,"selected_company_count":42,"coverage_complete":True,
            "completeness_scope":"42 screening results, NOT 42 fresh company qualitative research",
            "companies":items}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--screen-comparison",required=True)
    ap.add_argument("--structure",required=True)
    ap.add_argument("--output",required=True)
    a=ap.parse_args()
    old=json.loads(Path(a.screen_comparison).read_text(encoding="utf-8"))
    m=json.loads(Path(a.structure).read_text(encoding="utf-8"))
    research=build_research(old)
    result=engine.generate(research,m)
    out=Path(a.output).resolve()
    if out.name in {"trend_buy_formal_result.json","trend_buy_handoff.json","latest_formal_result.json","low_risk_handoff.json"}:
        raise ValueError("shadow_cannot_write_formal")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"mode":"SHADOW_HISTORICAL","date":result["trade_date"],"summary":result["summary"],
          "production_eligible":False,"not_fresh_company_research":True},ensure_ascii=False))

if __name__=="__main__":
    main()
