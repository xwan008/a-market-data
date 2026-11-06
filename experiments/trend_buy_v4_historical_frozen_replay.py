#!/usr/bin/env python3
"""Historical V4 prescreen coverage from ORIGINAL committed frozen files only.

Uses a temporary detached Git worktree per original formal publication. It
reruns that day's Python pre-screen, then applies today's declared V4 logic to
ONLY THEN-stored frozen history. The current history is read for subsequent
outcomes, never for historical selection. Unreviewed new names are NOT trades.
"""
from __future__ import annotations

import argparse
from datetime import datetime,timedelta
import json
from pathlib import Path
import subprocess
import tempfile
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
TZ=ZoneInfo("Asia/Shanghai")
FORMAL="research/trend_buy_formal_result.json"


def git(root,*args):
    return subprocess.run(["git",*args],cwd=root,check=True,
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          text=True).stdout


def show_json(root,sha,path):
    try:
        return json.loads(git(root,"show",sha+":"+path))
    except (subprocess.CalledProcessError,json.JSONDecodeError):
        return None


def first_published_rankings(root,days):
    lines=git(root,"log","--format=%H%x09%cI","--",FORMAL).splitlines()
    selected={}
    for line in reversed(lines):
        sha,stamp=line.split("\t")
        formal=show_json(root,sha,FORMAL)
        if not isinstance(formal,dict):
            continue
        day=formal.get("trade_date")
        if day not in days or day in selected:
            continue
        if formal.get("status")!="COMPLETE" or not formal.get("top5_by_theme"):
            continue
        timestamp=datetime.fromisoformat(stamp).astimezone(TZ)
        asof_close=datetime.fromisoformat(day+"T15:00:00+08:00")
        if not asof_close <= timestamp <= asof_close+timedelta(hours=36):
            continue
        selected[day]={"sha":sha,"published_at":timestamp.isoformat(),
                       "formal":formal}
    return selected


def future_returns(current_root,code,asof_date,known_asof_price,horizons=(1,2)):
    """Entirely outcome-only K lines, with strict asof price-basis match."""
    from trend_buy_v4_python_prescreen_shadow import history_for,positive
    stock=history_for(current_root,code,{})
    series={x["date"]:x for x in stock.get("history") or []
            if isinstance(x.get("date"),str)}
    asof=series.get(asof_date)
    if not asof or not positive(asof.get("close")):
        return None,"ASOF_CURRENT_HISTORY_MISSING"
    if not positive(known_asof_price) or abs(asof["close"]/known_asof_price-1)>.015:
        return None,"ASOF_HISTORY_PRICE_BASIS_MISMATCH"
    future=sorted(d for d in series if d>asof_date)
    out={}
    for days in horizons:
        if len(future)<days:
            out[str(days)]=None
            continue
        start=series[future[0]]
        end=series[future[days-1]]
        if not positive(start.get("open")) or not positive(end.get("close")):
            out[str(days)]=None
        else:
            out[str(days)]=round(100*(end["close"]/start["open"]-1),5)
    return out,None


