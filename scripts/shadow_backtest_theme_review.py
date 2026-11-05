#!/usr/bin/env python3
"""Point-in-time, quote-only shadow evaluation of legacy 3 vs grouped 10 reviews.

Historical commits provide each session's quotes and SW3 membership. The static
theme catalog is frozen to its October 11 publication commit. At each decision
date only prior/current archived prices enter discovery. Subsequent prices are
used exclusively for the clearly labeled EX-POST outcome diagnostics.

This is auxiliary DISCOVERY coverage research. It never confirms a trend,
routes to the buy-point system, or writes production registry/handoff files.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from backtest_sector_discovery_asof import (
    asof_features, future_return, load_days,
)
from build_sector_discovery import build as build_sector
from build_theme_evidence import build as build_theme


def group_match(a, b):
    """Compare theme identity or near-identical SW3 coverage, not similar names."""
    if a["source_id"] == b["source_id"]:
        return True
    x, y = set(a["industry_codes"]), set(b["industry_codes"])
    return bool(x and y and len(x & y) / len(x | y) >= .85)


def captured(target, selected):
    return any(group_match(target, item) for item in selected)


def members(index, level3_codes):
    requested = set(level3_codes)
    return {
        str(symbol).zfill(6)
        for symbol, row in index["companies"].items()
        if row.get("mapping_status") == "mapped"
        and row.get("industry_code") in requested
    }


def compact_lead(lead):
    return {
        "rank": lead["rank"], "source_id": lead["source_id"],
        "name": lead["name"], "industry_codes": lead["industry_codes"],
        "score": lead["review_priority_score"],
        "selection_track": lead["selection_track"],
        "persistent_industry_count": lead["persistent_industry_count"],
        "evidence": lead["industry_evidence"],
    }


def summarize_outcomes(outcomes, variant):
    rows = [x for x in outcomes if x["strategy"] == variant]
    summary = {"selected_records": len(rows), "horizons": {}}
    for horizon in (1, 2):
        valid = [x["outcomes"][str(horizon)] for x in rows
                 if x["outcomes"][str(horizon)]["status"] == "OBSERVED"]
        if valid:
            summary["horizons"][str(horizon)] = {
                "observed": len(valid),
                "not_observable_or_incomplete": len(rows) - len(valid),
                "median_forward_return_pct": round(
                    sorted(x["return_pct"] for x in valid)[len(valid)//2], 4),
                "relative_positive_count": sum(x["relative_pct"] > 0 for x in valid),
                "absolute_positive_count": sum(x["return_pct"] > 0 for x in valid),
                "weak_continuation_count": sum(x["weak_continuation_proxy"] for x in valid),
                "weak_continuation_rate": round(
                    sum(x["weak_continuation_proxy"] for x in valid) / len(valid), 4),
            }
        else:
            summary["horizons"][str(horizon)] = {
                "observed": 0, "not_observable_or_incomplete": len(rows),
                "weak_continuation_rate": None}
    return summary


def replay(root, manifest, catalog, start="2026-10-12"):
    days = load_days(root, manifest)
    catalog_date = catalog["catalog_as_of_date"]
    if start < catalog_date:
        raise ValueError("CATALOG_NOT_YET_AVAILABLE_ON_START_DATE")
    if manifest.get("catalog_frozen_commit") is None:
        raise ValueError("CATALOG_COMMIT_PROVENANCE_REQUIRED")
    daily, forward_rows, contexts = [], [], []
    for i, (day, sha, latest, index) in enumerate(days):
        if day < start:
            continue
        if day < catalog_date:
            raise ValueError("ASOF_CATALOG_LOOKAHEAD:" + day)
        if i < 10:
            raise ValueError("INSUFFICIENT_PRIOR_SESSIONS:" + day)
        structure = asof_features(days, i)
        sector_snapshot, sector_audit = build_sector(
            latest, index, structure, review_cap=3)
        args = [latest, index, structure, catalog, sector_audit]
        legacy = build_theme(*args, max_research=3,
                             crosscheck_limit=3, persistence_seats=0)
        current = build_theme(*args, max_research=10,
                              crosscheck_limit=10, persistence_seats=5)
        # A full taxonomy/curated pool is a denominator for coverage checks,
        # not an extra selection strategy or input to any ranked shortlist.
        whole = build_theme(*args, max_research=10,
                            crosscheck_limit=200, persistence_seats=0)
        old3, new10 = legacy["crosscheck_shortlist"], current["crosscheck_shortlist"]
        full = whole["crosscheck_shortlist"]
        persistent = [x for x in full if x["persistent_industry_count"] >= 2]
        if not all(x["industry_codes"] == [v["industry_code"] for v in x["industry_evidence"]]
                   for x in old3 + new10):
            raise ValueError("SW3_EVIDENCE_AND_ROUTING_IDENTITY_MISMATCH:" + day)
        if any("market_state" in x or "in_new_position_priority" in x
               for x in new10):
            raise ValueError("SHADOW_CREATED_FORMAL_AUTHORITY:" + day)
        daily.append({
            "trade_date": day, "source_commit": sha,
            "historical_available_at": "archived_daily_market_commit",
            "model_registry_written": False, "future_inputs_used": False,
            "market_data_status": sector_snapshot["status"],
            "industry_universe_count": sector_audit["industry_count"],
            "old_raw_sw3_seeds": [
                {"name": x["name"], "industry_code": x["id"].split(":")[-1]}
                for x in sector_snapshot["model_research_candidates"]],
            "old3": [compact_lead(x) for x in old3],
            "new10": [compact_lead(x) for x in new10],
            "old3_covers_new": sum(captured(x, new10) for x in old3),
            "new_exclusive_theme_count": sum(not captured(x, old3) for x in new10),
            "persistent_themes_eligible": len(persistent),
            "persistent_themes_captured_old3": sum(captured(x, old3) for x in persistent),
            "persistent_themes_captured_new10": sum(captured(x, new10) for x in persistent),
            "photovoltaic": {
                "old_rank": next((x["rank"] for x in old3 if x["source_id"]
                                 == "SW_L2_TAXONOMY:sw_l2_6305"), None),
                "new_rank": next((x["rank"] for x in new10 if x["source_id"]
                                 == "SW_L2_TAXONOMY:sw_l2_6305"), None),
                "new_track": next((x["selection_track"] for x in new10 if x["source_id"]
                                 == "SW_L2_TAXONOMY:sw_l2_6305"), None),
            }
        })
        contexts.append((i, old3, new10, latest, index))

    for i, old3, new10, latest, index in contexts:
        day, sha, _, _ = days[i]
        for strategy, leads in [("old3", old3), ("new10", new10),
                                ("new_exclusive", [x for x in new10
                                                  if not captured(x, old3)])]:
            for lead in leads:
                stocks = members(index, lead["industry_codes"])
                record = {"trade_date": day, "strategy": strategy,
                          "source_id": lead["source_id"], "name": lead["name"],
                          "selection_track": lead["selection_track"],
                          "member_count": len(stocks), "outcomes": {}}
                for horizon in (1, 2):
                    if i + horizon >= len(days):
                        record["outcomes"][str(horizon)] = {
                            "status": "NOT_YET_OBSERVABLE"}
                        continue
                    future = days[i + horizon][2]
                    perf = future_return(latest, future, stocks)
                    market_set = set(latest["stocks"]) & set(future["stocks"])
                    benchmark = future_return(latest, future, market_set)
                    if perf is None or benchmark is None:
                        record["outcomes"][str(horizon)] = {
                            "status": "INSUFFICIENT_FUTURE_COVERAGE"}
                        continue
                    relative = round(perf - benchmark, 4)
                    record["outcomes"][str(horizon)] = {
                        "status": "OBSERVED", "return_pct": perf,
                        "benchmark_pct": benchmark, "relative_pct": relative,
                        "weak_continuation_proxy": perf <= 0 and relative <= 0}
                forward_rows.append(record)
    if not daily:
        raise ValueError("NO_VALID_EVALUATION_DATES")
    total_persistent = sum(d["persistent_themes_eligible"] for d in daily)
    def ratio(n, d):
        return round(n / d, 4) if d else None
    result = {
        "schema_version": 1, "result_kind": "theme_review_shadow_point_in_time",
        "status": "SHADOW_ONLY_NO_FORMAL_TRADE_SIGNAL",
        "date_range": [daily[0]["trade_date"], daily[-1]["trade_date"]],
        "days": len(daily), "catalog_frozen_commit": manifest["catalog_frozen_commit"],
        "catalog_version": catalog["catalog_version"],
        "lookback_snapshots": len(days), "source": "immutable Git historical daily commits",
        "comparison": {
            "old3": "2026-11-04 pre-change composite top-3, no persistence reservation",
            "new10": "grouped composite top-5 plus up to five multi-L3 persistence seats",
            "denominator": "full eligible deduplicated theme/taxonomy pool",
            "selection_timestamp": "after each archived close; not an intraday replay",
        },
        "summary": {
            "mean_old3_count": round(sum(len(x["old3"]) for x in daily)/len(daily), 3),
            "mean_new10_count": round(sum(len(x["new10"]) for x in daily)/len(daily), 3),
            "persistent_theme_opportunities": total_persistent,
            "persistent_old_captured": sum(d["persistent_themes_captured_old3"] for d in daily),
            "persistent_new_captured": sum(d["persistent_themes_captured_new10"] for d in daily),
            "persistent_old_recall": ratio(
                sum(d["persistent_themes_captured_old3"] for d in daily), total_persistent),
            "persistent_new_recall": ratio(
                sum(d["persistent_themes_captured_new10"] for d in daily), total_persistent),
            "old3_retained_in_new10": sum(d["old3_covers_new"] for d in daily),
            "old3_total": sum(len(d["old3"]) for d in daily),
            "new_exclusive_theme_instances": sum(d["new_exclusive_theme_count"] for d in daily),
            "photovoltaic_old3_days": sum(d["photovoltaic"]["old_rank"] is not None for d in daily),
            "photovoltaic_new10_days": sum(d["photovoltaic"]["new_rank"] is not None for d in daily),
            "forward_outcomes": {
                strategy: summarize_outcomes(forward_rows, strategy)
                for strategy in ("old3", "new10", "new_exclusive")},
        },
        "warnings": [
            "Rules were developed after observing 2026-11-04 photovoltaic strength: in-sample / hindsight selection bias.",
            "New10 contains more themes, so aggregate forward hit rates are not directly comparable without matching candidate count or a cost model.",
            "Industry SW2 taxonomy and curated research themes are discovery-only groupings; component SW3 confirmation and CORE/DIRECT benefit must be independently verified.",
            "No formal market_state, industrial T state, stock handoff, trade, PnL, or official index return is inferred.",
            "Forward outcomes are cross-sectional constituent median price-return proxies; weak continuation is NOT a validated false-positive definition.",
            "Historical commit publication times may be later than a fixed 18:30 task; only after-close research is reconstructed.",
            "3/5-session price returns and volume are reconstructed only from archived immutable earlier daily quotes.",
            "Missing concepts and external non-equity price anchors are not recovered retroactively.",
        ],
        "daily": daily, "forward_evaluations": forward_rows,
    }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start", default="2026-10-12")
    args = parser.parse_args()
    result = replay(args.root, json.loads(args.manifest.read_text(encoding="utf-8")),
                    json.loads(args.catalog.read_text(encoding="utf-8")),
                    start=args.start)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n",
                           encoding="utf-8")
    print("SHADOW_SUMMARY", json.dumps({
        "days": result["days"], "date_range": result["date_range"],
        "summary": result["summary"],
        "photovoltaic_recent": [
            {"date": x["trade_date"], "old": x["photovoltaic"]["old_rank"],
             "new": x["photovoltaic"]["new_rank"],
             "track": x["photovoltaic"]["new_track"]}
            for x in result["daily"] if x["trade_date"] >= "2026-11-02"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
