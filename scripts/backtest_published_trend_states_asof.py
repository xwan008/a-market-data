#!/usr/bin/env python3
"""Tiny, authentic as-published TREND STATE proxy on historical SW member baskets.

ONLY observed 18:40-18:48 registry Git blobs. NO recreated model decisions,
historical concept memberships, or forward data for detection.
"""
import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import median
from datetime import datetime, timezone

from backtest_sector_discovery_asof import load, load_days
from route_hotspot_themes import is_main_board


def prices(day, codes):
    out={}
    for code in codes:
        item=(day.get("stocks") or {}).get(code) or {}
        if item.get("confidence") not in ("high","medium"):
            continue
        try:
            p=float(item["price"])
            if p>0:out[code]=p
        except (TypeError, ValueError, KeyError):
            continue
    return out


def result_for_basket(start, future, stock_codes, floor=.8):
    beginning=prices(start,stock_codes)
    ending=prices(future,stock_codes)
    common=sorted(set(beginning)&set(ending))
    eligible=len(stock_codes)
    if eligible<5 or len(common)<max(5,eligible*floor):
        return {"status":"INSUFFICIENT_PAIR_COVERAGE","paired_count":len(common),
                "basket_size":eligible}
    r=median((ending[c]/beginning[c]-1)*100 for c in common)
    return {"status":"OBSERVED","median_stock_return_pct":round(r,4),
            "paired_count":len(common),"basket_size":eligible,
            "paired_coverage":round(len(common)/eligible,4)}


def evaluate(root,day_manifest,registry_manifest):
    days=load_days(root,day_manifest)
    by_day={date:i for i,(date,*_) in enumerate(days)}
    out=[]
    for row in registry_manifest.get("records") or []:
        date,sha=row["trade_date"],row["registry_commit"]
        if date not in by_day:
            raise ValueError("REGISTRY_DAY_NOT_IN_IMMUTABLE_QUOTES:"+date)
        committed=datetime.fromisoformat(row["commit_at_utc"].replace("Z","+00:00"))
        local=committed.astimezone(timezone.utc)
        if committed.utcoffset() is None:
            raise ValueError("REGISTRY_COMMIT_TIMESTAMP_UNVERIFIED")
        # Publication time must be before NEXT signal-session opening;
        # and not before the signal date in Asia/Shanghai.
        from zoneinfo import ZoneInfo
        local=committed.astimezone(ZoneInfo("Asia/Shanghai"))
        if local.date().isoformat()!=date or not (18<=local.hour<=19):
            raise ValueError("REGISTRY_NOT_POSTCLOSE_SAME_DAY:"+date)
        registry=load(Path(root)/"registry"/date/"trend_registry.json")
        if registry.get("trade_date")!=date:
            raise ValueError("HISTORICAL_PUBLISHED_REGISTRY_DATE_MISMATCH")
        i=by_day[date]
        _,source_sha,now,index=days[i]
        sw_members={}
        for code,desc in index["companies"].items():
            code=str(code).zfill(6)
            industry=str(desc.get("industry_code") or "")
            if desc.get("mapping_status")!="mapped" or not is_main_board(code):
                continue
            sw_members.setdefault(industry,set()).add(code)
        for trend in registry.get("trends") or []:
            state=trend.get("market_state")
            if state not in ("趋势确认","候选趋势"):
                continue
            name=trend.get("trend_name")
            sectors=trend.get("industry_codes") or []
            group=set().union(*(sw_members.get(str(sector),set()) for sector in sectors))
            item={
                "trade_date":date,"name":name,
                "published_state":state,"published_T_stage":trend.get("trend_state"),
                "historical_registry_commit":sha,
                "daily_market_commit":source_sha,
                "sw_industry_codes":sectors,
                "asof_mainboard_group_size":len(group),
                "market_state_recomputed_by_test":False,
                "real_theme_membership_used":False,
                "outcomes":{},
            }
            for horizon in (1,2):
                if i+horizon>=len(days):
                    item["outcomes"][str(horizon)]={"status":"RIGHT_CENSORED"}
                    continue
                new_quotes=days[i+horizon][2]
                if not group:
                    item["outcomes"][str(horizon)]={"status":"NO_ASOF_SW_MEMBERS"}
                    continue
                sample=result_for_basket(now,new_quotes,group)
                if sample["status"]=="OBSERVED":
                    market_codes=set(now["stocks"])&set(new_quotes["stocks"])
                    benchmark=result_for_basket(now,new_quotes,market_codes)
                    if benchmark["status"]=="OBSERVED":
                        sample["relative_vs_market_pct"]=round(
                            sample["median_stock_return_pct"]-
                            benchmark["median_stock_return_pct"],4)
                item["outcomes"][str(horizon)]=sample
            out.append(item)
    grouped={}
    for state in ("趋势确认","候选趋势"):
        records=[x for x in out if x["published_state"]==state]
        grouped[state]={}
        for horizon in (1,2):
            observed=[x["outcomes"][str(horizon)] for x in records if
                      x["outcomes"][str(horizon)]["status"]=="OBSERVED"]
            weak=sum(x["median_stock_return_pct"]<=0 and
                     x.get("relative_vs_market_pct",999)<=0 for x in observed)
            grouped[state][str(horizon)]={
                "eligible_trend_date_observations":len(records),
                "observed":len(observed),
                "weak_absolute_and_relative_count":weak,
                "weak_rate":round(weak/len(observed),4) if observed else None,
                "not_observed":len(records)-len(observed),
            }
    return {
        "schema_version":1,
        "result_kind":"limited_real_published_state_forward_proxy",
        "records":out,"summary":grouped,
        "registry_commit_dates":[x["trade_date"] for x in registry_manifest["records"]],
        "limitations":[
            "Only three authentic same-day 18:38-18:48 model-published registry commits; not a statistically meaningful cohort.",
            "Signal-date SW mainboard group membership is a coarse proxy; names such as 固态电池 may be themes in reality and should not be relabeled as industry.",
            "No historical concept constituent snapshots available, so this cannot validate THEME-vs-INDUSTRY mapping or a new theme Top20/Top5.",
            "These are market group stock median forward returns, not executed portfolio returns, risk-adjusted alpha or trade win rates.",
            "The final published state was observed from historical versioned Git commits and never reconstructed from future prices.",
        ],
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",required=True)
    parser.add_argument("--manifest",required=True)
    parser.add_argument("--state-manifest",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    report=evaluate(args.root,load(args.manifest),load(args.state_manifest))
    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print("REAL_PUBLISHED_STATE_PROXY",json.dumps({
        "signals":len(report["records"]),"summary":report["summary"],
        "registry_commit_dates":report["registry_commit_dates"]},ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
