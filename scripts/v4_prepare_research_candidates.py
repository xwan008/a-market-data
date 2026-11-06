#!/usr/bin/env python3
"""V4 single-mainline company research admission: program BEFORE model.

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
import build_trend_buy_manual_research as old
import v4_financial_factorial_core as four


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_financial_source(finance, day):
    stamp=finance.get("asof_trade_date")
    if (finance.get("source")!=four.SOURCE or not isinstance(stamp,str)
            or not isinstance(finance.get("records"),dict)):
        raise ValueError("V4_F10_PROVENANCE_MISSING")
    delta=(date.fromisoformat(day)-date.fromisoformat(stamp)).days
    if not 0<=delta<=14:
        raise ValueError("V4_F10_SOURCE_DATE_NOT_VALID_FOR_CURRENT_SIGNAL")
    return stamp


def prepare(root=ROOT):
    trend=read(root/"research/trend_handoff.json")
    index=read(root/"data/low_risk/index.json")
    day=trend.get("trade_date")
    if not isinstance(day,str) or index.get("trade_date")!=day:
        raise ValueError("V4_ASOF_INPUT_MISMATCH")
    if not trend.get("signals"):
        raise ValueError("V4_NO_UPSTREAM_CONFIRMED_SW3")
    # The builder rechecks the original upstream registry + CORE/DIRECT routing.
    finance_path=root/"data/research/core_profit_refresh_latest.json"
    finance=read(finance_path)
    finance_stamp=validate_financial_source(finance,day)
    with tempfile.TemporaryDirectory(prefix="v4-prescreen-") as work:
        empty=Path(work)/"empty_reviews.json"
        empty.write_text(json.dumps({
            "schema_version":"trend_buy_company_reviews_v2",
            "as_of_date":day,
            "reviews":[],
        },ensure_ascii=False),encoding="utf-8")
        # Run the hard screen on ALL eligible companies. With zero deep
        # reviews it can never create a FORMAL result, only SHA-audited input.
        legacy=old.build(empty)
        if legacy["mode"]!="SHADOW" or not legacy["screen_audit"]["hard_eligible"]:
            raise ValueError("V4_PRE_RESEARCH_FAILED_CLOSED")
        factor=four.run(root,legacy,finance)
    groups=[]
    for g in factor["industry_groups"]:
        codes=g["cases"]["V4_CORE_FIRST"]
        if len(codes)>5 or len(codes)!=len(set(codes)):
            raise ValueError("V4_PER_SW3_MODEL_BUDGET_EXCEEDED")
        if len(codes)==0:
            raise ValueError("V4_NO_VALID_MEMBER_FOR_CONFIRMED_INDUSTRY:"+g["industry_code"])
        groups.append({
            "industry_code":g["industry_code"],
            "selected_codes":codes,
            "source_hard_eligible_count":g["hard_eligible_count"],
            "source_core_profit_matched_count":g["core_evidence_patched_count"],
            "reason":"PYTHON_3_LEADERS_2_ENTRY_FINANCE_CORE_FIRST",
        })
    if not groups:
        raise ValueError("V4_NO_VALID_CANDIDATES")
    return {
        "schema_version":"trend_buy_v4_research_admission_v1",
        "prescreen_version":"V4_B1",
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
            "finance_report_source":four.SOURCE,
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
    if (admission.get("schema_version")!="trend_buy_v4_research_admission_v1"
            or admission.get("prescreen_version")!="V4_B1"
            or admission.get("trade_date")!=day
            or idx.get("trade_date")!=day
            or src.get("confirmed_handoff_sha256")!=digest(root/"research/trend_handoff.json")
            or src.get("frozen_company_index_sha256")!=digest(root/"data/low_risk/index.json")
            or src.get("finance_evidence_sha256")!=digest(root/"data/research/core_profit_refresh_latest.json")
            or not admission.get("industries")):
        raise ValueError("V4_ADMISSION_SOURCE_STALE_OR_UNVERIFIED")
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
            raise ValueError("V4_ADMISSION_SECTOR_OR_BUDGET_INVALID")
        by_sector[sector]=codes
        all_codes+=codes
    if set(by_sector)!=valid_regions or len(all_codes)!=len(set(all_codes)):
        raise ValueError("V4_ADMISSION_CONFIRMED_INDUSTRY_COVERAGE_INCOMPLETE")
    if admission.get("selected_company_count")!=len(all_codes):
        raise ValueError("V4_ADMISSION_SELECTED_COUNT_MISMATCH")
    return by_sector


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    output=args.output.resolve()
    if "trend_buy_v4_candidates" not in str(output):
        raise ValueError("V4_ADMISSION_WRITES_TO_ITS_OWN_RESEARCH_PATH_ONLY")
    result=prepare()
    validate_admission(ROOT,result)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    readback=read(output)
    assert readback==result
    print("V4_B1_FROZEN_ADMISSION",json.dumps({
        "trade_date":result["trade_date"],"industries":result["industries"],
        "research_total":result["selected_company_count"],
        "mode":result["mode"],
    },ensure_ascii=False))


if __name__=="__main__":
    main()
