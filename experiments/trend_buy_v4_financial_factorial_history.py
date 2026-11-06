#!/usr/bin/env python3
"""Four-arm as-of historical snapshots (11/03-11/05) with future-only outcomes.

Important: newly recovered F10 numbers are an as-of date-filtered *proxy*,
not independently archived reports from that past date. No claim of a
point-in-time historically executed trading system.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"experiments"))
import trend_buy_v4_historical_frozen_replay as hist
import trend_buy_v4_financial_factorial_shadow as experiment
import trend_buy_v4_python_prescreen_shadow as v4

def run(dates,finance,root=ROOT):
    records=hist.first_published_rankings(root,set(dates))
    result={"mode":"CORE_FINANCE_2x2_HISTORICAL_RETROSPECTIVE_SENSITIVITY",
            "requested_dates":dates,"completed":[],"failed":[],
            "no_future_asof_information":True,
            "no_new_company_model_reviews":True,
            "no_formal_strategy_change":True,
            "limitations":[
                "Current F10 source snapshot only: publication/update date filtered but not historically archived",
                "Re-ranked Python candidate baskets only: not reviewed model Top5 or real execution",
                "Original sector sets and quote snapshots taken from first actually published original Git commit",
                "Future bars are used for outcome only, not for program scoring",
                "Only horizons with fully available subsequent sessions are scored; small and dependent sample",
                "Not suitable for statistical ranking improvement claims"]}
    for day in dates:
        record=records.get(day)
        if not record:
            result["failed"].append({"date":day,"error":"NO_REAL_HISTORICAL_PUBLICATION"})
            continue
        sha=record["sha"]
        with tempfile.TemporaryDirectory(prefix="v4factorial-") as tmp:
            clone=Path(tmp)/"frozen"
            try:
                hist.git(root,"worktree","add","--detach",str(clone),sha)
                screen=Path(tmp)/"frozen-original-shadow.json"
                subprocess.run([
                    sys.executable,str(clone/"scripts/build_trend_buy_manual_research.py"),
                    "--evidence",str(clone/"research/trend_buy_company_reviews/latest.json"),
                    "--output",str(screen)],
                    cwd=clone,check=True,stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,text=True)
                snapshot=v4.read_json(screen)
                if snapshot.get("trade_date")!=day:
                    raise ValueError("published_screen_day_mismatch")
                arms=experiment.run(clone,snapshot,finance)
                indexes=v4.read_json(clone/"data/low_risk/index.json")
                groups=[]
                for item in arms["industry_groups"]:
                    all_codes={c for stock_list in item["cases"].values() for c in stock_list}
                    original_rows=v4.frozen_industry_rows(clone,indexes,
                                                            item["industry_code"],day)
                    frozen_prices={r["code"]:r["price"] for r in original_rows
                                   if r["code"] in all_codes}
                    observations={}
                    errors={}
                    for code in all_codes:
                        returns,error=hist.future_returns(root,code,day,
                                            frozen_prices.get(code),horizons=(1,2,3,5,10))
                        if error:errors[code]=error
                        else:observations[code]=returns
                    metrics={}
                    for horizon in ("1","2","3","5","10"):
                        if all(code in observations and observations[code][horizon] is not None
                               for code in all_codes):
                            returns={arm:round(
                                sum(observations[c][horizon] for c in codes)/len(codes),5)
                                for arm,codes in item["cases"].items() if codes}
                            if len(returns)==4:
                                metrics[horizon]={
                                    "unreviewed_top5_equal_weight_open_to_close_pct":returns,
                                    "original_core_increment_pp":round(
                                        returns["ORIGINAL_CORE_FIRST"]-returns["ORIGINAL_LEGACY"],5),
                                    "v4_core_increment_pp":round(
                                        returns["V4_CORE_FIRST"]-returns["V4_LEGACY"],5),
                                    "v4_minus_original_with_core_pp":round(
                                        returns["V4_CORE_FIRST"]-returns["ORIGINAL_CORE_FIRST"],5)}
                            else: metrics[horizon]=None
                        else:
                            metrics[horizon]=None
                    groups.append({
                        "industry_code":item["industry_code"],
                        "cases":item["cases"],
                        "core_patched":item["core_evidence_patched_count"],
                        "source_reasons":item["source_audit"],
                        "horizon_metrics":metrics,
                        "unobservable_stock_reasons":errors})
                result["completed"].append({
                    "date":day,"original_commit":sha,
                    "original_published_at":record["published_at"],
                    "financial_source_retrospective":arms["source_snapshot_is_retrospective"],
                    "groups":groups})
            except (subprocess.CalledProcessError,ValueError,KeyError,OSError) as exc:
                err=(exc.stderr[-2000:] if isinstance(exc,subprocess.CalledProcessError)
                     and isinstance(exc.stderr,str) else str(exc))
                result["failed"].append({"date":day,"commit":sha,
                                        "error":type(exc).__name__+":"+err[:1200]})
            finally:
                if clone.exists():
                    try:hist.git(root,"worktree","remove","--force",str(clone))
                    except subprocess.CalledProcessError:pass
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--dates",default="2026-11-03,2026-11-04,2026-11-05")
    p.add_argument("--finance",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    dates=[x.strip() for x in args.dates.split(",") if x.strip()]
    if not dates or len(dates)>6 or len(dates)!=len(set(dates)):
        raise ValueError("invalid_distinct_dates")
    output=args.output.resolve()
    if "shadow" not in str(output).lower():
        raise ValueError("shadow_only_output")
    outcome=run(dates,v4.read_json(args.finance))
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(outcome,indent=2,ensure_ascii=False)+"\n",
                      encoding="utf-8")
    for section in outcome["completed"]:
        for group in section["groups"]:
            print("HISTORICAL_FINANCIAL_FACTORIAL "+json.dumps({
                "date":section["date"],"industry":group["industry_code"],
                "cases":group["cases"],"core_patched":group["core_patched"],
                "metrics":group["horizon_metrics"],"excluded":group["unobservable_stock_reasons"]
            },ensure_ascii=False))
    print("HISTORICAL_FINANCIAL_FAILURES "+json.dumps(outcome["failed"],ensure_ascii=False))


if __name__=="__main__":
    main()
