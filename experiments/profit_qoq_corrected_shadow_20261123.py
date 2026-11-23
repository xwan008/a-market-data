#!/usr/bin/env python3
"""Bounded 'quarter YoY first, REAL profit QoQ secondary' shadow only.

Q/Q is computed from source-verified adjacent Q1/Q2/Q3 cumulative deductible
profits by the sibling read-only probe, not inferred from YoY accelerations.
Weights are EXPERIMENTAL and MUST NOT flow into the formal model or main.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"experiments"))
import profit_yoy_qoq_shadow_20261123 as core
DAY=core.DAY

def factors(report):
    if (report.get("trade_date")!=DAY or report.get("codes")!=38
        or report.get("q3_frozen_mismatches")):
        raise ValueError("qoq_source_incomplete_or_mismatched")
    result={}
    by_status={}
    for r in report["records"]:
        code=r["code"]
        status=r["status"]
        by_status[status]=by_status.get(status,0)+1
        if status=="COMPLETE_POSITIVE_BASE":
            val=r["qoq_pct"]
            if not core.num(val):
                raise ValueError("invalid_positive_base_qoq")
            result[code]=core.clamp((val+100)/200)*2-1 if -100<=val<=100 else (-1 if val<-100 else 1)
            # This is exactly clip(qoq_pct / 100, -1,+1), avoiding huge base effects.
        elif status=="TURNAROUND_FROM_LOSS":
            result[code]=0.5
        elif status=="NON_POSITIVE_Q2_BASE":
            # Two negative quarters: compare improvement in absolute profit,
            # without manufacturing a percentage or equivalent gain rate.
            q2=r.get("profit_q2_yuan")
            q3=r.get("profit_q3_yuan")
            result[code]=.25 if core.num(q2) and core.num(q3) and q3>q2 else -.25
        else:
            raise ValueError("qoq_source_not_complete:"+code+":"+status)
    if len(result)!=38:
        raise ValueError("qoq_38_hard_eligible_coverage_missing")
    return result,by_status

def admission_diff(a,b):
    base={g["industry_code"]:g["research_codes"] for g in a["industry_groups"]}
    out=[]
    for g in b["industry_groups"]:
        code=g["industry_code"];old=base[code];new=g["research_codes"]
        out.append({"industry_code":code,"before":old,"after":new,
                    "added":sorted(set(new)-set(old)),
                    "removed":sorted(set(old)-set(new))})
    return out

def attention_corrected(attention, factors):
    new=[]
    total_changes=0
    for theme in attention:
        original=theme["items"]
        items=[]
        for r in original:
            factor=factors[r["code"]]
            # Existing opportunity model: research-quality score is 15%.
            # QoQ correction changes quality by max +/-5 points, hence max
            # +/-0.75 total opportunity-score points; not BUY permission.
            score=round(r["shadow_score"]+ .15*5*factor,4)
            items.append({**r,"qoq_direction_factor":round(factor,4),
                          "qoq_corrected_score":score})
        sorted_items=sorted(items,key=lambda x:(
            0 if x["status"]=="READY" else 1,-x["qoq_corrected_score"],x["code"]))
        for i,r in enumerate(sorted_items,1):
            r["qoq_corrected_rank"]=i
            total_changes+=(r["qoq_corrected_rank"]!=r["original_rank"])
        new.append({"theme":theme["theme"],
                    "original_order":theme["old_order"],
                    "quarter_yoy_order":theme["shadow_order"],
                    "quarter_yoy_plus_qoq_order":[x["code"] for x in sorted_items],
                    "items":sorted(items,key=lambda x:x["original_rank"])})
    return new,total_changes

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--qoq-source",required=True)
    p.add_argument("--output",default="/tmp/profit_yoy_qoq_corrected_shadow_20261123.json")
    args=p.parse_args()
    output=Path(args.output).resolve()
    if ROOT.resolve() in output.parents or output==ROOT.resolve():
        raise ValueError("SHADOW_REPO_WRITE_FORBIDDEN")
    qoq=core.read(args.qoq_source)
    factor,coverage=factors(qoq)
    idx=core.read(ROOT/"data/low_risk/index.json")
    fin=core.read(ROOT/"data/research/core_profit_refresh_latest.json")
    official=core.read(ROOT/"research/trend_buy_formal_result.json")
    admission=core.read(ROOT/"research/trend_buy_candidates/latest.json")
    original=core.admission.prepare(ROOT)
    if admission["industries"]!=original["industries"]:
        raise ValueError("BASELINE_ADMISSION_REPLAY_FAILED")
    same_quarter_yoy,coverage_fin,_=core.shadow_admission(idx,fin)
    with_real_qoq,coverage_fin2,_=core.shadow_admission(idx,fin,qoq_factors=factor)
    old_by={g["industry_code"]:g["selected_codes"] for g in original["industries"]}
    before=[]
    for r in same_quarter_yoy["industry_groups"]:
        original_codes=old_by[r["industry_code"]]
        before.append({"industry_code":r["industry_code"],
                       "original":original_codes,
                       "quarter_yoy":r["research_codes"],
                       "added":sorted(set(r["research_codes"])-set(original_codes)),
                       "removed":sorted(set(original_codes)-set(r["research_codes"]))})
    att, _=core.attention_shadow(official,fin)
    corrected,changes=attention_corrected(att,factor)
    result={
        "mode":"SHADOW_Q_YOY_PRIMARY_REAL_QOQ_BOUNDED_CORRECTION",
        "trade_date":DAY,"finance_asof":fin["asof_trade_date"],
        "qoq_source_status_counts":coverage,
        "quarter_yoy_source_coverage":coverage_fin,
        "quarter_yoy_only_vs_official":before,
        "qoq_corrected_vs_quarter_yoy":admission_diff(same_quarter_yoy,with_real_qoq),
        "attention_sensitivity":corrected,
        "qoq_corrected_rank_changes_vs_official":changes,
        "provisional_parameters":{
            "candidate_financial_score_qoq_bump_max":0.05,
            "candidate_entry_score_qoq_bump_max":0.0075,
            "attention_total_score_qoq_bump_max":0.75,
            "qoq_positive_base_clip_pct":[-100,100],
            "loss_to_profit_factor":0.5,
            "two_loss_quarters_direction_only_factor":0.25
        },
        "qoq_primary_data_source":"F10_asof_2026-11-23_Q1_Q2_Q3_cumulative_core_profit",
        "price_inputs_unmodified":True,
        "official_ready_wait_not_recomputed":True,
        "no_main_write":True,
        "no_trade_authorization":True,
        "warning":"One day, provisional weights, subject to seasonality/low base; compare outcomes before adoption."
    }
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("REAL_QOQ_CORRECTED_SHADOW",json.dumps({
        "qoq_coverage":coverage,
        "quarter_yoy_only_vs_official":before,
        "qoq_corrected_vs_quarter_yoy":result["qoq_corrected_vs_quarter_yoy"],
        "ranking":{x["theme"]:{
                    "original":x["original_order"],
                    "q_yoy":x["quarter_yoy_order"],
                    "q_yoy_qoq":x["quarter_yoy_plus_qoq_order"]}
                   for x in corrected},
        "changed_rank_vs_official":changes,
    },ensure_ascii=False))

if __name__=="__main__":
    main()
