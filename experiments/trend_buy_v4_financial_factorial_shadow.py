#!/usr/bin/env python3
"""Four-way as-of screened candidate experiment; zero new LLM calls.

A0 = exact frozen legacy prescreen Top5 (official sixth tie omitted for budget).
A1 = legacy opportunity/70-30 ranking, ONLY profit evidence source upgraded.
B0 = V4 Python 3+2, old financial score.
B1 = V4 Python 3+2, same upgraded financial score as A1.

New F10 evidence is retrospectively recovered and explicitly labeled as such;
no historical financial expectation or execution performance is asserted.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from copy import deepcopy
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
sys.path.insert(0,str(ROOT/"experiments"))
import build_trend_buy_manual_research as baseline
import trend_buy_v4_python_prescreen_shadow as v4

VERSION="V4_FINANCIAL_2x2_PYTHON_PRESCREEN_SHADOW"
SOURCE="eastmoney_RPT_F10_FINANCE_MAINFINADATA"
CASES=("ORIGINAL_LEGACY","ORIGINAL_CORE_FIRST","V4_LEGACY","V4_CORE_FIRST")


def usable(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)


def validated_patch(company, record, asof, source_asof):
    if not record or record.get("source_report")!=SOURCE:
        return None,"SOURCE_UNKNOWN"
    period=company.get("report_date")
    if not isinstance(period,str) or not period or record.get("report_date")!=period:
        return None,"REPORT_PERIOD_MISMATCH"
    if source_asof<asof:
        return None,"SOURCE_SNAPSHOT_BEFORE_ASOF"
    for key in ("report_date","notice_date","update_date"):
        stamp=record.get(key)
        if key=="update_date" and stamp is None:
            return None,"UPDATE_TIME_NOT_VERIFIED"
        if not isinstance(stamp,str) or stamp>asof:
            return None,"UNDISCLOSED_OR_REVISED_AFTER_ASOF:"+key
    patch={}
    for name in ("deduct_net_profit_yoy","deduct_net_profit",
                 "nonrecurring_profit_share_pct","deduct_basic_eps"):
        if usable(record.get(name)) and not usable(company.get(name)):
            patch[name]=record[name]
    return (patch if patch else None),("VALID_MATCH" if patch else "NO_NEW_VERIFIED_FIELDS")


def run(root, frozen, finance):
    date=frozen.get("trade_date")
    index=v4.read_json(root/"data/low_risk/index.json")
    if not isinstance(date,str) or index.get("trade_date")!=date:
        raise ValueError("screen_and_industry_freeze_mismatch")
    f_asof=finance.get("asof_trade_date")
    if (not isinstance(f_asof,str) or
            not isinstance(finance.get("records"),dict) or
            finance.get("source")!=SOURCE):
        raise ValueError("missing_provenanced_core_financial_snapshot")
    audit=frozen.get("screen_audit") or {}
    scanned=audit.get("lightweight_scanned")
    selected=audit.get("pre_screen_selected")
    if not isinstance(scanned,list) or not isinstance(selected,list):
        raise ValueError("unverified_original_pre_screen_audit")
    by_industry=defaultdict(list)
    original=defaultdict(list)
    for r in scanned:
        by_industry[r["industry_code"]].append(r)
    for r in selected:
        original[r["industry_code"]].append(r["code"])
    previously_rejected={
        r["code"] for r in audit.get("pre_screened_out") or []
        if r.get("reason")=="THEME_NOT_SUPPORTED"
    }
    patched_screen=deepcopy(frozen)
    audit_map={r["code"]:r for r in patched_screen["screen_audit"]["lightweight_scanned"]}
    if len(audit_map)!=len(scanned):
        raise ValueError("duplicate_company_in_original_screen")
    financial_patch_by_code={}
    industry_results=[]
    for industry in sorted(by_industry):
        rows=v4.frozen_industry_rows(root,index,industry,date)
        eligible_by_code={r["code"]:r for r in by_industry[industry]}
        eligible=[r for r in rows if r["code"] in eligible_by_code]
        if len(eligible)!=len(eligible_by_code):
            raise ValueError("hard_eligible_universe_incomplete:"+industry)
        original_scores=baseline.scores(eligible)
        # A0 parity ensures we are comparing the ORIGINAL scoring universe.
        for row,score in zip(eligible,original_scores):
            prior=eligible_by_code[row["code"]]
            if abs(score[0]-prior["fundamental_score"])>1e-6:
                raise ValueError("original_financial_score_parity_failed:"+row["code"])
        patched=[]
        per_industry_patches={}
        audit_reasons=defaultdict(int)
        for company in eligible:
            core=finance["records"].get(company["code"])
            values,reason=validated_patch(company,core,date,f_asof)
            audit_reasons[reason]+=1
            if values:
                per_industry_patches[company["code"]]=values
                financial_patch_by_code[company["code"]]=values
            patched.append({**company,**(values or {})})
        core_scores=baseline.scores(patched,financial_mode="CORE_FIRST")
        changed=[]
        for row,old_score,new_score in zip(eligible,original_scores,core_scores):
            scan=audit_map[row["code"]]
            scan["fundamental_score"]=new_score[0]
            scan["growth"]=new_score[1]
            scan["quality"]=new_score[2]
            scan["valuation_match"]=new_score[3]
            scan["growth_risk"]=new_score[5]
            if scan.get("opportunity") is not None:
                scan["combined_score"]=round(
                    .7*scan["opportunity"]["opportunity_score"]+
                    .3*new_score[0],6)
            if new_score[0]!=old_score[0]:
                changed.append({
                    "code":row["code"],
                    "legacy_fundamental_score":old_score[0],
                    "core_first_fundamental_score":new_score[0],
                    "core_profit_yoy":per_industry_patches.get(
                        row["code"],{}).get("deduct_net_profit_yoy"),
                })
        # A1: same opportunity gate/combined formula, but core-first
        # financial subscore. Keep previously verified NOT_SUPPORTED exclusions.
        eligible_ranked=[audit_map[r["code"]] for r in eligible
                         if audit_map[r["code"]].get("opportunity") is not None
                         and r["code"] not in previously_rejected]
        eligible_ranked.sort(key=lambda r:(-r["combined_score"],r["code"]))
        original_core=[r["code"] for r in eligible_ranked[:5]]
        original_legacy=original[industry][:5]
        original_tie_overflow=original[industry][5:]
        industry_results.append({
            "industry_code":industry,
            "original_company_count":len(rows),
            "hard_eligible_count":len(eligible),
            "core_evidence_patched_count":len(per_industry_patches),
            "source_audit":dict(audit_reasons),
            "fundamental_score_changes":changed,
            "cases":{
                "ORIGINAL_LEGACY":original_legacy,
                "ORIGINAL_CORE_FIRST":original_core},
            "original_research_tie_overflow_not_compared":original_tie_overflow,
        })
    # B0 original V4 and B1 *same* V4 with financial improvements only.
    b0=v4.run(root,frozen,industry_index=index)
    b1=v4.run(root,patched_screen,industry_index=index,
              financial_overlay=financial_patch_by_code)
    b0_by={g["industry_code"]:g for g in b0["industry_groups"]}
    b1_by={g["industry_code"]:g for g in b1["industry_groups"]}
    for item in industry_results:
        code=item["industry_code"]
        old=b0_by[code]["v4_research_codes"]
        new=b1_by[code]["v4_research_codes"]
        item["cases"]["V4_LEGACY"]=old
        item["cases"]["V4_CORE_FIRST"]=new
        item["core_only_change_codes"]=sorted(
            set(item["cases"]["ORIGINAL_CORE_FIRST"])^set(item["cases"]["ORIGINAL_LEGACY"]))
        item["v4_core_change_codes"]=sorted(set(old)^set(new))
        item["v4_candidate_evidence_core"]=b1_by[code]["selected_candidates"]
        item["new_model_review_required_vs_original"]=sorted(
            set(new)-set(item["cases"]["ORIGINAL_LEGACY"]))
        for name,codes in item["cases"].items():
            if len(codes)>5 or len(codes)!=len(set(codes)):
                raise ValueError("model_research_budget_exceeded:"+name+":"+code)
    return {
        "version":VERSION,
        "asof_date":date,
        "source_finance_snapshot_asof":f_asof,
        "source_provenance":SOURCE,
        "source_snapshot_is_retrospective":f_asof>date,
        "mode":"SHADOW_FOUR_WAY_UNREVIEWED_PRESCREEN",
        "arm_definitions":{
            "ORIGINAL_LEGACY":"Published legacy Python score; exact first five",
            "ORIGINAL_CORE_FIRST":"Same legacy 70/30 and opportunity gates; core yoy preferred, noncore share used if verified",
            "V4_LEGACY":"V4 3+2 with legacy fundamental scores",
            "V4_CORE_FIRST":"Same V4 3+2 with identical core-first financial scores",
        },
        "trade_readiness_unchanged":True,
        "model_reviews_executed":0,
        "industry_groups":industry_results,
        "limitations":[
            "As-of-dated present F10 evidence is retrospectively retrieved, NOT an archived independently frozen prior publication",
            "Historical use requires report/notice/update dates at or before original trading day",
            "No price return is available for 2026-11-05 after as-of; not a performance result",
            "Five candidate inclusion and finance score changes are not full company reviews or executable orders",
            "Baseline's published optional sixth near-tie deliberately excluded for equal five-company research budget",
        ]
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=ROOT)
    p.add_argument("--screen",type=Path,required=True)
    p.add_argument("--finance",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    output=args.output.resolve()
    if "shadow" not in str(output).lower() or any(k in str(output)
        for k in ("trend_buy_formal_result","trend_buy_handoff")):
        raise ValueError("shadow_only_output_path_required")
    result=run(args.root.resolve(),v4.read_json(args.screen),
               v4.read_json(args.finance))
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    for group in result["industry_groups"]:
        print("V4_FINANCIAL_FACTORIAL "+json.dumps({
            k:group[k] for k in
            ("industry_code","hard_eligible_count","core_evidence_patched_count",
             "source_audit","cases","core_only_change_codes","v4_core_change_codes",
             "new_model_review_required_vs_original")
        },ensure_ascii=False))
    print("V4_FINANCIAL_2x2_NO_PRODUCTION_PROMOTION")


if __name__=="__main__":
    main()
