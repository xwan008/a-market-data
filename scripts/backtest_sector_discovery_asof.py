#!/usr/bin/env python3
"""Point-in-time sector discovery replay and objective forward-outcome diagnostics.

Signals use ONLY each day's saved Git tree. Future snapshots are used solely
in separate ex-post outcomes; they are never passed to the discovery function.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median

from build_sector_discovery import build, number


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_days(root, manifest):
    observed = []
    for entry in manifest["snapshots"]:
        day = entry["trade_date"]
        sub = Path(root) / day
        latest = load(sub / "latest.json")
        index = load(sub / "company_industry_index.json")
        structure = load(sub / "full_market_price_structure.json")
        if latest.get("trade_date") != day or structure.get("reference_trade_date") != day:
            raise ValueError("ASOF_DATE_MISMATCH:" + day)
        if latest.get("market_status") != "closed":
            raise ValueError("ASOF_NOT_COMPLETED_SESSION:" + day)
        if not isinstance(index.get("companies"), dict) or not index["companies"]:
            raise ValueError("ASOF_INDUSTRY_INDEX_MISSING:" + day)
        observed.append((day, entry["commit"], latest, index, structure))
    if not observed or len({row[0] for row in observed}) != len(observed):
        raise ValueError("missing_or_duplicate_sessions")
    if [x[0] for x in observed] != sorted(x[0] for x in observed):
        raise ValueError("unordered_sessions")
    return observed


def closes(quotes, codes):
    result = {}
    for code in codes:
        quote = (quotes.get("stocks") or {}).get(code) or {}
        if quote.get("confidence") == "invalid":
            continue
        p = number(quote.get("price"))
        if p is not None and p > 0:
            result[code] = p
    return result


def future_return(signal_quotes, future_quotes, codes, coverage_floor=.8):
    start = closes(signal_quotes, codes)
    finish = closes(future_quotes, codes)
    paired = [code for code in codes if code in start and code in finish]
    if len(paired) < max(5, len(codes) * coverage_floor):
        return None
    return round(median((finish[c] / start[c] - 1) * 100 for c in paired), 4)


def replay(root, manifest, horizon=2, cap=20):
    days = load_days(root, manifest)
    decisions, all_results = [], []
    for day, commit, latest, index, structure in days:
        snapshot, audit = build(latest, index, structure, review_cap=cap)
        if snapshot["trade_date"] != day:
            raise ValueError("REPLAY_DATE_MISMATCH")
        industries = {
            "industry:" + str(info["industry_code"]):
                {str(code).zfill(6) for code, info2 in index["companies"].items()
                 if info2.get("mapping_status") == "mapped"
                 and str(info2.get("industry_code")) == str(info["industry_code"])}
            for info in [{"industry_code": key} for key in
                         {v.get("industry_code") for v in index["companies"].values()
                          if v.get("industry_code")}]
        }
        decisions.append({"date": day, "source_commit": commit,
                          "scope": "SW_LEVEL3_ASOF_COMMIT_ONLY",
                          "status": snapshot["status"],
                          "industry_count": audit["industry_count"],
                          "eligible": audit["eligible_count"],
                          "selected": audit["selected_count"],
                          "deferred": audit["deferred_count"],
                          "source_future_data_used_for_discovery": False,
                          "agriculture": [
                              {"id": row["id"], "name": row["name"],
                               "median_1d_pct": row["median_1d_pct"],
                               "breadth": row["advance_ratio"],
                               "channels": row["channels"], "reason": row["reason"]}
                              for row in audit["sectors"]
                              if row["name"] in ("种子", "粮食种植", "粮油加工")],
                          "candidates": [
                              {"id": row["id"], "name": row["name"],
                               "channels": row["channels"], "reason": row["reason"]}
                              for row in audit["sectors"] if row["channels"]]})
        all_results.append((latest, industries, audit, snapshot))
    # Outcomes are deliberately evaluated AFTER all as-of decisions are frozen.
    evaluations = []
    for i, (current, industries, audit, snapshot) in enumerate(all_results):
        for row in audit["sectors"]:
            if not row["channels"] or row["reason"] == "OVERLAPPING_CANDIDATE":
                continue
            codes = industries.get(row["id"], set())
            out = {"signal_date": days[i][0], "id": row["id"], "name": row["name"],
                   "selected": row["reason"] == "MODEL_REVIEW",
                   "channels": row["channels"], "outcomes": {}}
            for step in (1, horizon):
                if i + step >= len(days):
                    out["outcomes"][str(step)] = {"status": "NOT_YET_OBSERVABLE"}
                    continue
                future = all_results[i + step][0]
                perf = future_return(current, future, codes)
                if perf is None:
                    out["outcomes"][str(step)] = {"status": "INSUFFICIENT_FUTURE_COVERAGE"}
                    continue
                market_codes = set((current.get("stocks") or {})) & set((future.get("stocks") or {}))
                benchmark = future_return(current, future, market_codes)
                if benchmark is None:
                    out["outcomes"][str(step)] = {"status": "BENCHMARK_UNAVAILABLE"}
                    continue
                relative = round(perf - benchmark, 4)
                out["outcomes"][str(step)] = {
                    "status": "OBSERVED", "median_return_pct": perf,
                    "relative_vs_market_pct": relative,
                    "weak_follow_through_proxy": perf <= 0 and relative <= 0}
            evaluations.append(out)

    selected = [x for x in evaluations if x["selected"]]
    def summarize(items, step):
        outcomes = [x["outcomes"][str(step)] for x in items
                    if x["outcomes"][str(step)]["status"] == "OBSERVED"]
        weak = sum(bool(x["weak_follow_through_proxy"]) for x in outcomes)
        return {"observations": len(outcomes), "weak_follow_through_count": weak,
                "weak_follow_through_rate": round(weak / len(outcomes), 4) if outcomes else None,
                "not_evaluable_count": len(items) - len(outcomes)}
    return {
        "schema_version": 1, "result_kind": "sector_discovery_asof_backtest",
        "scope": "SW_LEVEL3_ONLY", "days": len(days),
        "date_range": [days[0][0], days[-1][0]],
        "horizon_session_count": horizon, "research_cap": cap,
        "signal_input_rule": "exact committed data files at signal-day SHA; no future inputs",
        "evaluation_rule": "future committed daily snapshots used only after decisions frozen",
        "weak_follow_through_definition": "sector median forward return <=0 and relative vs entire market median <=0",
        "warnings": [
            "Forward weakness is only a market-continuation proxy; NOT proof of an emotional/speculative false positive or a failed trade.",
            "Some historical sessions may lack later complete sessions; exclude them from that horizon denominator.",
            "Historical data publishing times may differ from fixed 18:40 research task time.",
            "Only repository-covered mainboard equities and contemporaneous stored SW mapping are tested."],
        "summary": {
            "selected_horizon_1": summarize(selected, 1),
            f"selected_horizon_{horizon}": summarize(selected, horizon),
            "all_eligible_horizon_1": summarize(evaluations, 1),
            f"all_eligible_horizon_{horizon}": summarize(evaluations, horizon)},
        "daily_decisions": decisions, "forward_evaluations": evaluations,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--horizon", type=int, default=2)
    args = parser.parse_args()
    if args.horizon < 2:
        parser.error("horizon must be at least 2 sessions")
    result = replay(args.root, load(args.manifest), args.horizon)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print("ASOF_REPLAY_RESULT", json.dumps(
        {"days": result["days"], "summary": result["summary"],
         "agriculture": [x for x in result["daily_decisions"]
                         if x["date"] in ("2026-10-08", "2026-10-09")]},
        ensure_ascii=False))


if __name__ == "__main__":
    main()
