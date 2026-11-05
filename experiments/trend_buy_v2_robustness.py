#!/usr/bin/env python3
"""Sensitivity analysis of historical shadow ranking without any new trade signals.

Read two point-in-time replay JSON files. The only future data are outcomes
that have already been sealed into those files. Do NOT use this module to
optimize scoring weights or decide the historical selection universe.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from itertools import product
import json
import math
from pathlib import Path
import statistics

EXPECTED_RANKINGS = ("V2", "V21_STRUCTURAL")
HORIZONS = (3, 5, 10)


def avg(xs):
    return statistics.mean(xs) if xs else None


def median(xs):
    return statistics.median(xs) if xs else None


def round_or_none(x):
    return round(x, 4) if x is not None else None


def diff_pp(r):
    return r["v2_top1_return_pct"] - r["old_top1_return_pct"]


def day_clusters(rows):
    groups = defaultdict(list)
    for r in rows:
        groups[r["asof"]].append(diff_pp(r))
    return {k: avg(v) for k, v in sorted(groups.items())}


def exact_sign_flip_p(day_values):
    """Exploratory paired/date-cluster sign permutation, NOT causal inference."""
    xs = list(day_values)
    if not 5 <= len(xs) <= 16:
        return None
    abs_mean = abs(avg(xs))
    total, extreme = 0, 0
    for signs in product((-1, 1), repeat=len(xs)):
        sample_mean = abs(sum(s * x for s, x in zip(signs, xs)) / len(xs))
        total += 1
        if sample_mean + 1e-12 >= abs_mean:
            extreme += 1
    return round(extreme / total, 5)


def no_overlap_by_theme(rows):
    """One event per theme until prior horizon has ended (first chronological)."""
    last_target = {}
    selected = []
    for r in sorted(rows, key=lambda x: (x["asof"], x["theme"])):
        theme = r["theme"]
        # same trade date could have only one row per theme in formal snapshots
        if theme in last_target and r["asof"] <= last_target[theme]:
            continue
        selected.append(r)
        last_target[theme] = r["future_target_session"]
    return selected


def first_distinct_switch(rows):
    """One earliest sample per (theme, old top1, new top1) tuple."""
    seen, distinct = set(), []
    for r in sorted(rows, key=lambda x: (x["asof"], x["theme"])):
        key = (r["theme"], r["old_top1"], r["v2_top1"])
        if key in seen:
            continue
        seen.add(key)
        distinct.append(r)
    return distinct


def by_group(rows, field):
    buckets = defaultdict(list)
    for r in rows:
        buckets[r.get(field, "UNKNOWN")].append(diff_pp(r))
    return {
        key: {"n": len(v), "mean_diff_pp": round_or_none(avg(v)),
              "median_diff_pp": round_or_none(median(v))}
        for key, v in sorted(buckets.items())
    }


def robust_summary(rows):
    if not rows:
        return {"cohorts": 0}
    changed = [r for r in rows if r["old_top1"] != r["v2_top1"]]
    days = day_clusters(rows)
    nonoverlap = no_overlap_by_theme(rows)
    dedup = first_distinct_switch(rows)
    leave_day_out = [
        avg([v for d2, v in days.items() if d2 != d])
        for d in days
    ] if len(days) > 1 else []
    chronological = sorted(days.items())
    first_cut = max(1, int(len(chronological) * 0.6))
    early, late = chronological[:first_cut], chronological[first_cut:]
    executable_proxy_available = [
        r for r in rows
        if all(isinstance(r.get(k), (int, float))
               and not isinstance(r.get(k), bool)
               and math.isfinite(r[k])
               for k in ("old_top1_open_gap_pct", "v2_top1_open_gap_pct"))
    ]
    no_large_gap = [
        r for r in executable_proxy_available
        if r["old_top1_open_gap_pct"] < 5
        and r["v2_top1_open_gap_pct"] < 5
        and not r.get("old_top1_possible_limit_locked")
        and not r.get("v2_top1_possible_limit_locked")
    ]
    possible_limit = [
        r for r in executable_proxy_available
        if r.get("old_top1_possible_limit_locked")
        or r.get("v2_top1_possible_limit_locked")
    ]
    return {
        "cohorts": len(rows),
        "open_gap_diagnostic_coverage": len(executable_proxy_available),
        "v2_top1_mean_next_open_gap_pct": (
            round_or_none(avg([r["v2_top1_open_gap_pct"]
                               for r in executable_proxy_available]))),
        "old_top1_mean_next_open_gap_pct": (
            round_or_none(avg([r["old_top1_open_gap_pct"]
                               for r in executable_proxy_available]))),
        "both_top1_open_gap_below_5pct_cohorts": len(no_large_gap),
        "both_top1_open_gap_below_5pct_mean_diff_pp": (
            round_or_none(avg([diff_pp(r) for r in no_large_gap]))),
        "possible_one_price_limit_open_cohorts": len(possible_limit),
        "distinct_dates": len(days),
        "distinct_themes": len({r["theme"] for r in rows}),
        "changed_top1_cohorts": len(changed),
        "equal_cohort_mean_diff_pp": round_or_none(avg([diff_pp(r) for r in rows])),
        "equal_date_mean_diff_pp": round_or_none(avg(list(days.values()))),
        "equal_date_median_diff_pp": round_or_none(median(list(days.values()))),
        "date_jackknife_mean_range_pp": (
            [round(min(leave_day_out),4), round(max(leave_day_out),4)]
            if leave_day_out else None),
        "date_cluster_exploratory_signflip_p": exact_sign_flip_p(days.values()),
        "changed_top1_only_mean_diff_pp": (
            round_or_none(avg([diff_pp(r) for r in changed]))),
        "changed_top1_wins_losses_ties": {
            "wins": sum(diff_pp(r) > 0 for r in changed),
            "losses": sum(diff_pp(r) < 0 for r in changed),
            "ties": sum(abs(diff_pp(r)) < 1e-8 for r in changed),
        },
        "unique_theme_old_new_tuple_cohorts": len(dedup),
        "unique_theme_old_new_tuple_mean_diff_pp": (
            round_or_none(avg([diff_pp(r) for r in dedup]))),
        "nonoverlap_by_theme_cohorts": len(nonoverlap),
        "nonoverlap_by_theme_mean_diff_pp": (
            round_or_none(avg([diff_pp(r) for r in nonoverlap]))),
        "early_dates": len(early),
        "early_dates_mean_pp": round_or_none(avg([v for _,v in early])),
        "later_dates": len(late),
        "later_dates_mean_pp": round_or_none(avg([v for _,v in late])),
        "by_v2_top1_asof_regime": by_group(rows, "v2_top1_regime"),
        "by_theme": by_group(rows, "theme"),
        "worst_5_changed": [
            {"asof": r["asof"], "theme": r["theme"],
             "old_top1": r["old_top1"], "candidate_top1": r["v2_top1"],
             "diff_pp": round(diff_pp(r),4)}
            for r in sorted(changed, key=diff_pp)[:5]
        ],
    }


def run(reports):
    ranking_set = set(reports)
    if ranking_set != set(EXPECTED_RANKINGS):
        raise ValueError("both_v2_and_v21_reports_required")
    combined = {"mode": "SHADOW_HISTORICAL_ROBUSTNESS_NON_TRADE",
                "versions": {},
                "comparability": {},
                "promotion_eligible": False,
                "limitations": [
                    "Day/date clusters are not independent market regimes; adjacent windows overlap",
                    "Sign-flip p is exploratory, not evidence of independent causal strategy effect",
                    "Chronological early/later splits are NOT held-out strategy discovery data",
                    "Next-open mark-to-market outcome is not a tradable fill/stop result",
            "Open gap <5% is a descriptive sensitivity subset, not a guaranteed fill; board/ST limit status unverified",
                    "Small date count, duplicate companies, missing previous as-of facts and survivor filtering",
                    "A negative result cannot establish that the original production method is profitable",
                ]}
    keys_by_version = {}
    for name in EXPECTED_RANKINGS:
        report = reports[name]
        if (report.get("ranking") != name or
                report.get("mode") != "HISTORICAL_SHADOW_INDICATIVE_NOT_TRADING_BACKTEST"):
            raise ValueError("unverified_replay_provenance:" + name)
        combined["versions"][name] = {
            "asof_dates": report.get("asof_dates"),
            "skipped": report.get("skipped"),
            "by_horizon": {},
        }
        keys = set()
        for horizon in HORIZONS:
            rows = [x for x in report.get("samples", []) if x.get("horizon") == horizon]
            for r in rows:
                key = (r["asof"], r["theme"], horizon)
                if key in keys:
                    raise ValueError("duplicate_date_theme_horizon:" + name)
                keys.add(key)
                if not (r["future_first_session"] > r["asof"]
                        and r["future_target_session"] >= r["future_first_session"]):
                    raise ValueError("invalid_outcome_dates:" + name)
            combined["versions"][name]["by_horizon"][str(horizon)] = robust_summary(rows)
        keys_by_version[name] = keys
    combined["comparability"]["identical_cohort_keys"] = (
        keys_by_version["V2"] == keys_by_version["V21_STRUCTURAL"])
    combined["comparability"]["shared_cohort_keys"] = len(
        keys_by_version["V2"] & keys_by_version["V21_STRUCTURAL"])
    if not combined["comparability"]["identical_cohort_keys"]:
        combined["limitations"].append(
            "Different complete-case cohorts mean per-version comparisons are not paired")
    return combined


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--v2", type=Path, required=True)
    p.add_argument("--v21", type=Path, required=True)
    p.add_argument("--output", type=Path)
    opts = p.parse_args()
    r2 = json.loads(opts.v2.read_text(encoding="utf-8"))
    r21 = json.loads(opts.v21.read_text(encoding="utf-8"))
    result = run({"V2": r2, "V21_STRUCTURAL": r21})
    output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if opts.output:
        path = opts.output.resolve()
        if "shadow" not in str(path).lower() or any(
                x in str(path) for x in ("trend_buy_formal_result",
                                        "trend_buy_handoff")):
            raise ValueError("only_shadow_output_supported")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output, encoding="utf-8")
    print(json.dumps({
        "mode": result["mode"],
        "promotion_eligible": result["promotion_eligible"],
        "paired": result["comparability"],
        "summary": {k: {
            h: {x: b.get(x) for x in (
                "cohorts", "distinct_dates", "equal_cohort_mean_diff_pp",
                "equal_date_mean_diff_pp", "changed_top1_only_mean_diff_pp",
                "unique_theme_old_new_tuple_cohorts",
                "unique_theme_old_new_tuple_mean_diff_pp",
                "nonoverlap_by_theme_cohorts",
                "nonoverlap_by_theme_mean_diff_pp",
                "date_jackknife_mean_range_pp",
                "both_top1_open_gap_below_5pct_cohorts",
                "both_top1_open_gap_below_5pct_mean_diff_pp",
                "possible_one_price_limit_open_cohorts",
            )} for h,b in v["by_horizon"].items()
        } for k,v in result["versions"].items()},
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
