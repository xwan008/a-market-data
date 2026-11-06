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
    return patch,"VALIDATED" if patch else "NO_NEW_FIELDS"

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
    audited=scan["screen_audit"]["lightweight_scanned"]
    scan_by_code={row["code"]:row for row in audited}
    if len(scan_by_code)!=len(audited):
        raise ValueError("ADMISSION_SCANNED_DUPLICATE_COMPANY")
    industries=defaultdict(list)
    for row in audited:
        industries[row["industry_code"]].append(row["code"])
    validated_overlay={}
    evidence_counts={}
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
        for row,metric in zip(peer_rows,scanner.scores(patched,financial_mode="CORE_FIRST")):
            audit=scan_by_code[row["code"]]
            audit["fundamental_score"]=metric[0]
            audit["growth"]=metric[1]
            audit["quality"]=metric[2]
            audit["valuation_match"]=metric[3]
            audit["growth_risk"]=metric[5]
    # Sole stock selection is the audited 正式 dual channel.
    prescreen_output=prescreen.run(root,scan,industry_index=index,
                     financial_overlay=validated_overlay)
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
            "reason":"PYTHON_3_LEADERS_2_ENTRY_FINANCE_CORE_FIRST",
        })
    if set(industries)!={g["industry_code"] for g in groups}:
        raise ValueError("ADMISSION_ALL_CONFIRMED_SW3_COVERAGE_REQUIRED")
    return {
        "schema_version":"trend_buy_research_admission",
        "prescreen_version":"CANONICAL",
        "mode":"PROGRAM_VERIFIED_MODEL_RESEARCH_PENDING",
        "trade_date":day,
        "industry_count":len(groups),
        "selected_company_count":sum(len(g["selected_codes"]) for g in groups),
        "industries":groups,
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
            "new_same_day_model_review_required":True,
        },
    }


def validate_admission(root,admission):
    day=read(root/"research/trend_handoff.json").get("trade_date")
    idx=read(root/"data/low_risk/index.json")
    src=admission.get("source") or {}
    if (admission.get("schema_version")!="trend_buy_research_admission"
            or admission.get("prescreen_version")!="CANONICAL"
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
                or len(codes)!=len(set(codes))):
            raise ValueError("ADMISSION_ADMISSION_SECTOR_OR_BUDGET_INVALID")
        by_sector[sector]=codes
        all_codes+=codes
    if set(by_sector)!=valid_regions or len(all_codes)!=len(set(all_codes)):
        raise ValueError("ADMISSION_ADMISSION_CONFIRMED_INDUSTRY_COVERAGE_INCOMPLETE")
    if admission.get("selected_company_count")!=len(all_codes):
        raise ValueError("ADMISSION_ADMISSION_SELECTED_COUNT_MISMATCH")
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