def run(root,days):
    published=first_published_rankings(root,set(days))
    output={"mode":"V4_HISTORICAL_FROZEN_PROGRAM_ONLY_EXPLORATORY",
            "asof_dates_requested":days,
            "asof_snapshots":[],"failed_dates":[],
            "risk_status":"NOT_TRADABLE_UNREVIEWED_CANDIDATES",
            "rules":{"future_bars_only_for_outcomes":True,
                "original_git_worktree_at_publish_sha":True,
                "does_not_reconstruct_future_financial_expectations":True,
                "new_candidates_require_model_review":True,
                "official_workflow_untouched":True},
            "limitations":[
                "Historical eligible universe and industry confirmation depend on actual as-of formal records",
                "Only 1/2-day outcomes attempted; missing future sessions are not fabricated",
                "New V4 candidates lack complete as-of business research and cannot be traded on this evidence",
                "Program code is current declared V4 hypothesis applied retrospectively, not a strategy actually published on that date",
                "Small samples and overlapping industry/stock dates prevent performance significance claims"]}
    for day in days:
        entry=published.get(day)
        if not entry:
            output["failed_dates"].append({"date":day,"reason":"NO_ORIGINAL_RANKABLE_FORMAL_COMMIT"})
            continue
        formal=entry["formal"]
        sha=entry["sha"]
        with tempfile.TemporaryDirectory(prefix="v4-historical-") as tmp:
            worktree=Path(tmp)/"snapshot"
            try:
                git(root,"worktree","add","--detach",str(worktree),sha)
                screen=Path(tmp)/"v4-historical-screen-shadow.json"
                subprocess.run([
                    "python",str(worktree/"scripts/build_trend_buy_manual_research.py"),
                    "--evidence",str(worktree/"research/trend_buy_company_reviews/latest.json"),
                    "--output",str(screen)],cwd=worktree,check=True,
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                result=Path(tmp)/"v4-historical-result-shadow.json"
                subprocess.run([
                    "python",str(root/"experiments/trend_buy_v4_python_prescreen_shadow.py"),
                    "--root",str(worktree),"--screen",str(screen),
                    "--output",str(result)],cwd=root,check=True,
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                screen_json=json.loads(screen.read_text(encoding="utf-8"))
                v4=json.loads(result.read_text(encoding="utf-8"))
                if (screen_json.get("trade_date")!=day or v4.get("asof_date")!=day
                        or show_json(root,sha,"data/low_risk/index.json").get("trade_date")!=day):
                    raise ValueError("original_frozen_date_mismatch")
                groups=[]
                for group in v4["industry_groups"]:
                    baseline=group["original_research_codes"]
                    trial=group["v4_research_codes"]
                    companies={c["code"]:c for c in group["selected_candidates"]}
                    old_prices={}
                    frozen_index=show_json(root,sha,"data/low_risk/index.json")
                    # Compare only research selection and frozen price outcomes,
                    # not whether unreviewed candidates deserve a recommendation.
                    from trend_buy_v4_python_prescreen_shadow import frozen_industry_rows
                    rows=frozen_industry_rows(worktree,frozen_index,
                                              group["industry_code"],day)
                    old_prices={r["code"]:r["price"] for r in rows
                                if r["code"] in set(baseline)|set(trial)}
                    results={}
                    issues={}
                    for code in set(baseline)|set(trial):
                        moves,error=future_returns(root,code,day,old_prices.get(code))
                        if error:issues[code]=error
                        else:results[code]=moves
                    means={}
                    for horizon in ("1","2"):
                        if (baseline and trial
                            and all(code in results and results[code][horizon] is not None
                                    for code in set(baseline)|set(trial))):
                            oldavg=sum(results[code][horizon] for code in baseline)/len(baseline)
                            newavg=sum(results[code][horizon] for code in trial)/len(trial)
                            means[horizon]={
                                "original_pre_screen_mean_return_pct":round(oldavg,4),
                                "v4_unreviewed_mean_return_pct":round(newavg,4),
                                "v4_minus_original_pp":round(newavg-oldavg,4)}
                        else:
                            means[horizon]=None
                    groups.append({
                        "industry_code":group["industry_code"],
                        "industry_name":group["industry_name"],
                        "original":baseline,"v4":trial,
                        "new_model_reviews_needed":group["new_research_required_codes"],
                        "original_hard_eligible":group["original_hard_eligible"],
                        "eligible_with_verified_history":group["eligible_with_new_technical_evidence"],
                        "excluded_due_history":group["history_exclusions"],
                        "possible_unreviewed_basket_outcome":means,
                        "outcome_exclusions":issues,
                    })
                output["asof_snapshots"].append({
                    "date":day,"source_commit":sha,
                    "original_published_at":entry["published_at"],
                    "groups":groups,
                    "historical_official_theme_count":len(formal["top5_by_theme"])})
            except (subprocess.CalledProcessError,ValueError,OSError) as ex:
                msg=(ex.stderr[-1200:] if isinstance(ex,subprocess.CalledProcessError)
                     and isinstance(ex.stderr,str) else str(ex))
                output["failed_dates"].append({
                    "date":day,"source_commit":sha,
                    "reason":"ASOF_RECONSTRUCTION_FAILED",
                    "details":msg})
            finally:
                if worktree.exists():
                    try:git(root,"worktree","remove","--force",str(worktree))
                    except subprocess.CalledProcessError:pass
    return output


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--dates",default="2026-11-03,2026-11-04,2026-11-05")
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    dates=[x.strip() for x in args.dates.split(",") if x.strip()]
    if not dates or len(dates)>10 or len(dates)!=len(set(dates)):
        raise ValueError("valid_distinct_dates_required")
    path=args.output.resolve()
    if ("shadow" not in str(path).lower()
            or any(x in str(path) for x in ("trend_buy_formal_result","trend_buy_handoff"))):
        raise ValueError("shadow_only_output_required")
    out=run(ROOT,dates)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",
                    encoding="utf-8")
    print("V4_HISTORICAL_COVERAGE "+json.dumps({
        "dates":len(out["asof_snapshots"]),
        "group_count":sum(len(x["groups"]) for x in out["asof_snapshots"]),
        "failed":out["failed_dates"],"new_candidate_codes":{
            x["date"]:sorted({code for g in x["groups"]
                              for code in g["new_model_reviews_needed"]})
            for x in out["asof_snapshots"]}
    },ensure_ascii=False))


if __name__=="__main__":
    main()
