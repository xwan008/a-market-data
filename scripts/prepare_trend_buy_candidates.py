#!/usr/bin/env python3
"""正式 single-mainline company research admission: program BEFORE model.

Only frozen same-day confirmed SW3 industries, hard filtering and 65-bar
momentum. Produces <= 5 names per industry, for NEW same-day model review.
Never selects from earlier published Top5 and never grants READY.
"""
from __future__ import annotations
from datetime import date
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import build_trend_buy_manual_research as scanner
import trend_buy_prescreen_core as prescreen


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


F10_SOURCE="eastmoney_RPT_F10_FINANCE_MAINFINADATA"

def usable(value):
    import math
    return (isinstance(value,(int,float)) and not isinstance(value,bool)
            and math.isfinite(value))

def validated_core_patch(company, record,asof):
    if not isinstance(record,dict) or record.get("source_report")!=F10_SOURCE:
        return {}, "FINANCE_SOURCE_UNKNOWN"
    period=company.get("report_date")
    if not isinstance(period,str) or period!=record.get("report_date"):
        return {}, "FINANCE_REPORT_PERIOD_MISMATCH"
    for name in ("report_date","notice_date","update_date"):
        value=record.get(name)
        if not isinstance(value,str) or not value or value>asof:
            return {}, "FINANCE_NOT_AVAILABLE_ASOF:"+name
    patch={}
    for key in ("deduct_net_profit_yoy","deduct_net_profit",
                "nonrecurring_profit_share_pct","deduct_basic_eps"):
        if usable(record.get(key)) and not usable(company.get(key)):
            patch[key]=record[key]
    acceleration=validated_quarterly_acceleration(record,period,asof)
    if acceleration is not None:
        patch["quarterly_acceleration"]=acceleration
    return patch,"VALIDATED" if patch else "NO_NEW_FIELDS"

def previous_quarter_period(report_date):
    try:
        y,m,d=map(int,report_date[:10].split("-"))
    except (TypeError,ValueError):
        return None
    if (m,d)==(3,31):
        return f"{y-1}-12-31"
    if (m,d)==(6,30):
        return f"{y}-03-31"
    if (m,d)==(9,30):
        return f"{y}-06-30"
    if (m,d)==(12,31):
        return f"{y}-09-30"
    return None


def validated_quarterly_acceleration(record, period, asof):
    accel=record.get("quarterly_acceleration") if isinstance(record,dict) else None
    if not isinstance(accel,dict) or accel.get("status")!="VERIFIED":
        return None
    if accel.get("source_report")!=F10_SOURCE:
        return None
    if accel.get("latest_report_date")!=period:
        return None
    if accel.get("previous_report_date")!=previous_quarter_period(period):
        return None
    for key in (
        "latest_report_date","latest_notice_date","latest_update_date",
        "previous_report_date","previous_notice_date","previous_update_date",
    ):
        value=accel.get(key)
        if not isinstance(value,str) or not value or value>asof:
            return None
    numeric=(
        "latest_single_quarter_deduct_profit_yoy_pct",
        "previous_single_quarter_deduct_profit_yoy_pct",
        "latest_single_quarter_revenue_yoy_pct",
        "previous_single_quarter_revenue_yoy_pct",
        "deduct_profit_acceleration_pp",
        "revenue_acceleration_pp",
    )
    if not all(usable(accel.get(key)) for key in numeric):
        return None
    return accel


