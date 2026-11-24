#!/usr/bin/env python3
"""Read-only, paired close-return replay of the archived official candidate sets.

No signals are generated from outcomes. No portfolio simulation, order or
formal output. Missing/unmatured observations are counted, never imputed.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
from statistics import mean
from trend_buy_engine import opportunity_rank_evidence

METRICS = ("return_pct", "excess_vs_market_pct", "excess_vs_sector_pct")
HORIZONS = ("1", "3", "5", "10")
TOP_K = (1, 2, 3)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def numeric(value):
    return isinstance(value, (int,float)) and not isinstance(value,bool) and math.isfinite(value)


def observation_key(x):
    return x["trade_date"], x["code"], x["source_run_id"]


def replay(formals, observations):
    by_key = {}
    for item in observations["items"]:
        key = observation_key(item)
        if key in by_key:
            raise ValueError("DUPLICATE_OUTCOME:" + str(key))
        by_key[key] = item
    groups, gaps = [], []
    seen = set()
    for formal in sorted(formals, key=lambda x:x["trade_date"]):
        day, run_id = formal["trade_date"], formal["run_id"]
        if day in seen:
            raise ValueError("DUPLICATE_ARCHIVE_DATE:" + day)
        seen.add(day)
        if formal.get("mode") != "FORMAL" or formal.get("status") != "COMPLETE":
            gaps.append({"trade_date":day,"reason":"NOT_COMPLETE_FORMAL"})
            continue
        rows = {r["code"]:r for r in formal["ready"]+formal["wait"]}
        for g in formal["top5_by_theme"]:
            theme = g["trend_name"]
            codes = [x["code"] for x in g["items"]]
            if len(codes) != len(set(codes)) or any(code not in rows for code in codes):
                raise ValueError("INVALID_FROZEN_TOP5:"+day+":"+theme)
            old = [rows[code] for code in codes]
            if not old:
                continue
            if any(x.get("data_date")!=day or x.get("trend_name")!=theme for x in old):
                raise ValueError("INCONSISTENT_FROZEN_MEMBER:"+day+":"+theme)
            evidence = {x["code"]:opportunity_rank_evidence(x,day) for x in old}
            if any(x["status"]!="COMPLETE_ASOF_EVIDENCE" for x in evidence.values()):
                gaps.append({"trade_date":day,"theme":theme,"reason":"ASOF_SCORE_EVIDENCE_MISSING"})
                continue
            new = sorted(old,key=lambda x:(0 if x["status"]=="READY" else 1,
                 -evidence[x["code"]]["score"],x["model_priority"],x["code"]))
            group = {"trade_date":day,"theme":theme,"old_codes":codes,
                     "new_codes":[x["code"] for x in new],"scores":evidence,
                     "paired":{}}
            for horizon in HORIZONS:
                for k in TOP_K:
                    if len(old)<k:
                        continue
                    def collect(items):
                        result = []
                        for row in items[:k]:
                            obs = by_key.get((day,row["code"],run_id),{})
                            h = (obs.get("horizons") or {}).get(horizon,{})
                            if (obs.get("status")!=row["status"]
                                or h.get("state")!="matured"
                                or not isinstance(h.get("target_date"),str)
                                or h["target_date"]<=day
                                or not all(numeric(h.get(m)) for m in METRICS[:2])):
                                return None
                            result.append(h)
                        return {m:mean(x[m] for x in result)
                                if all(numeric(x.get(m)) for x in result) else None
                                for m in METRICS}
                    a,b = collect(old),collect(new)
                    if a is not None and b is not None:
                        group["paired"][f"{horizon}/{k}"] = {"old":a,"new":b}
            groups.append(group)
    summary = {}
    for horizon in HORIZONS:
        for k in TOP_K:
            key=f"{horizon}/{k}"
            pairs=[g["paired"][key] for g in groups if key in g["paired"]]
            summary[key]={"paired_groups":len(pairs),"scored_groups":len(groups),
                          "old":{m:mean(p["old"][m] for p in pairs)
                                 if pairs and all(numeric(p["old"][m]) and numeric(p["new"][m]) for p in pairs)
                                 else None for m in METRICS},
                          "new":{m:mean(p["new"][m] for p in pairs)
                                 if pairs and all(numeric(p["old"][m]) and numeric(p["new"][m]) for p in pairs)
                                 else None for m in METRICS}}
    return {"kind":"NON_PRODUCTION_PAIRED_CLOSE_RETURN_REPLAY",
            "method":"same historical published candidates; status unchanged; not executable return",
            "archive_days":len(seen),"scored_groups":len(groups),
            "scored_rows":sum(len(g["old_codes"]) for g in groups),
            "gaps":gaps,"summary":summary,"groups":groups}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive",type=Path,required=True)
    parser.add_argument("--outcomes",type=Path,required=True)
    parser.add_argument("--from-date",default="0000-00-00")
    parser.add_argument("--through-date",default="9999-99-99")
    args=parser.parse_args()
    formals=[read(p) for p in sorted(args.archive.glob("*/trend_buy_formal_result.json"))
             if args.from_date<=p.parent.name<=args.through_date]
    if not formals:
        raise ValueError("NO_MATCHING_HISTORICAL_FORMAL_ARCHIVES")
    print(json.dumps(replay(formals,read(args.outcomes)),ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
