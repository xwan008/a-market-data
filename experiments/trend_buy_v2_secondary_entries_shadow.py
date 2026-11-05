#!/usr/bin/env python3
"""Explore confirmed-sector secondary entry SHAPES using as-of OHLCV only.

Outputs candidate observations, NEVER an executable buy zone, stop, or READY.
Each signal must be based only on bars completed by that date; future bars
are discarded before any calculation. Historical rebasing is checked.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def good(v):
    return isinstance(v, (int,float)) and not isinstance(v,bool) and math.isfinite(v) and v > 0


def asof_bars(rows, trade_date, frozen_close):
    r = sorted([x for x in rows if isinstance(x.get("date"), str)
                and x["date"] <= trade_date], key=lambda x:x["date"])
    if not r or r[-1]["date"] != trade_date:
        raise ValueError("missing_completed_asof_bar")
    if len({x["date"] for x in r}) != len(r):
        raise ValueError("duplicate_completed_bar")
    if any(not all(good(x.get(k)) for k in ("open","high","low","close","volume"))
           or x["low"] > min(x["open"],x["close"],x["high"])
           or x["high"] < max(x["open"],x["close"],x["low"]) for x in r):
        raise ValueError("invalid_ohlcv")
    if abs(r[-1]["close"]/frozen_close-1) > .015:
        raise ValueError("frozen_price_history_basis_mismatch")
    return r


def detect(rows, trade_date, frozen_close):
    r = asof_bars(rows, trade_date, frozen_close)
    result = {"trade_date":trade_date, "asof_close":frozen_close,
              "mode":"SHADOW_SHAPES_NO_EXECUTABLE_TRADE",
              "trend_follow":False, "consolidation_rebreak":False,
              "observed_recent_low":None, "hypothetical_low_distance_pct":None,
              "trade_entry_zone":None,"trade_invalidation_price":None,
              "trade_R":None, "evidence":[]}
    if len(r) < 22:
        result["evidence"].append("INSUFFICIENT_22_COMPLETED_BARS")
        return result
    today=r[-1]
    prior20=r[-21:-1]
    prior5=r[-6:-1]
    avg20=sum(x["volume"] for x in prior20)/20
    span=today["high"]-today["low"]
    close_pos=(today["close"]-today["low"])/span if span>0 else .5
    volratio=today["volume"]/avg20 if avg20>0 else None
    fresh_break=today["close"] > 1.002*max(x["high"] for x in prior5)
    increasing=sum(r[i]["close"]>r[i-1]["close"] for i in (-3,-2,-1))
    recent_low=min(x["low"] for x in r[-3:])
    distance=100*(frozen_close/recent_low-1)
    result["observed_recent_low"]=round(recent_low,4)
    result["hypothetical_low_distance_pct"]=round(distance,3)
    result["evidence"].append({
        "asof_volume_ratio_20d":round(volratio,3) if volratio is not None else None,
        "asof_close_position_pct":round(close_pos*100,2),
        "fresh_5day_high_break":fresh_break,
        "up_closes_in_last_3":increasing
    })
    # A series already up 2+ of last 3 days and still closing strongly.
    # Recent low only describes excursion, NEVER a verified invalidation.
    if (fresh_break and increasing>=2 and volratio is not None
            and volratio>=1.2 and close_pos>=.65
            and distance<=6):
        result["trend_follow"]=True
        result["evidence"].append("TREND_FOLLOW_OBSERVATION_PASSES")
    else:
        result["evidence"].append("TREND_FOLLOW_NOT_YET_QUALIFIED")
    # Must be real preceding consolidation: 3-6 completed bars, not current bar.
    valid_windows=[]
    for days in (3,4,5,6):
        window=r[-days-1:-1]
        highs=[x["high"] for x in window]
        lows=[x["low"] for x in window]
        closes=[x["close"] for x in window]
        range_pct=100*(max(closes)/min(closes)-1)
        volume_avg=sum(x["volume"] for x in window)/days
        prior_avg=sum(x["volume"] for x in r[-days-21:-days-1])/20
        if (range_pct<=4 and volume_avg<=prior_avg*1.1
                and today["close"]>max(highs)*1.002
                and volratio is not None and volratio>=1.2
                and close_pos>=.65):
            support=min(lows)
            # Constrains observed stretch but still not a stop.
            if 100*(frozen_close/support-1)<=8:
                valid_windows.append({"window_days":days,
                    "observed_consolidation_low":round(support,4),
                    "close_range_pct":round(range_pct,3)})
    if valid_windows:
        result["consolidation_rebreak"]=True
        result["evidence"].append({"best_consolidation":max(
            valid_windows,key=lambda x:x["window_days"])})
    else:
        result["evidence"].append("NO_CONFIRMED_PRECEDING_CONSOLIDATION")
    return result


def evaluate_formal(formal, repository=ROOT):
    trade_date=formal["trade_date"]
    cache={}
    results=[]
    for g in formal.get("top5_by_theme") or []:
        for item in g.get("items") or []:
            code=item["code"]
            prefix=code[:4]
            if prefix not in cache:
                path=repository/"data/history_shards"/(prefix+".json")
                cache[prefix]=json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            stock=(cache[prefix].get("stocks") or {}).get(code) or {}
            try:
                result=detect(stock.get("history") or [],trade_date,item["current_price"])
            except ValueError as err:
                result={"error":str(err), "trend_follow":False,
                        "consolidation_rebreak":False,
                        "trade_entry_zone":None, "trade_invalidation_price":None,
                        "trade_R":None}
            results.append({"theme":g["trend_name"],"code":code,
                            "name":item.get("company_name"),"status":item.get("status"),
                            "signal":result})
    return {"mode":"SECONDARY_ENTRY_SHAPES_SHADOW_ONLY",
            "trade_date":trade_date,"items":results,
            "signals_are_not_order_or_ready":True}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--formal",type=Path,default=ROOT/"research/trend_buy_formal_result.json")
    ap.add_argument("--output",type=Path)
    a=ap.parse_args()
    formal=json.loads(a.formal.read_text(encoding="utf-8"))
    result=evaluate_formal(formal)
    if a.output:
        path=a.output.resolve()
        if "shadow" not in str(path).lower() or "trend_buy_formal_result" in str(path):
            raise ValueError("shadow_output_required")
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"trade_date":result["trade_date"],
        "count":len(result["items"]),
        "trend_follow":[x["code"] for x in result["items"] if x["signal"]["trend_follow"]],
        "consolidation_rebreak":[x["code"] for x in result["items"]
                                 if x["signal"]["consolidation_rebreak"]],
        "invalid_history":[x["code"] for x in result["items"]
                           if x["signal"].get("error")]},ensure_ascii=False))

if __name__=="__main__":
    main()
