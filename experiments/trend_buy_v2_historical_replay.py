#!/usr/bin/env python3
"""Point-in-time published-cohort replay for relative-entry shadow ranking.

Historical inputs are the ORIGINAL git commits of formal research and frozen
sector financial rows. Forward daily prices are consulted ONLY for OUTCOMES.
This is an indicative next-open mark-to-market study, not a fill/stop backtest.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta
import json
import math
from pathlib import Path
import statistics
import subprocess
from zoneinfo import ZoneInfo

from trend_buy_v2_relative_entry_shadow import rerank_formal, numeric, positive
from trend_buy_v2_structural_ablation import rerank_structural

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Asia/Shanghai")
FORMAL_PATH = "research/trend_buy_formal_result.json"
HORIZONS = (1, 2, 3, 5, 10)


def git(args, repo=ROOT):
    return subprocess.run(["git", *args], cwd=repo, check=True,
                          text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE).stdout


def historical_file(commit, path, repo=ROOT):
    try:
        return json.loads(git(["show", f"{commit}:{path}"], repo))
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return None


def published_snapshots(repo=ROOT, min_date="2026-10-09", max_date="2026-11-04", policy="EARLIEST_COMPLETE"):
    """Earliest completed original publication per trade date, not hindsight reruns.

    Publication must be within 36 hours after the as-of session's 15:00 close;
    this deliberately excludes archived/backfilled retrospective selections.
    """
    if policy not in ("EARLIEST_COMPLETE", "FIRST_RANKABLE"):
        raise ValueError("unknown_publication_policy")
    raw = git(["log", "--format=%H%x09%cI", "--", FORMAL_PATH], repo)
    accepted, rejected = {}, []
    for line in reversed(raw.splitlines()):
        sha, timestamp = line.strip().split("\t")
        formal = historical_file(sha, FORMAL_PATH, repo)
        if not isinstance(formal, dict):
            continue
        day = formal.get("trade_date")
        if not (isinstance(day, str) and min_date <= day <= max_date):
            continue
        if formal.get("status") != "COMPLETE" or formal.get("production_eligible") is False:
            rejected.append({"date": day, "reason": "not_complete_or_not_eligible"})
            continue
        try:
            release = datetime.fromisoformat(timestamp).astimezone(TZ)
            close_time = datetime.fromisoformat(day + "T15:00:00+08:00")
        except ValueError:
            rejected.append({"date": day, "reason": "malformed_date"})
            continue
        if not (close_time <= release <= close_time + timedelta(hours=36)):
            rejected.append({"date": day, "reason": "publication_outside_36_hours"})
            continue
        if (policy == "FIRST_RANKABLE" and not any(
                isinstance(g.get("items"), list) and len(g["items"]) >= 1
                for g in formal.get("top5_by_theme") or [])):
            rejected.append({"date": day, "reason": "rankless_complete_before_first_rankable",
                             "commit": sha})
            continue
        if day not in accepted:
            accepted[day] = {"date": day, "commit": sha,
                             "published_at": release.isoformat(),
                             "formal": formal}
    return sorted(accepted.values(), key=lambda x: x["date"]), rejected


def historical_fundamentals(snapshot, repo=ROOT):
    """Compute current scoring formula from THEN-frozen sector rows, not today's values."""
    date, sha, formal = snapshot["date"], snapshot["commit"], snapshot["formal"]
    index = historical_file(sha, "data/low_risk/index.json", repo)
    if not isinstance(index, dict) or index.get("trade_date") != date:
        return {}, "HISTORICAL_FROZEN_INDEX_MISSING_OR_MISMATCHED"
    # The V2 experiment intentionally uses the current declared peer-score
    # formula, applied to historical materialized facts, not future financials.
    import sys
    scripts = str(repo / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from build_trend_buy_manual_research import hard_reason, scores
    codes = {x["code"]: x["industry_code"]
             for x in (formal.get("ready") or []) + (formal.get("wait") or [])
             if x.get("industry_code")}
    industries = sorted(set(codes.values()))
    found = {}
    for industry in industries:
        meta = (index.get("industries") or {}).get(industry)
        if not meta:
            continue
        path = meta.get("legacy_file") or meta.get("file")
        frozen = historical_file(sha, path, repo) if path else None
        if not isinstance(frozen, dict) or frozen.get("trade_date") != date:
            continue
        eligible = [x for x in frozen.get("companies", []) if hard_reason(x) is None]
        for row, score in zip(eligible, scores(eligible)):
            found[row["code"]] = score[0]
    coverage = sum(1 for k in codes if k in found)
    return found, f"HISTORICAL_FROZEN_FUNDAMENTALS_{coverage}_OF_{len(codes)}"


def stock_history(root, code, cache):
    prefix = code[:4]
    if prefix not in cache:
        path = root / "data/history_shards" / (prefix + ".json")
        cache[prefix] = (json.loads(path.read_text(encoding="utf-8"))
                         if path.exists() else {})
    stock = (cache[prefix].get("stocks") or {}).get(code) or {}
    rows = {}
    for r in stock.get("history") or []:
        d = r.get("date")
        if (isinstance(d, str) and positive(r.get("close"))
                and positive(r.get("high")) and positive(r.get("low"))):
            rows[d] = r
    return rows, stock.get("history_basis")


def outcome(row, next_date, target_date, calendar, histories):
    code = row["code"]
    h, basis = histories[code]
    if next_date not in h or target_date not in h or row["date"] not in h:
        return None, "MISSING_REQUIRED_PRICE_DATE"
    asof_close = h[row["date"]]["close"]
    frozen_close = row["current_price"]
    # An unaligned adjusted history can create fake returns. Skip, do not patch.
    if abs(asof_close / frozen_close - 1) > .015:
        return None, "ASOF_CLOSE_VS_HISTORY_BASIS_MISMATCH"
    entry = h[next_date].get("open")
    if not positive(entry):
        return None, "NEXT_OPEN_MISSING"
    dates = [d for d in calendar if next_date <= d <= target_date]
    if any(d not in h for d in dates):
        return None, "MISSING_INTERMEDIATE_SESSION"
    close = h[target_date]["close"]
    low = min(h[d]["low"] for d in dates)
    high = max(h[d]["high"] for d in dates)
    gap_pct = 100 * (entry / asof_close - 1)
    first_bar = h[next_date]
    # Near-limit one-price open is a *possible* no-fill, not proof of an
    # unfillable market order. ST/board special cases remain unverified.
    limit_pct = (20 if code.startswith(("300", "301", "688", "689"))
                 else 30 if code.startswith(("8", "4")) else 10)
    one_price = (positive(first_bar.get("high"))
                 and positive(first_bar.get("low"))
                 and abs(first_bar["high"] / first_bar["low"] - 1) < .0006)
    locked_up_proxy = bool(gap_pct >= limit_pct - .25 and one_price)
    return {
        "return_pct": 100 * (close / entry - 1),
        "open_gap_pct": gap_pct,
        "possible_price_limit_locked_open": locked_up_proxy,
        "mae_pct": 100 * (low / entry - 1),
        "mfe_pct": 100 * (high / entry - 1),
        "entry_open": entry,
        "history_basis": basis,
    }, None


def published_before_next_open(published_at, next_session_date):
    """A ranking becomes observable only AFTER the actual Git publication."""
    release = datetime.fromisoformat(published_at).astimezone(TZ)
    open_time = datetime.fromisoformat(next_session_date + "T09:30:00+08:00")
    return release <= open_time


def asof_regime(row):
    """As-of market structure for diagnostics, never a trade filter."""
    ctx = row.get("technical_context") or {}
    ma60, price = ctx.get("ma60"), row.get("current_price")
    slope = ctx.get("ma20_slope_5d_pct")
    if not (positive(price) and positive(ma60) and numeric(slope)):
        return "UNKNOWN_STRUCTURE"
    if (row.get("trend_phase") == "REPAIRING"
            and price < ma60 and slope < 0):
        return "REPAIR_BELOW_MA60_FALLING_MA20"
    return "OTHER_VERIFIED_STRUCTURE"


def pairwise_order_accuracy(order, moves):
    """Rank pair concordance with *future* returns (outcome only).

    Earlier-ranked stocks should outperform later-ranked stocks. A return tie
    counts half. All pairs in a complete cohort must be observed.
    """
    if len(order) < 2 or len(set(order)) != len(order):
        raise ValueError("valid_unique_rank_order_required")
    if any(x not in moves for x in order):
        raise ValueError("missing_pairwise_outcome")
    wins, pairs = 0.0, 0
    for i, first in enumerate(order):
        for second in order[i+1:]:
            a,b = moves[first]["return_pct"], moves[second]["return_pct"]
            wins += 1.0 if a > b else .5 if abs(a-b) <= 1e-10 else 0.0
            pairs += 1
    return wins / pairs


def mean(rows, key):
    return statistics.mean(r[key] for r in rows)


def summarize(samples):
    by_horizon = []
    for horizon in HORIZONS:
        rows = [x for x in samples if x["horizon"] == horizon]
        if not rows:
            by_horizon.append({"horizon": horizon, "cohorts": 0})
            continue
        top1_diffs = [x["v2_top1_return_pct"] - x["old_top1_return_pct"] for x in rows]
        top3_diffs = [x["v2_top3_return_pct"] - x["old_top3_return_pct"] for x in rows]
        pairwise_diffs = [100 * (x["v2_pairwise_accuracy"] - x["old_pairwise_accuracy"])
                          for x in rows]
        changed = [x for x in rows if x["old_top1"] != x["v2_top1"]]
        changed_diffs = [x["v2_top1_return_pct"] - x["old_top1_return_pct"]
                         for x in changed]
        by_horizon.append({
            "horizon": horizon, "cohorts": len(rows),
            "distinct_dates": len({x["asof"] for x in rows}),
            "distinct_themes": len({x["theme"] for x in rows}),
            "old_top1_avg_return_pct": round(statistics.mean(x["old_top1_return_pct"] for x in rows), 3),
            "v2_top1_avg_return_pct": round(statistics.mean(x["v2_top1_return_pct"] for x in rows), 3),
            "top1_mean_difference_pp": round(statistics.mean(top1_diffs), 3),
            "top1_median_difference_pp": round(statistics.median(top1_diffs), 3),
            "v2_top1_won_fraction": round(sum(d > 0 for d in top1_diffs) / len(rows), 3),
            "changed_top1_cohorts": len(changed),
            "v2_top1_won_fraction_given_changed": (
                round(sum(d > 0 for d in changed_diffs) / len(changed_diffs), 3)
                if changed_diffs else None),
            "top3_mean_difference_pp": round(statistics.mean(top3_diffs), 3),
            "old_pairwise_accuracy_pct": round(100 * statistics.mean(
                x["old_pairwise_accuracy"] for x in rows), 3),
            "v2_pairwise_accuracy_pct": round(100 * statistics.mean(
                x["v2_pairwise_accuracy"] for x in rows), 3),
            "pairwise_accuracy_difference_pp": round(statistics.mean(pairwise_diffs), 3),
            "old_top1_mean_mae_pct": round(statistics.mean(x["old_top1_mae_pct"] for x in rows), 3),
            "v2_top1_mean_mae_pct": round(statistics.mean(x["v2_top1_mae_pct"] for x in rows), 3),
        })
    return by_horizon


def replay(repo=ROOT, min_date="2026-10-09", max_date="2026-11-04", ranking="V2", snapshot_policy="EARLIEST_COMPLETE"):
    if ranking not in ("V2","V21_STRUCTURAL"):
        raise ValueError("unknown_shadow_ranker")
    snapshots, publication_rejections = published_snapshots(repo, min_date, max_date, snapshot_policy)
    stock_cache, stock_set, cohorts, coverage_audit = {}, set(), [], []
    for snap in snapshots:
        formal = snap["formal"]
        peers, peer_status = historical_fundamentals(snap, repo)
        try:
            v2 = (rerank_structural(formal, peers)
                  if ranking=="V21_STRUCTURAL" else rerank_formal(formal, peers))
        except (ValueError, KeyError) as e:
            cohorts.append({"date": snap["date"], "invalid": str(e), "commit": snap["commit"]})
            coverage_audit.extend({
                "date":snap["date"], "theme":g.get("trend_name"),
                "published_members":len(g.get("items") or []),
                "eligibility":"RANKER_EXCEPTION", "error":str(e)}
                for g in formal.get("top5_by_theme") or [])
            continue
        baseline = {x["trend_name"]: x for x in formal.get("top5_by_theme") or []}
        for group in v2["groups"]:
            theme = group["trend_name"]
            old = [x["code"] for x in baseline[theme]["items"]]
            new = [x["code"] for x in group["items"]]
            if len(old) < 2 or len(old) != len(new) or set(old) != set(new):
                coverage_audit.append({
                    "date":snap["date"], "theme":theme,
                    "published_members":len(old),
                    "eligibility":"NOT_COMPARABLE_LT_2_OR_MISMATCH"})
                continue
            coverage_audit.append({
                "date":snap["date"], "theme":theme,
                "published_members":len(old),
                "eligibility":"VALID_RANKED_COHORT"})
            stock_set.update(old)
            lookup = {r["code"]: r for r in (formal.get("ready") or []) + (formal.get("wait") or [])}
            market_states=sorted({lookup[code].get("market_state") or "UNKNOWN" for code in old})
            market_state_category=("CONFIRMED_ONLY"
                                   if market_states==["趋势确认"]
                                   else "NONCONFIRMED_OR_MIXED")
            cohorts.append({
                "date": snap["date"], "theme": theme,
                "commit": snap["commit"],
                "published_at": snap["published_at"],
                "old_codes": old, "v2_codes": new,
                "peers": peer_status,
                "market_state_category":market_state_category,
                "market_states":market_states,
                "protocol_epoch": ("PRE_2026_10_27" if snap["date"]<"2026-10-27"
                                    else "CONFIRMED_ONLY_2026_10_27_PLUS"),
                "asof_regimes": {code: asof_regime(lookup[code]) for code in old},
                "rows": {code: {"code": code, "date": snap["date"],
                                "current_price": lookup[code]["current_price"]}
                         for code in old},
            })
    cache = {}
    histories = {code: stock_history(repo, code, cache) for code in stock_set}
    calendar = sorted({day for rows, _ in histories.values() for day in rows})
    samples, skipped, outcome_exclusions = [], defaultdict(int), []
    for cohort in cohorts:
        if "invalid" in cohort:
            skipped["INVALID_HISTORICAL_FORMAL"] += 1
            continue
        date, old, new = cohort["date"], cohort["old_codes"], cohort["v2_codes"]
        if date not in calendar:
            skipped["ASOF_DATE_MISSING_FROM_HISTORY"] += 1
            continue
        future = [d for d in calendar if d > date]
        # Published after the next open is NOT a trade known at that open.
        # Git's first publication time is a stronger gate than as-of date.
        if future and not published_before_next_open(
                cohort["published_at"], future[0]):
            skipped["PUBLICATION_AFTER_NEXT_SESSION_OPEN"] += len(HORIZONS)
            outcome_exclusions.append({"date":date,"theme":cohort["theme"],
                "reason":"PUBLICATION_AFTER_NEXT_SESSION_OPEN"})
            continue
        for horizon in HORIZONS:
            if len(future) < horizon:
                skipped[f"NOT_YET_{horizon}_SESSIONS"] += 1
                outcome_exclusions.append({"date":date,"theme":cohort["theme"],
                    "horizon":horizon,"reason":"NOT_ENOUGH_FUTURE_SESSIONS"})
                continue
            next_date, target_date = future[0], future[horizon-1]
            moves = {}
            errors = set()
            missing_by_code={}
            for code in old:
                result, error = outcome(cohort["rows"][code], next_date, target_date,
                                        calendar, histories)
                if error:
                    errors.add(error)
                    missing_by_code[code]=error
                else:
                    moves[code] = result
            # Complete-case cohort avoids silently selecting only survivors.
            if len(moves) != len(old):
                skipped["INCOMPLETE_COHORT:" + ",".join(sorted(errors))] += 1
                outcome_exclusions.append({"date":date,"theme":cohort["theme"],
                    "horizon":horizon,
                    "reason":"INCOMPLETE_COHORT",
                    "problem_codes":missing_by_code})
                continue
            old_top1, v2_top1 = moves[old[0]], moves[new[0]]
            samples.append({
                "asof": date, "theme": cohort["theme"], "horizon": horizon,
                "published_at": cohort["published_at"], "commit": cohort["commit"],
                "future_first_session": next_date, "future_target_session": target_date,
                "fundamentals": cohort["peers"],
                "market_state_category": cohort["market_state_category"],
                "market_states": cohort["market_states"],
                "protocol_epoch": cohort["protocol_epoch"],
                "published_member_count":len(old),
                "old_top1": old[0], "v2_top1": new[0],
                "old_pairwise_accuracy": round(pairwise_order_accuracy(old, moves), 6),
                "v2_pairwise_accuracy": round(pairwise_order_accuracy(new, moves), 6),
                "old_top1_regime": cohort["asof_regimes"][old[0]],
                "v2_top1_regime": cohort["asof_regimes"][new[0]],
                "old_top1_open_gap_pct": round(old_top1["open_gap_pct"], 5),
                "v2_top1_open_gap_pct": round(v2_top1["open_gap_pct"], 5),
                "old_top1_possible_limit_locked": old_top1["possible_price_limit_locked_open"],
                "v2_top1_possible_limit_locked": v2_top1["possible_price_limit_locked_open"],
                "old_top1_return_pct": round(old_top1["return_pct"], 5),
                "v2_top1_return_pct": round(v2_top1["return_pct"], 5),
                "old_top1_mae_pct": round(old_top1["mae_pct"], 5),
                "v2_top1_mae_pct": round(v2_top1["mae_pct"], 5),
                "old_top3_return_pct": round(statistics.mean(moves[c]["return_pct"]
                                                             for c in old[:3]), 5),
                "v2_top3_return_pct": round(statistics.mean(moves[c]["return_pct"]
                                                            for c in new[:3]), 5),
                "sector_equal_weight_return_pct": round(statistics.mean(
                    moves[c]["return_pct"] for c in old), 5),
            })
    summary = summarize(samples)
    achieved = defaultdict(lambda: defaultdict(set))
    for r in samples:
        achieved[r["theme"]][r["horizon"]].add(r["asof"])
    published_by_theme = defaultdict(set)
    comparable_by_theme = defaultdict(set)
    for r in coverage_audit:
        published_by_theme[r["theme"]].add(r["date"])
        if r["eligibility"] == "VALID_RANKED_COHORT":
            comparable_by_theme[r["theme"]].add(r["date"])
    theme_coverage = [
        {"theme":theme,
         "published_dates":sorted(published_by_theme[theme]),
         "comparable_dates":sorted(comparable_by_theme[theme]),
         "completed_horizon_counts":{
             str(h):len(achieved[theme][h]) for h in HORIZONS}}
        for theme in sorted(published_by_theme)]
    # Not enough independent trading dates to claim stable model improvement.
    enough = (len(summary) == len(HORIZONS)
              and all(x.get("distinct_dates", 0) >= 20
                      and x.get("cohorts", 0) >= 40 for x in summary))
    return {
        "mode": "HISTORICAL_SHADOW_INDICATIVE_NOT_TRADING_BACKTEST",
        "ranking":ranking,
        "snapshot_policy":snapshot_policy,
        "strategy": "next_session_open_to_horizon_close_no_cost_or_fill_constraints",
        "selection": ("first_rankable_formal_commit_within_36h"
                      if snapshot_policy=="FIRST_RANKABLE"
                      else "earliest_complete_formal_commit_within_36h"),
        "asof_dates": [x["date"] for x in snapshots],
        "published_snapshots": len(snapshots), "cohort_count": len([
            x for x in cohorts if "invalid" not in x]),
        "summary": summary, "samples": samples,
        "theme_coverage":theme_coverage,
        "coverage_audit":coverage_audit,
        "outcome_exclusions":outcome_exclusions,
        "skipped": dict(sorted(skipped.items())),
        "publication_rejections": publication_rejections[:30],
        "enough_independent_evidence_for_production_upgrade": enough,
        "limitations": [
            "Overlapping cohorts and repeated tickers reduce independent observations",
            "Historical bars may be backward-adjusted and corporate action mismatches are excluded",
            "Next-open hypothetical is not an actual fill; no price-limit, volume, fees or slippage simulation",
            "Earliest formal publication strictly precedes assumed next-session open; otherwise skipped",
            "No trade invalidation stop or first-touch 1.5R outcomes are claimed",
            "Next-open gap and possible one-price-limit-up are diagnostic proxies, not verified fills or price-limit status",
            "Pre-screen membership fixed at previously published Top5: dual-channel extra candidates need review",
            "Frozen financial inputs missing on some dates are marked neutral rather than backfilled",
            "Historical scoring formula is experimental and was not selected using outcome optimization",
            "FIRST_RANKABLE uses earliest complete ranked publication and flags earlier rankless posts; it is NOT the strict first-complete policy",
            "Changing protocol epochs (Oct 9 older pre-screen and Oct 27 confirmed-only) are NOT homogeneous strategy observations",
            "2-company cohorts contribute only one pair to pairwise concordance and are not comparable to 5-company cohorts without stratification",
        ],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-date", default="2026-10-09")
    ap.add_argument("--snapshot-policy", choices=("EARLIEST_COMPLETE","FIRST_RANKABLE"),
                    default="EARLIEST_COMPLETE")
    ap.add_argument("--ranking", choices=("V2","V21_STRUCTURAL"), default="V2")
    ap.add_argument("--max-date", default="2026-11-04")
    ap.add_argument("--output", type=Path, help="Optional shadow-only JSON output")
    args = ap.parse_args()
    result = replay(ROOT, args.min_date, args.max_date, args.ranking, args.snapshot_policy)
    output = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        path = args.output.resolve()
        if "shadow" not in str(path).lower() or (
            "trend_buy_formal_result" in str(path) or "trend_buy_handoff" in str(path)
        ):
            raise ValueError("shadow_output_required")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output, encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in (
        "samples", "publication_rejections", "coverage_audit", "outcome_exclusions"
    )}, ensure_ascii=False))


if __name__ == "__main__":
    main()
