#!/usr/bin/env python3
"""Read-only Q1/Q2/Q3 cumulative deductible-profit probe at 2026-11-23 as-of.

Emits actual single-quarter Q2 and Q3 profits and their quarter-on-quarter
change, not the change between two YoY growth percentages. No repo writes.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import build_trend_buy_manual_research as scanner
import refresh_core_financial_only as src
DAY="2026-11-23"
PERIODS=("2026-03-31","2026-06-30","2026-09-30")

def read(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))

def candidate_codes():
    with tempfile.TemporaryDirectory(prefix="profit-qoq-audit-") as d:
        empty=Path(d)/"reviews.json"
        empty.write_text(json.dumps({"schema_version":"trend_buy_company_reviews_v2",
                                     "as_of_date":DAY,"reviews":[]}),encoding="utf-8")
        audit=scanner.build(empty,audit_only=True)
    return sorted({x["code"] for x in audit["screen_audit"]["lightweight_scanned"]})

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--output",default="/tmp/real_profit_qoq_20261123.json")
    args=a.parse_args()
    out=Path(args.output).resolve()
    if ROOT.resolve() in out.parents or out==ROOT.resolve():
        raise ValueError("QOQ_PROBE_CAN_ONLY_WRITE_OUTSIDE_REPO")
    finance=read(ROOT/"data/research/core_profit_refresh_latest.json")
    assert finance["asof_trade_date"]<DAY
    codes=candidate_codes()
    assert len(codes)==38,(len(codes),codes)
    raw=src.query_batch(codes,timeout=40,attempts=3)
    by=defaultdict(dict)
    for r in raw:
        code=r.get("SECURITY_CODE")
        period=src.day(r.get("REPORT_DATE"))
        published=src.day(r.get("NOTICE_DATE"))
        updated=src.day(r.get("UPDATE_DATE"))
        if (code not in codes or period not in PERIODS or not published
            or published>DAY or period>DAY or (updated and updated>DAY)):
            continue
        amount=src.as_number(r.get("KCFJCXSYJLR"))
        if amount is None:
            continue
        old=by[code].get(period)
        evidence={"period":period,"notice_date":published,"update_date":updated,
                  "cumulative_deduct_profit_yuan":amount}
        if not old or (published,updated or "")>(old["notice_date"],old.get("update_date") or ""):
            by[code][period]=evidence
    report=[]
    mismatches=[]
    counts=defaultdict(int)
    for code in codes:
        available=by[code]
        q1,q2,q3=(available.get(p) for p in PERIODS)
        row={"code":code,"periods":available}
        if not (q1 and q2 and q3):
            row.update(status="MISSING_REPORT",missing=[p for p in PERIODS if p not in available])
            counts["MISSING_REPORT"]+=1
            report.append(row);continue
        frozen=finance["records"].get(code)
        if (not frozen or frozen.get("report_date")!="2026-09-30"
            or not isinstance(frozen.get("deduct_net_profit"),(int,float))
            or abs(q3["cumulative_deduct_profit_yuan"]-frozen["deduct_net_profit"])>
               max(1.0,abs(frozen["deduct_net_profit"])*.001)):
            row["status"]="Q3_SOURCE_MISMATCH"
            mismatches.append(code);counts["Q3_SOURCE_MISMATCH"]+=1
            report.append(row);continue
        profit_q2=q2["cumulative_deduct_profit_yuan"]-q1["cumulative_deduct_profit_yuan"]
        profit_q3=q3["cumulative_deduct_profit_yuan"]-q2["cumulative_deduct_profit_yuan"]
        row.update({"profit_q2_yuan":round(profit_q2,2),
                    "profit_q3_yuan":round(profit_q3,2),
                    "change_yuan":round(profit_q3-profit_q2,2),
                    "qoq_pct":round(100*(profit_q3/profit_q2-1),4) if profit_q2>0 else None,
                    "latest_single_quarter_profit_yoy_pct":
                        frozen.get("single_quarter_deduct_net_profit_yoy"),
                    "previous_single_quarter_profit_yoy_pct":
                        (frozen.get("quarterly_acceleration") or {}).get("previous_single_quarter_deduct_profit_yoy_pct")})
        row["status"]=("COMPLETE_POSITIVE_BASE" if profit_q2>0 else
                       "TURNAROUND_FROM_LOSS" if profit_q2<0 and profit_q3>0 else
                       "NON_POSITIVE_Q2_BASE")
        counts[row["status"]]+=1
        report.append(row)
    answer={"mode":"READ_ONLY_REAL_QOQ_PROBE","trade_date":DAY,"codes":len(codes),
            "raw_rows":len(raw),"status_counts":dict(counts),
            "q3_frozen_mismatches":mismatches,"all_asof":True,
            "formula":"Q2 single = Q2 YTD - Q1 YTD; Q3 single = Q3 YTD - Q2 YTD",
            "qoq_only_when_q2_profit_positive":True,
            "records":report}
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(answer,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("REAL_QOQ_PROBE",json.dumps({
        "records":len(report),"status_counts":dict(counts),
        "q3_mismatch":mismatches,"raw_rows":len(raw),
        "sample":{r["code"]:{"status":r["status"],"qoq_pct":r.get("qoq_pct")}
                  for r in report if r["code"] in ("002463","605058","603920","601658")}
    },ensure_ascii=False))
if __name__=="__main__":
    main()