def quarterly_acceleration_shadow_scores(rows, base_metrics):
    """Small, bounded shadow adjustment; never used by the formal selection."""
    valid=[]
    for row in rows:
        accel=row.get("quarterly_acceleration") or {}
        if (accel.get("status")=="VERIFIED"
                and usable(accel.get("deduct_profit_acceleration_pp"))
                and usable(accel.get("latest_single_quarter_deduct_profit_yoy_pct"))
                and usable(accel.get("latest_single_quarter_revenue_yoy_pct"))
                and usable(accel.get("revenue_acceleration_pp"))):
            valid.append(accel)
        else:
            valid.append(None)
    available=sum(item is not None for item in valid)
    coverage=available/len(rows) if rows else 0.0
    if len(rows)<3:
        reason="INSUFFICIENT_PEER_SAMPLE"
    elif coverage<0.75:
        reason="INSUFFICIENT_FINANCIAL_ACCELERATION_COVERAGE"
    else:
        reason="SHADOW_RULE_ACTIVE"
    activated=reason=="SHADOW_RULE_ACTIVE"
    ranks=scanner.percentile([
        item["deduct_profit_acceleration_pp"] if item else None
        for item in valid
    ]) if activated else [.5]*len(rows)
    shadow_metrics=[]
    company_audit=[]
    for i,(row,base,accel) in enumerate(zip(rows,base_metrics,valid)):
        base_score,base_growth,quality,attraction,trend,abnormal=base
        if not activated:
            shadow=base
            accel_quality=None
        elif accel is None:
            accel_quality=.5
            shadow_growth=.8*base_growth+.2*accel_quality
            shadow_score=max(0.0,min(1.0,base_score+.45*(shadow_growth-base_growth)))
            shadow=(round(shadow_score,6),round(shadow_growth,5),
                    quality,attraction,trend,abnormal)
        else:
            profit_accel=accel["deduct_profit_acceleration_pp"]
            latest_profit=accel["latest_single_quarter_deduct_profit_yoy_pct"]
            latest_revenue=accel["latest_single_quarter_revenue_yoy_pct"]
            revenue_accel=accel["revenue_acceleration_pp"]
            rank=ranks[i]
            if profit_accel>0 and latest_profit>0:
                profit_score=.5+.5*rank
            elif profit_accel>0:
                # A loss-to-less-loss repair is positive evidence, but not
                # equivalent to acceleration into positive earnings growth.
                profit_score=.5+.25*rank
            elif latest_profit>0:
                profit_score=.5*rank
            else:
                profit_score=.25*rank
            if latest_revenue>=0 and revenue_accel>=0:
                revenue_match=1.0
            elif latest_revenue>=0:
                revenue_match=.75
            elif revenue_accel>0:
                revenue_match=.5
            else:
                revenue_match=.25
            accel_quality=.7*profit_score+.3*revenue_match
            shadow_growth=.8*base_growth+.2*accel_quality
            shadow_score=max(0.0,min(1.0,base_score+.45*(shadow_growth-base_growth)))
            shadow=(round(shadow_score,6),round(shadow_growth,5),
                    quality,attraction,trend,abnormal)
        shadow_metrics.append(shadow)
        company_audit.append({
            "code":row.get("code"),
            "quarterly_acceleration_status":
                (accel or {}).get("status","UNKNOWN"),
            "deduct_profit_acceleration_pp":
                (accel or {}).get("deduct_profit_acceleration_pp"),
            "revenue_acceleration_pp":
                (accel or {}).get("revenue_acceleration_pp"),
            "revenue_alignment":(accel or {}).get("revenue_alignment","UNKNOWN"),
            "base_fundamental_score":base_score,
            "shadow_fundamental_score":shadow[0],
            "shadow_acceleration_quality":accel_quality,
        })
    return shadow_metrics,{
        "activated":activated,
        "reason":reason,
        "eligible_count":len(rows),
        "available_count":available,
        "coverage_ratio":round(coverage,4),
        "weight_within_growth_dimension":0.20,
        "max_total_score_impact":0.09,
        "companies":company_audit,
    }


def validate_financial_source(finance, day):
    stamp=finance.get("asof_trade_date")
    if (finance.get("source")!=F10_SOURCE or not isinstance(stamp,str)
            or not isinstance(finance.get("records"),dict)):
        raise ValueError("ADMISSION_F10_PROVENANCE_MISSING")
    delta=(date.fromisoformat(day)-date.fromisoformat(stamp)).days
    if not 0<=delta<=14:
        raise ValueError("ADMISSION_F10_SOURCE_DATE_NOT_VALID_FOR_CURRENT_SIGNAL")
    return stamp

