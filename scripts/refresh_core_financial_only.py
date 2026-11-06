#!/usr/bin/env python3
"""Financial-only F10 core-profit backfill. DOES NOT fetch or change price bars.

Uses Eastmoney's proven batch SECUCODE-IN endpoint (RPT_F10_FINANCE_MAINFINADATA).
Reads last persisted data/latest.json, filters each report to as-of published
and not later-updated facts; never replaces a known value with null. Shadow
mode writes ONLY a separate output report. Apply mode is explicitly requested
by the weekly pipeline, before market data is committed.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
import json
import math
from pathlib import Path
import re
import time
from zoneinfo import ZoneInfo
import requests

ROOT=Path(__file__).resolve().parents[1]
URL="https://datacenter-web.eastmoney.com/api/data/v1/get"
SOURCE="eastmoney_RPT_F10_FINANCE_MAINFINADATA"
HEADERS={"User-Agent":"Mozilla/5.0","Referer":"https://emweb.securities.eastmoney.com/"}
SH=("600","601","603","605","688","689")
DEFAULT_BATCH_SIZE=40
TZ=ZoneInfo("Asia/Shanghai")


def as_number(x):
    try:
        v=float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def day(s):
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10]).isoformat()
    except ValueError:
        return None


def secu_code(code):
    if not re.fullmatch(r"\d{6}",code):
        raise ValueError("invalid_ashare_stock_code:"+str(code))
    return code+(".SH" if code.startswith(SH) else ".SZ")


def query_batch(codes, *, timeout=25, attempts=2):
    """One batch, first 500 latest report rows for all requested companies."""
    names=",".join('"'+secu_code(c)+'"' for c in codes)
    params={
        "reportName":"RPT_F10_FINANCE_MAINFINADATA",
        "columns":"ALL",
        "filter":f"(SECUCODE in ({names}))",
        "sortColumns":"REPORT_DATE",
        "sortTypes":"-1",
        "pageSize":500,
        "pageNumber":1,
        "source":"WEB","client":"WEB",
    }
    error=None
    for attempt in range(attempts):
        try:
            response=requests.get(URL,params=params,headers=HEADERS,timeout=timeout)
            response.raise_for_status()
            payload=response.json()
            part=payload.get("result") or {}
            rows=part.get("data") or []
            if payload.get("success") is not True or not rows:
                raise ValueError("f10_batch_no_rows_or_unsuccessful")
            if any(str(item.get("SECURITY_CODE")) not in set(codes) for item in rows):
                raise ValueError("f10_unexpected_company_response")
            return rows
        except (requests.RequestException, ValueError, TypeError) as exc:
            error=exc
            if attempt+1<attempts:
                time.sleep(attempt+1)
    raise RuntimeError(f"F10_BATCH_FAILED_{len(codes)}:"+type(error).__name__+":"+str(error)[:100])


def find_asof_row(rows, code, asof):
    candidates=[]
    for row in rows:
        if row.get("SECURITY_CODE")!=code:
            continue
        period=day(row.get("REPORT_DATE"))
        notice=day(row.get("NOTICE_DATE"))
        updated=day(row.get("UPDATE_DATE"))
        if not period or not notice or period>asof or notice>asof:
            continue
        if updated and updated>asof:
            continue
        core=as_number(row.get("KCFJCXSYJLR"))
        yoy=as_number(row.get("KCFJCXSYJLRTZ"))
        eps=as_number(row.get("EPSKCJB"))
        if core is None and yoy is None and eps is None:
            continue
        parent=as_number(row.get("PARENTNETPROFIT"))
        share=(100*(parent-core)/abs(parent)
               if parent is not None and core is not None and abs(parent)>1
               else None)
        candidates.append({
            "code":code,"report_date":period,"notice_date":notice,
            "update_date":updated,
            "deduct_net_profit":core,
            "deduct_net_profit_yoy":yoy,
            "deduct_basic_eps":eps,
            "reported_parent_net_profit":parent,
            "nonrecurring_profit_share_pct":round(share,4) if share is not None else None,
            "source_report":SOURCE,
            "source_public_url":"https://datacenter-web.eastmoney.com/api/data/v1/get",
        })
    return max(candidates,key=lambda r:(r["report_date"],r["notice_date"])) if candidates else None


def fetch_all(codes,asof,batch_size=DEFAULT_BATCH_SIZE,workers=4):
    codes=sorted(set(codes))
    if not codes:
        raise ValueError("no_stocks_to_refresh")
    batches=[codes[i:i+batch_size] for i in range(0,len(codes),batch_size)]
    selected={}
    errors=[]
    # Fail isolated bad batch recursively instead of silently losing its peers.
    def retrieve(group):
        try:
            rows=query_batch(group)
            found={c:find_asof_row(rows,c,asof) for c in group}
            return found,[]
        except Exception as exc:
            if len(group)==1:
                return {},[{"code":group[0],"error":type(exc).__name__+":"+str(exc)[:130]}]
            mid=len(group)//2
            left,le=retrieve(group[:mid])
            right,re=retrieve(group[mid:])
            return {**left,**right},le+re

    with ThreadPoolExecutor(max_workers=max(1,min(workers,6))) as pool:
        futures=[pool.submit(retrieve,b) for b in batches]
        for fut in as_completed(futures):
            found,issues=fut.result()
            for code,row in found.items():
                if row is not None:
                    selected[code]=row
            errors.extend(issues)
    return selected,errors,len(batches)


def apply_to_copy(snapshot,records):
    """No mutation of source payload; no changes to any price/trend field."""
    updated=json.loads(json.dumps(snapshot))
    stocks=updated.get("stocks") or {}
    changed=0
    mismatched=[]
    for code,stock in stocks.items():
        report=records.get(code)
        if report is None:
            continue
        prior=stock.get("fundamentals") or {}
        current_period=day(prior.get("report_date"))
        if current_period!=report["report_date"]:
            mismatched.append({"code":code,
                               "existing_report_date":current_period,
                               "candidate_date":report["report_date"]})
            continue
        fundamentals=dict(prior)
        patched=False
        for src,dest in (
            ("deduct_net_profit","deduct_net_profit"),
            ("deduct_net_profit_yoy","deduct_net_profit_yoy"),
            ("deduct_basic_eps","deduct_basic_eps"),
            ("nonrecurring_profit_share_pct","nonrecurring_profit_share_pct"),
        ):
            candidate=report.get(src)
            if candidate is not None and as_number(fundamentals.get(dest)) is None:
                fundamentals[dest]=candidate
                patched=True
        if patched:
            fundamentals["core_profit_notice_date"]=report["notice_date"]
            fundamentals["core_profit_update_date"]=report["update_date"]
            sources=dict(fundamentals.get("sources") or {})
            sources["core_profit"]=SOURCE
            fundamentals["sources"]=sources
            stock["fundamentals"]=fundamentals
            changed+=1
    stats=dict(updated.get("fundamental_stats") or {})
    stats["deduct_profit_growth_usable"]=sum(
        as_number(((s.get("fundamentals") or {}).get("deduct_net_profit_yoy"))) is not None
        or as_number(((s.get("fundamentals") or {}).get("deduct_basic_eps_yoy"))) is not None
        for s in stocks.values())
    stats["core_profit_amount_usable"]=sum(
        as_number(((s.get("fundamentals") or {}).get("deduct_net_profit"))) is not None
        for s in stocks.values())
    stats["core_profit_backfill_updated_stocks"]=changed
    updated["fundamental_stats"]=stats
    return updated,{"updated_stocks":changed,"report_date_mismatches":mismatched}


def build_report(snapshot,records,errors,batches,updated,changes):
    stocks=snapshot["stocks"]
    initial=sum(
        as_number(((s.get("fundamentals") or {}).get("deduct_net_profit_yoy"))) is not None
        or as_number(((s.get("fundamentals") or {}).get("deduct_basic_eps_yoy"))) is not None
        for s in stocks.values())
    stats=updated["fundamental_stats"]
    return {
        "mode":"CORE_FINANCIAL_ONLY_BACKFILL_SHADOW_REVIEW",
        "asof_date":snapshot["trade_date"],
        "generated_at":datetime.now(TZ).isoformat(),
        "source":SOURCE,
        "market_snapshot_unmodified_in_report":True,
        "scope":"COMPLETE_FROZEN_MARKET_COMPANIES",
        "stocks":len(stocks),
        "batch_count":batches,
        "report_rows_asof_with_any_core_evidence":len(records),
        "prior_deduct_growth_usable":initial,
        "after_deduct_growth_usable":stats["deduct_profit_growth_usable"],
        "after_core_amount_usable":stats["core_profit_amount_usable"],
        "updated_stocks":changes["updated_stocks"],
        "report_date_mismatches":changes["report_date_mismatches"][:30],
        "unresolved_query_errors":errors[:100],
        "source_data_retrieval_incomplete":bool(errors),
        "sample_verified_companies":{
            code:records.get(code) for code in
            ("000506","600489","600547","002517","002624","600519")
            if code in records},
        "records":records
    }


def run(snapshot,batch_size=DEFAULT_BATCH_SIZE,workers=4):
    if not isinstance(snapshot.get("stocks"),dict) or len(snapshot["stocks"])<20:
        raise ValueError("invalid_frozen_market_snapshot")
    asof=day(snapshot.get("trade_date"))
    if not asof:
        raise ValueError("missing_frozen_trade_date")
    # Must NEVER accept notices published after this immutable daily trade date.
    records,errors,batches=fetch_all(
        snapshot["stocks"].keys(),asof,batch_size=batch_size,workers=workers)
    enriched,changes=apply_to_copy(snapshot,records)
    report=build_report(snapshot,records,errors,batches,enriched,changes)
    return enriched,report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--input",type=Path,default=ROOT/"data/latest.json")
    parser.add_argument("--output",type=Path,required=True,help="Only shadow report JSON")
    parser.add_argument("--apply",action="store_true",
                        help="Explicit weekly-only enriched data/latest.json write")
    parser.add_argument("--batch-size",type=int,default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--workers",type=int,default=4)
    parser.add_argument("--min-core-coverage",type=float,default=.75)
    args=parser.parse_args()
    if not 1<=args.batch_size<=80 or not 1<=args.workers<=6:
        raise ValueError("batch_size_or_workers_out_of_bounds")
    output=args.output.resolve()
    if "shadow" not in str(output).lower() or any(s in str(output) for s in
            ("trend_buy_formal_result","trend_buy_handoff")):
        raise ValueError("shadow_report_path_required")
    src=json.loads(args.input.read_text(encoding="utf-8"))
    updated,report=run(src,args.batch_size,args.workers)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    coverage=report["after_deduct_growth_usable"]/report["stocks"]
    print("CORE_PROFIT_BACKFILL_STATS "+json.dumps({
        k:report[k] for k in (
            "asof_date","stocks","batch_count",
            "report_rows_asof_with_any_core_evidence",
            "prior_deduct_growth_usable","after_deduct_growth_usable",
            "after_core_amount_usable","updated_stocks",
            "source_data_retrieval_incomplete")},ensure_ascii=False))
    print("CORE_PROFIT_BACKFILL_SAMPLES "+json.dumps(
        report["sample_verified_companies"],ensure_ascii=False))
    if (coverage<args.min_core_coverage
        or report["source_data_retrieval_incomplete"]):
        raise RuntimeError(
            f"core_profit_not_fresh_enough:{coverage:.2%}; "
            f"errors={len(report['unresolved_query_errors'])}; "
            "original_market_snapshot_preserved")
    if args.apply:
        if args.input.resolve()!=ROOT.joinpath("data/latest.json").resolve():
            raise ValueError("apply_only_to_canonical_latest")
        args.input.write_text(json.dumps(updated,ensure_ascii=False,indent=2)+"\n",
                              encoding="utf-8")
        print("CORE_PROFIT_BACKFILL_APPLIED_WITHOUT_PRICE_CHANGES")
    else:
        print("CORE_PROFIT_BACKFILL_SHADOW_ONLY_NO_REPOSITORY_WRITES")


if __name__=="__main__":
    main()
