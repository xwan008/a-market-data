#!/usr/bin/env python3
"""Event-based A/B for confirmed-sector Top5, without requiring company READY.

Fixed candidate Top5 selected on FIRST sector-confirmed close and held without
replacement. Entry next session's OPEN; on the first non-confirmed sector close,
exit NEXT session's OPEN. Historical candidate algorithm is a retrospective
experimental proxy, not a published old-time trading strategy. No trade advice.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import statistics
import requests

ROOT=Path(__file__).resolve().parents[1]
REPOSITORY="xwan008/a-market-data"
HANDOFF_COMMITS=[
    [
        "2026-10-13",
        "f155c9886e9808e7003a51ed912fecea96bc3909"
    ],
    [
        "2026-10-14",
        "13ef60313270cb5623fb900d2b489acac199804d"
    ],
    [
        "2026-10-15",
        "63aff9b27d673b9538b7a8a0f55715aaee439978"
    ],
    [
        "2026-10-16",
        "1a71d4aeed63c35d70905f8869578e893dd1b6bc"
    ],
    [
        "2026-10-19",
        "e745298a2702e4f74d5e7b920626b329fcee5d24"
    ],
    [
        "2026-10-20",
        "34613814cb6cdeeb631eaeeceb2d62befb17d918"
    ],
    [
        "2026-10-21",
        "d91cb7c2ce1208554915eb628214be6fef195a25"
    ],
    [
        "2026-10-22",
        "77b43e1ec5c432e8ab4b46b447bff343e559a484"
    ],
    [
        "2026-10-23",
        "ef17f409853125431fb757d99ad4e12a5e2e796e"
    ],
    [
        "2026-10-26",
        "34bda5a29493c14cea98155613443611e241bab1"
    ],
    [
        "2026-10-27",
        "4cbb9e599f4eb09d60302d112dce89213872b014"
    ],
    [
        "2026-10-28",
        "9cc963bba18fefa77eef3ed6595aff7c6db5b3f3"
    ],
    [
        "2026-10-29",
        "bcd70bb22ee0fd721c051e0ab04243c6aa60f035"
    ],
    [
        "2026-10-30",
        "a9f4f24be87cbf87451ae50da6ddf497b5f0bb65"
    ],
    [
        "2026-11-02",
        "8b6d9435c217006c3fdf99841b63bc6783c1fd2a"
    ],
    [
        "2026-11-03",
        "02a152cfefe88c9d00b764ed9a84dd044ab36f09"
    ],
    [
        "2026-11-04",
        "130ab3e2521e624d8d8479a757c2df4875e65d98"
    ],
    [
        "2026-11-05",
        "d93dc6dc2b4f3b9efb8c5ef2143f4204f2c8d8e1"
    ],
    [
        "2026-11-06",
        "d75b17c2259b451dba79e9254ef9184977fba9af"
    ],
    [
        "2026-11-09",
        "5480ae81343b77e8edf30bebf3d3ac8efc3e1f05"
    ],
    [
        "2026-11-10",
        "d4540aad9b4c515975970ebe7548e6437480ccbf"
    ],
    [
        "2026-11-11",
        "aaafc381c5108a6cead5ff0c4a4c878e24b066c3"
    ],
    [
        "2026-11-12",
        "f00f4220c6abe9745225d95a01a45f5132c55e16"
    ],
    [
        "2026-11-13",
        "e25728114e6c9687578a5fb9f1eaa1d481921d28"
    ],
    [
        "2026-11-16",
        "9eb5cd9577d5236917a9f51efcbcd637bb53ec32"
    ],
    [
        "2026-11-17",
        "d13b58995a5087eee387788d3ea03ab7837f8f65"
    ],
    [
        "2026-11-18",
        "f7a9724d404ede1b078116e36bb03f3b823e3f40"
    ],
    [
        "2026-11-19",
        "2115e858e5b8cc15aafe3b7003eb46463b8db497"
    ],
    [
        "2026-11-20",
        "641236cda5777430e237de39b2f01087214bda78"
    ]
]
RESEARCH_ARTIFACT_RUN=44918451697


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def as_positive_float(value):
    try:
        result=float(value)
        return result if math.isfinite(result) and result>0 else None
    except (TypeError,ValueError):
        return None


def historical_confirmations():
    """Fetch exactly-pinned official closing handoffs; no hindsight states."""
    token=os.environ.get("GH_TOKEN")
    if not token:
        raise RuntimeError("GH_TOKEN_REQUIRED_TO_READ_PINNED_HANDOFFS")
    headers={"Accept":"application/vnd.github+json",
             "Authorization":"Bearer "+token}
    daily={}
    for day,sha in HANDOFF_COMMITS:
        response=requests.get(
            f"https://api.github.com/repos/{REPOSITORY}/contents/research/trend_handoff.json",
            params={"ref":sha},headers=headers,timeout=25)
        response.raise_for_status()
        encoded=response.json()
        if encoded.get("encoding")!="base64":
            raise RuntimeError("HANDOFF_CONTENT_NOT_BASE64:"+day)
        payload=json.loads(base64.b64decode(encoded["content"]))
        if payload.get("trade_date")!=day or not isinstance(payload.get("signals"),list):
            raise ValueError("HANDOFF_PINNED_DATE_OR_SCHEMA_MISMATCH:"+day)
        confirmed={}
        for signal in payload["signals"]:
            if signal.get("market_state")!="趋势确认":
                continue
            for code in signal.get("industry_codes") or []:
                if code in confirmed:
                    raise ValueError("DUPLICATE_CONFIRMED_SW3:"+day+":"+code)
                confirmed[code]=signal["trend_name"]
        daily[day]=confirmed
    return daily


def event_starts(daily):
    """First confirmed state after a prior archived nonconfirmed close."""
    days=sorted(daily)
    starts=[]
    for index in range(1,len(days)):
        day=days[index]
        previous=set(daily[days[index-1]])
        for code,name in sorted(daily[day].items()):
            if code in previous:
                continue
            end=None
            for future in days[index+1:]:
                if code not in daily[future]:
                    end=future
                    break
            starts.append({
                "industry_code":code,"trend_name":name,
                "confirmed_at":day,"first_unconfirmed_at":end,
                "outcome_status":"LEFT_CENSORED" if index==0 else
                                 "RIGHT_CENSORED" if end is None else "PENDING",
            })
    return starts


def market_prices(codes):
    """Read only latest repository OHLC history, never feed future bars to selections."""
    result={}
    calendar=None
    shard_dir=ROOT/"data/history_shards"
    for prefix in sorted({code[:4] for code in codes}|{"6012"}):
        file=shard_dir/(prefix+".json")
        if not file.exists():
            raise RuntimeError("PRICE_SHARD_MISSING:"+prefix)
        stocks=read(file).get("stocks") or {}
        for code,payload in stocks.items():
            if code not in codes and code!="601288":
                continue
            result[code]={}
            for row in payload.get("history") or []:
                d=str(row.get("date") or "")
                if d:
                    result[code][d]={
                        "open":as_positive_float(row.get("open")),
                        "close":as_positive_float(row.get("close"))}
            if code=="601288":
                calendar=sorted(d for d,r in result[code].items() if r["close"] is not None)
    if not calendar or calendar[-1]<HANDOFF_COMMITS[-1][0]:
        raise RuntimeError("UNVERIFIED_MARKET_CALENDAR_OR_LAST_SESSION")
    return result,calendar


def next_market_session(calendar,asof):
    future=[day for day in calendar if day>asof]
    return future[0] if future else None


def equal_weight_open_to_open(codes,prices,start,end):
    if not codes:
        return {"status":"BLOCKED","reason":"NO_ELIGIBLE_TOP5"}
    observations=[]
    for code in codes:
        r=prices.get(code,{})
        first=(r.get(start) or {}).get("open")
        last=(r.get(end) or {}).get("open")
        if not first or not last:
            return {"status":"CENSORED","reason":"MISSING_OBSERVED_ENTRY_OR_EXIT_OPEN",
                    "affected_code":code}
        observations.append((last/first-1)*100)
    return {"status":"OBSERVED","equal_weight_return_pct":round(statistics.mean(observations),5),
            "company_count":len(observations),"negative_company_count":sum(v<0 for v in observations)}


def evaluate(shadow_report,daily):
    sources=shadow_report.get("industry_sessions") or []
    keyed={(s["date"],s["industry_code"]):s for s in sources}
    episodes=event_starts(daily)
    needed={code for e in episodes for variant in
            ("replayed_baseline_codes","shadow_codes")
            for code in (keyed.get((e["confirmed_at"],e["industry_code"]),{})
                         .get(variant) or [])}
    prices,calendar=market_prices(needed)
    paired=[]
    for episode in episodes:
        signal=episode["confirmed_at"]
        key=(signal,episode["industry_code"])
        source=keyed.get(key)
        if source is None:
            episode["outcome_status"]="NO_RECONSTRUCTED_CANDIDATE_CHECKPOINT"
            continue
        episode["candidate_traceability"]=source["baseline_traceability"]
        baseline=source["replayed_baseline_codes"]
        alternative=source["shadow_codes"]
        episode["baseline_top5"]=baseline
        episode["financial_acceleration_top5"]=alternative
        episode["changed_in"]=source["new_codes"]
        episode["changed_out"]=source["removed_codes"]
        episode["has_member_replacement"]=bool(source["new_codes"] or source["removed_codes"])
        episode["selection_order_changed"]=source["selection_changed"]
        if not source["reconstruction_eligible"]:
            episode["outcome_status"]="BLOCKED_NO_ELIGIBLE_TOP5"
            continue
        if episode["first_unconfirmed_at"] is None:
            episode["outcome_status"]="RIGHT_CENSORED_NO_SECTOR_EXIT_YET"
            continue
        start=next_market_session(calendar,signal)
        end=next_market_session(calendar,episode["first_unconfirmed_at"])
        if not start or not end:
            episode["outcome_status"]="RIGHT_CENSORED_NO_FUTURE_EXECUTION_OPEN"
            continue
        if start>end:
            raise ValueError("EVENT_ENTRY_AFTER_EXIT")
        episode["entry_session_open"]=start
        episode["exit_session_open"]=end
        episode["holding_trading_days"]=calendar.index(end)-calendar.index(start)
        original=equal_weight_open_to_open(baseline,prices,start,end)
        alternate=equal_weight_open_to_open(alternative,prices,start,end)
        episode["baseline_outcome"]=original
        episode["acceleration_outcome"]=alternate
        if original["status"]==alternate["status"]=="OBSERVED":
            episode["outcome_status"]="OBSERVED"
            delta=round(alternate["equal_weight_return_pct"]-
                        original["equal_weight_return_pct"],5)
            episode["delta_acceleration_minus_baseline_pp"]=delta
            paired.append(episode)
        else:
            episode["outcome_status"]="CENSORED_UNPAIRED_PRICE"
    deltas=[e["delta_acceleration_minus_baseline_pp"] for e in paired]
    changed=[e for e in paired if e["has_member_replacement"]]
    changed_deltas=[e["delta_acceleration_minus_baseline_pp"] for e in changed]
    def stats(items):
        return {"n":len(items),
                "mean_delta_pp":round(statistics.mean(items),5) if items else None,
                "improved":sum(x>0 for x in items),
                "worse":sum(x<0 for x in items),
                "unchanged":sum(x==0 for x in items)}
    return {
        "schema_version":1,
        "result_kind":"confirmed_sector_top5_episode_acceleration_ab",
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "selection_policy":"FIRST_OFFICIAL_MARKET_STATE_CONFIRMED_SW3_THEN_FREEZE_OLD_NEW_TOP5",
        "entry_policy":"NEXT_TRADING_DAY_OPEN_AFTER_FIRST_CONFIRMATION_CLOSE",
        "exit_policy":"NEXT_TRADING_DAY_OPEN_AFTER_FIRST_UNCONFIRMED_CLOSE",
        "not_required_company_state":"READY",
        "not_claimed":"NO_EXECUTABLE_TRADING_STRATEGY; NO_ASOF_FINANCIAL_REVISION_RECONSTRUCTION",
        "source_shadow_run_id":RESEARCH_ARTIFACT_RUN,
        "pinned_handoff_snapshots":len(HANDOFF_COMMITS),
        "original_top5_vs_reconstructed":Counter(e.get("candidate_traceability","UNKNOWN") for e in episodes),
        "total_sector_episodes":len(episodes),
        "episodes_with_member_replacement":sum(e.get("has_member_replacement",False) for e in episodes),
        "paired_observed_episodes":len(paired),
        "all_paired":stats(deltas),
        "paired_with_actual_top5_member_change":stats(changed_deltas),
        "episode_status_counts":dict(Counter(e["outcome_status"] for e in episodes)),
        "episodes":episodes,
        "limitations":[
            "Prior candidate rankings were retrospectively reconstructed for early dates and are not contemporary published top5.",
            "The 2026-10-23 robot confirmed group may have incomplete contemporary price history; blocked events are excluded, not imputed.",
            "End-of-day sector downgrade is only observable after close; entry/exit both use following session open.",
            "No READY prerequisite by user's selection-effect study: reported outcomes are hypothetical sector-conditioned baskets, NOT orders or realized PnL.",
            "As-of F10 report-date filtering does not fully reconstruct historical pre-revision vendor datasets.",
            "Industry episodes/companies share market risk and are not statistically independent.",
            "Open-to-open return ignores fees, taxes, dividends, gap liquidity and execution risk.",
            "Right-censored trends are reported but never assigned a fabricated exit.",
        ],
        "no_production_changes":True
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--input",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    source=read(args.input)
    if source.get("group_count")!=92 or source.get("no_formal_publication") is not True:
        raise RuntimeError("UNEXPECTED_RESEARCH_INPUT_ARTIFACT")
    daily=historical_confirmations()
    result=evaluate(source,daily)
    p=Path(args.output)
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=dict)+"\n",encoding="utf-8")
    print("CONFIRMED_SECTOR_EPISODE_AB_SUMMARY",json.dumps({
        key:result[key] for key in
        ("total_sector_episodes","episodes_with_member_replacement",
         "paired_observed_episodes","all_paired",
         "paired_with_actual_top5_member_change","episode_status_counts")
    },ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