def prepare(root=ROOT):
    """One frozen deterministic prescreen before model research."""
    from collections import defaultdict
    from copy import deepcopy
    trend=read(root/"research/trend_handoff.json")
    index=read(root/"data/low_risk/index.json")
    day=trend.get("trade_date")
    if not isinstance(day,str) or index.get("trade_date")!=day:
        raise ValueError("ADMISSION_ASOF_INPUT_MISMATCH")
    if not trend.get("signals"):
        raise ValueError("ADMISSION_NO_UPSTREAM_CONFIRMED_SW3")
    finance_path=root/"data/research/core_profit_refresh_latest.json"
    finance=read(finance_path)
    finance_stamp=validate_financial_source(finance,day)
    with tempfile.TemporaryDirectory(prefix="trend-prescreen-") as work:
        empty=Path(work)/"empty_reviews.json"
        empty.write_text(json.dumps({
            "schema_version":"trend_buy_company_reviews_v2",
            "as_of_date":day,
            "reviews":[],
        },ensure_ascii=False),encoding="utf-8")
        # Existing hard-filter and compact opportunity calculators are reused
        # solely for cheap full-universe audit, NOT for a second publication.
        lightweight=scanner.build(empty,audit_only=True)
    if (lightweight["mode"]!="AUDIT_ONLY" or
            not lightweight["screen_audit"]["hard_eligible"]):
        raise ValueError("ADMISSION_PRE_RESEARCH_FAILED_CLOSED")
    scan=deepcopy(lightweight)
    shadow_scan=deepcopy(lightweight)
    audited=scan["screen_audit"]["lightweight_scanned"]
    scan_by_code={row["code"]:row for row in audited}
    shadow_by_code={
        row["code"]:row for row in shadow_scan["screen_audit"]["lightweight_scanned"]
    }
    if len(scan_by_code)!=len(audited):
        raise ValueError("ADMISSION_SCANNED_DUPLICATE_COMPANY")
    industries=defaultdict(list)
    for row in audited:
        industries[row["industry_code"]].append(row["code"])
    validated_overlay={}
    evidence_counts={}
    acceleration_evaluations={}
    for industry,codes in industries.items():
        frozen=prescreen.frozen_industry_rows(root,index,industry,day)
        eligible=set(codes)
        peer_rows=[row for row in frozen if row["code"] in eligible]
        if len(peer_rows)!=len(codes):
            raise ValueError("ADMISSION_HARD_ELIGIBLE_FROZEN_SCOPE_MISMATCH")
        patched=[]
        count=0
        for row in peer_rows:
            patch,reason=validated_core_patch(
                row,finance["records"].get(row["code"]),day)
            # Report period, announcement/update date and source all matched.
            # This flag describes provenance, not a claim of earnings quality.
            if reason in ("VALIDATED","NO_NEW_FIELDS"):
                patch={**patch,"financial_publication_date_verified":True}
                count+=1
            if patch:
                validated_overlay[row["code"]]=patch
            patched.append({**row,**patch})
        evidence_counts[industry]=count
        base_metrics=scanner.scores(patched,financial_mode="CORE_FIRST")
        shadow_metrics,acceleration_audit=quarterly_acceleration_shadow_scores(
            patched,base_metrics)
        for row,metric,shadow_metric in zip(peer_rows,base_metrics,shadow_metrics):
            audit=scan_by_code[row["code"]]
            audit["fundamental_score"]=metric[0]
            audit["growth"]=metric[1]
            audit["quality"]=metric[2]
            audit["valuation_match"]=metric[3]
            audit["growth_risk"]=metric[5]
            shadow_audit=shadow_by_code[row["code"]]
            shadow_audit["fundamental_score"]=shadow_metric[0]
            shadow_audit["growth"]=shadow_metric[1]
            shadow_audit["quality"]=shadow_metric[2]
            shadow_audit["valuation_match"]=shadow_metric[3]
            shadow_audit["growth_risk"]=shadow_metric[5]
        acceleration_evaluations[industry]=acceleration_audit
    # The formal output continues to use baseline scores. The experimental
    # score runs in parallel and is recorded only for offline comparison.
    prescreen_output=prescreen.run(root,scan,industry_index=index,
                     financial_overlay=validated_overlay)
    shadow_output=prescreen.run(root,shadow_scan,industry_index=index,
                     financial_overlay=validated_overlay)
    shadow_group_by_sector={
        g["industry_code"]:g for g in shadow_output["industry_groups"]
    }
    for g in prescreen_output["industry_groups"]:
        sector=g["industry_code"]
        shadow_group=shadow_group_by_sector.get(sector)
        if shadow_group is None:
            raise ValueError("ACCELERATION_SHADOW_INDUSTRY_SCOPE_MISMATCH")
        baseline_codes=g["research_codes"]
        shadow_codes=shadow_group["research_codes"]
        evaluation=acceleration_evaluations[sector]
        evaluation.update({
            "industry_code":sector,
            "baseline_selected_codes":baseline_codes,
            "acceleration_shadow_selected_codes":shadow_codes,
            "changed_out_codes":[x for x in baseline_codes if x not in shadow_codes],
            "changed_in_codes":[x for x in shadow_codes if x not in baseline_codes],
            "selection_changed":baseline_codes!=shadow_codes,
        })
    groups=[]
    for g in prescreen_output["industry_groups"]:
        codes=g["research_codes"]
        if len(codes)>5 or len(codes)!=len(set(codes)) or not codes:
            raise ValueError("ADMISSION_PER_SW3_MODEL_BUDGET_OR_COVERAGE_INVALID")
        groups.append({
            "industry_code":g["industry_code"],
            "selected_codes":codes,
            "source_hard_eligible_count":g["hard_eligible_count"],
            "source_financial_provenance_verified_count":evidence_counts[g["industry_code"]],
            "reason":"PYTHON_UNIFIED_ENTRY_FIRST_FINANCE_CORE_FIRST",
            "selection_policy":"ENTRY_FIRST_NO_QUOTAS",
            "entry_selected_count":g["selection_evidence"]["entry_selected_count"],
            "watch_fallback_count":g["selection_evidence"]["watch_fallback_count"],
        })
    if set(industries)!={g["industry_code"] for g in groups}:
        raise ValueError("ADMISSION_ALL_CONFIRMED_SW3_COVERAGE_REQUIRED")
    return {
        "schema_version":"trend_buy_research_admission",
        "prescreen_version":"CANONICAL",
        "mode":"PROGRAM_VERIFIED_MODEL_RESEARCH_PENDING",
        "selection_policy":"ENTRY_FIRST_NO_QUOTAS",
        "trade_date":day,
        "industry_count":len(groups),
        "selected_company_count":sum(len(g["selected_codes"]) for g in groups),
        "industries":groups,
        "quarterly_financial_acceleration_shadow":{
            "version":"SINGLE_QUARTER_ACCELERATION_V1",
            "mode":"SHADOW_ONLY",
            "not_used_for_formal_selection":True,
            "activation_coverage_threshold":0.75,
            "minimum_peer_count":3,
            "weight_within_growth_dimension":0.20,
            "industries":[acceleration_evaluations[k] for k in sorted(acceleration_evaluations)],
        },
        "source":{
            "confirmed_handoff_sha256":digest(root/"research/trend_handoff.json"),
            "frozen_company_index_sha256":digest(root/"data/low_risk/index.json"),
            "finance_evidence_sha256":digest(finance_path),
            "finance_report_asof_date":finance_stamp,
            "finance_report_source":F10_SOURCE,
        },
        "checks":{
            "only_confirmed_industries":True,
            "all_hard_eligible_python_scanned":True,
            "model_invocations":0,
            "five_company_max_per_sw3":True,
            "ready_wait_unmodified":True,
            "quarterly_acceleration_shadow_only":True,
            "formal_selection_uses_baseline_financial_scores":True,
            "new_same_day_model_review_required":True,
        },
    }


def validate_admission(root,admission):
    day=read(root/"research/trend_handoff.json").get("trade_date")
    idx=read(root/"data/low_risk/index.json")
    src=admission.get("source") or {}
    if (admission.get("schema_version")!="trend_buy_research_admission"
            or admission.get("prescreen_version")!="CANONICAL"
            or admission.get("selection_policy")!="ENTRY_FIRST_NO_QUOTAS"
            or admission.get("trade_date")!=day
            or idx.get("trade_date")!=day
            or src.get("confirmed_handoff_sha256")!=digest(root/"research/trend_handoff.json")
            or src.get("frozen_company_index_sha256")!=digest(root/"data/low_risk/index.json")
            or src.get("finance_evidence_sha256")!=digest(root/"data/research/core_profit_refresh_latest.json")
            or not admission.get("industries")):
        raise ValueError("ADMISSION_SOURCE_STALE_OR_UNVERIFIED")
    finance=read(root/"data/research/core_profit_refresh_latest.json")
    validate_financial_source(finance,day)
    valid_regions={
        code for signal in read(root/"research/trend_handoff.json")["signals"]
        for code in signal.get("industry_codes",[])
    }
    by_sector={}
    all_codes=[]
    for g in admission["industries"]:
        sector=g.get("industry_code")
        codes=g.get("selected_codes")
        if (not sector or sector not in valid_regions or sector in by_sector
                or not isinstance(codes,list) or not 1<=len(codes)<=5
                or len(codes)!=len(set(codes))
                or g.get("selection_policy")!="ENTRY_FIRST_NO_QUOTAS"
                or g.get("reason")!="PYTHON_UNIFIED_ENTRY_FIRST_FINANCE_CORE_FIRST"
                or type(g.get("entry_selected_count")) is not int
                or type(g.get("watch_fallback_count")) is not int
                or g["entry_selected_count"]+g["watch_fallback_count"]!=len(codes)
                or not all(isinstance(x,str) for x in codes)):
            raise ValueError("ADMISSION_ADMISSION_SECTOR_OR_BUDGET_INVALID")
        by_sector[sector]=codes
        all_codes+=codes
    if set(by_sector)!=valid_regions or len(all_codes)!=len(set(all_codes)):
        raise ValueError("ADMISSION_ADMISSION_CONFIRMED_INDUSTRY_COVERAGE_INCOMPLETE")
    if admission.get("selected_company_count")!=len(all_codes):
        raise ValueError("ADMISSION_ADMISSION_SELECTED_COUNT_MISMATCH")
    shadow=admission.get("quarterly_financial_acceleration_shadow") or {}
    if (shadow.get("version")!="SINGLE_QUARTER_ACCELERATION_V1"
            or shadow.get("mode")!="SHADOW_ONLY"
            or shadow.get("not_used_for_formal_selection") is not True):
        raise ValueError("ADMISSION_QUARTERLY_ACCELERATION_SHADOW_CONTRACT_INVALID")
    shadow_by_sector={
        item.get("industry_code"):item for item in shadow.get("industries",[])
    }
    if set(shadow_by_sector)!=set(by_sector):
        raise ValueError("ADMISSION_QUARTERLY_ACCELERATION_SHADOW_SCOPE_MISMATCH")
    for sector,codes in by_sector.items():
        if shadow_by_sector[sector].get("baseline_selected_codes")!=codes:
            raise ValueError("ADMISSION_SHADOW_BASELINE_SELECTION_MISMATCH")
    return by_sector


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    output=args.output.resolve()
    if output.name != "latest.json" or output.parent.name != "trend_buy_candidates":
        raise ValueError("ADMISSION_ADMISSION_WRITES_TO_ITS_OWN_RESEARCH_PATH_ONLY")
    result=prepare()
    validate_admission(ROOT,result)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    readback=read(output)
    assert readback==result
    print("CANONICAL_FROZEN_ADMISSION",json.dumps({
        "trade_date":result["trade_date"],"industries":result["industries"],
        "research_total":result["selected_company_count"],
        "mode":result["mode"],
    },ensure_ascii=False))


if __name__=="__main__":
    main()
