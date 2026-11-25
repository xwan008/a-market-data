#!/usr/bin/env python3
"""Deterministic sector discovery only; never emits buy/sell or trend confirmations."""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

from price_inputs import load_momentum_shards
from discovery_coverage import build_coverage_review
from build_history import normalized_volume

TZ = ZoneInfo("Asia/Shanghai")

# Industry-level seed capacity stays at 3; theme-level cross-check is independent.
THEME_CROSSCHECK_LIMIT = 10


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def pct(value, base):
    return round(value / base, 4) if base else None


def stock_features(code, latest, structure, trade_date):
    quote = (latest.get("stocks") or {}).get(code) or {}
    item = (structure.get("companies") or {}).get(code) or {}
    if not quote or quote.get("confidence") == "invalid":
        return None
    change = number(quote.get("change_pct"))
    if change is None:
        price, previous = number(quote.get("price")), number(quote.get("prev_close"))
        change = (price / previous - 1) * 100 if price and previous and previous > 0 else None
    if change is None:
        return None
    evidence = item.get("phase_evidence") or {}
    fresh = item.get("data_status") == "verified" and item.get("data_date") == trade_date
    return {
        "code": code, "r1": change,
        "r3": number(evidence.get("return_3d_pct")) if fresh else None,
        "r5": number(evidence.get("return_5d_pct")) if fresh else None,
        "volume": number(evidence.get("volume_ratio_1d")) if fresh else None,
    }


def load_daily_history(codes, history_dir, trade_date):
    """Reuse the existing adjusted OHLCV shards; do not create another price store."""
    by_prefix = defaultdict(set)
    for code in codes:
        by_prefix[str(code).zfill(6)[:4]].add(str(code).zfill(6))
    result = {}
    for prefix, members in sorted(by_prefix.items()):
        path = Path(history_dir) / (prefix + ".json")
        if not path.exists():
            continue
        try:
            stocks = (read_json(path).get("stocks") or {})
        except (OSError, ValueError, TypeError, AttributeError):
            continue
        for code in members:
            rows = (stocks.get(code) or {}).get("history") or []
            # Retain enough earlier bars for the five sessions and 20-bar volume.
            # Never use future bars or silently bridge missing market sessions.
            result[code] = sorted(
                (r for r in rows if isinstance(r, dict)
                 and isinstance(r.get("date"), str) and r["date"] <= trade_date),
                key=lambda r: r["date"])[-26:]
    return result


def daily_structure_evidence(groups, features, history, trade_date):
    """Objective session-by-session evidence, not a score, state or eligibility gate.

    Historical membership is the current as-of SW3 mapping. A replay must use
    that day's frozen input files. A missing observation is not a zero return.
    """
    history = history or {}
    dates = {trade_date}
    indexed = {}
    for code, rows in history.items():
        if code not in features:
            continue
        by_day = {}
        duplicates = set()
        for r in rows:
            day = r.get("date")
            close = number(r.get("close"))
            if not isinstance(day, str) or day > trade_date or close is None or close <= 0:
                continue
            if r.get("confidence") == "invalid":
                continue
            if day in by_day:
                duplicates.add(day)
            by_day[day] = r
        for day in duplicates:
            by_day.pop(day, None)
        indexed[code] = by_day
        dates.update(by_day)
    sessions = sorted(dates)[-6:]
    report_days = sessions[-5:]
    previous = {d: sessions[i-1] if i else None for i, d in enumerate(sessions)}
    by_session = {}
    for day in report_days:
        stock_metrics = {}
        prev_day = previous[day]
        for code, feature in features.items():
            rows = indexed.get(code, {})
            row = rows.get(day)
            prior = rows.get(prev_day)
            daily_return = volume = above = below = None
            if row is not None and prior is not None:
                close, prev_close = number(row.get("close")), number(prior.get("close"))
                if close is not None and prev_close is not None and prev_close > 0:
                    daily_return = (close / prev_close - 1) * 100
                hi, lo = number(prior.get("high")), number(prior.get("low"))
                if close is not None and hi is not None and lo is not None and hi >= lo > 0:
                    above, below = close > hi, close < lo
            if row is not None:
                old = [rows[d] for d in sorted(rows) if d < day][-20:]
                vol = number(normalized_volume(row))
                vols = [number(normalized_volume(r)) for r in old]
                if len(vols) == 20 and vol is not None and vol > 0 and all(
                        v is not None and v > 0 for v in vols):
                    volume = vol / (sum(vols) / 20)
            if day == trade_date:
                # Keep the production close's quote and momentum measures authoritative.
                daily_return = feature["r1"] if feature is not None else None
                volume = feature["volume"] if feature is not None else None
                if feature is None:
                    above = below = None
            stock_metrics[code] = (daily_return, volume, above, below)
        market = [v[0] for v in stock_metrics.values() if v[0] is not None]
        benchmark = median(market) if market and len(market) >= .90 * len(features) else None
        by_session[day] = (stock_metrics, benchmark, len(market))
    output = {}
    for group in groups:
        series = []
        n = len(group["codes"])
        minimum = max(3, math.ceil(.8 * n))
        for day in report_days:
            metrics, benchmark, market_n = by_session[day]
            values = [metrics[c] for c in group["codes"]]
            returns = [v[0] for v in values if v[0] is not None]
            volumes = [v[1] for v in values if v[1] is not None and v[1] > 0]
            ranges = [v for v in values if v[2] is not None and v[3] is not None]
            med = median(returns) if len(returns) >= minimum else None
            advancing = sum(v > 0 for v in returns)
            series.append({
                "trade_date": day, "previous_observed_session_date": previous[day],
                "member_count": n, "return_sample_size": len(returns),
                "return_coverage": pct(len(returns), n),
                "median_1d_pct": round(med, 3) if med is not None else None,
                "market_sample_size": market_n,
                "market_median_1d_pct": round(benchmark, 3) if benchmark is not None else None,
                "relative_1d_vs_market_median_pct": (
                    round(med - benchmark, 3) if med is not None and benchmark is not None else None),
                "advancing_count": advancing,
                "advance_ratio": pct(advancing, len(returns)) if len(returns) >= minimum else None,
                "volume_sample_size": len(volumes),
                "median_volume_ratio_vs_prior_20d": (
                    round(median(volumes), 3) if len(volumes) >= minimum else None),
                "prior_range_sample_size": len(ranges),
                "close_above_prior_day_high_count": sum(v[2] for v in ranges),
                "close_below_prior_day_low_count": sum(v[3] for v in ranges),
            })
        output[group["id"]] = {
            "status": "COMPLETE" if len(series) == 5 and all(
                r["relative_1d_vs_market_median_pct"] is not None
                and r["median_volume_ratio_vs_prior_20d"] is not None
                and r["prior_range_sample_size"] >= minimum for r in series) else "PARTIAL",
            "role": "OBJECTIVE_EVIDENCE_ONLY",
            "series": series,
        }
    return output


def build(latest, industry_index, structure, review_cap=3,
          sw2_indices=None, price_anchors=None, daily_history=None):
    trade_date = str(latest.get("trade_date") or "")
    if not trade_date or latest.get("market_status") != "closed":
        raise ValueError("completed_market_session_required")
    if str(structure.get("reference_trade_date")) != trade_date:
        raise ValueError("structure_date_mismatch")
    companies = industry_index.get("companies")
    if not isinstance(companies, dict) or not companies:
        raise ValueError("industry_universe_missing")

    industries = defaultdict(lambda: {"name": "", "codes": set()})
    mapped = set()
    for code, item in companies.items():
        code = str(code).zfill(6)
        if item.get("mapping_status") != "mapped":
            continue
        sector = str(item.get("industry_code") or "")
        if not sector or not item.get("sw_level3_name"):
            continue
        industries[sector]["name"] = item["sw_level3_name"]
        industries[sector]["codes"].add(code)
        mapped.add(code)
    groups = [
        {"id": "industry:" + key, "name": data["name"], "codes": data["codes"],
         "kind": "industry", "source": "data/research/company_industry_index.json"}
        for key, data in sorted(industries.items())
    ]

    codes = set().union(*(g["codes"] for g in groups)) if groups else set()
    features = {code: stock_features(code, latest, structure, trade_date) for code in codes}
    market_changes = [f["r1"] for f in features.values() if f is not None]
    if not market_changes or sum(f is not None for f in features.values()) / max(len(features), 1) < .90:
        raise ValueError("mapped_quote_coverage_below_90pct")
    market_median = median(market_changes)
    dynamic = daily_structure_evidence(groups, features, daily_history, trade_date)

    rows = []
    for g in groups:
        available = [features[c] for c in g["codes"] if features.get(c) is not None]
        count, usable = len(g["codes"]), len(available)
        coverage = pct(usable, count)
        gains = [v["r1"] for v in available]
        med1 = median(gains) if gains else None
        breadth = pct(sum(x > 0 for x in gains), usable)
        r3 = [f["r3"] for f in available if f["r3"] is not None]
        r5 = [f["r5"] for f in available if f["r5"] is not None]
        vols = [f["volume"] for f in available if f["volume"] is not None and f["volume"] > 0]
        # Historical participation means stock-level cumulative returns > 0,
        # not a median industry return or a count of separate up-days.
        enough3 = usable > 0 and len(r3) >= max(3, math.ceil(.8 * usable))
        enough5 = usable > 0 and len(r5) >= max(3, math.ceil(.8 * usable))
        breadth3 = pct(sum(x > 0 for x in r3), len(r3)) if enough3 else None
        breadth5 = pct(sum(x > 0 for x in r5), len(r5)) if enough5 else None
        med3 = median(r3) if len(r3) >= max(3, usable // 2) else None
        med5 = median(r5) if len(r5) >= max(3, usable // 2) else None
        medvolume = median(vols) if len(vols) >= max(3, usable // 2) else None
        acceleration = round(med3 - .6 * med5, 3) if med3 is not None and med5 is not None else None
        rs1 = round(med1 - market_median, 3) if med1 is not None else None
        quality = ("LOW_SAMPLE" if count < 3 else
                   "INSUFFICIENT" if coverage < .8 else
                   "SMALL_SAMPLE" if count < 5 else "OK")
        signal_eligible = quality in ("OK", "SMALL_SAMPLE")
        strong = bool(signal_eligible and breadth >= .6 and med1 >= .5 and rs1 >= .8)
        emerging = bool(signal_eligible and breadth >= .6 and med1 >= .35 and rs1 >= .3
                        and acceleration is not None and acceleration >= .35)
        channels = (["STRONG"] if strong else []) + (["EMERGING"] if emerging else [])
        score = round((rs1 or 0) + max((breadth or 0) - .5, 0) * 3
                      + max(acceleration or 0, 0) * .35, 3)
        rows.append({
            "id": g["id"], "name": g["name"], "kind": g["kind"],
            "source": g["source"], "member_count": count, "usable_count": usable,
            "coverage": coverage, "sample_quality": quality,
            "median_1d_pct": round(med1, 3) if med1 is not None else None,
            "relative_1d_vs_market_median_pct": rs1,
            "advance_ratio": breadth, "breadth_3d": breadth3, "breadth_5d": breadth5,
            "usable_3d_count": len(r3), "usable_5d_count": len(r5),
            "median_3d_pct": med3, "median_5d_pct": med5,
            "acceleration_3d_vs_5d": acceleration,
            "median_volume_ratio_vs_20d": medvolume, "score": score,
            "daily_structure": dynamic[g["id"]],
            "channels": channels,
            "reason": "ELIGIBLE" if channels else
                      ("LOW_SAMPLE_OBSERVE" if quality == "LOW_SAMPLE" else
                       "INSUFFICIENT_COVERAGE" if quality != "OK" else "NO_COHERENT_TRIGGER")
        })

    # Deduplicate near-identical membership; keep source provenance in full audit.
    members_by_id = {g["id"]: g["codes"] for g in groups}
    pool = sorted((r for r in rows if r["channels"]),
                  key=lambda r: (-r["score"], r["id"]))
    unique = []
    for row in pool:
        members = members_by_id[row["id"]]
        duplicate = next((
            prior for prior in unique
            if len(members & members_by_id[prior["id"]])
               / max(len(members | members_by_id[prior["id"]]), 1) >= .85
        ), None)
        if duplicate:
            row["reason"] = "OVERLAPPING_CANDIDATE"
            row["overlaps_with"] = duplicate["id"]
        else:
            unique.append(row)

    # Reserve one third of research capacity for early improvements not already strong.
    emerging_only = [r for r in unique if "EMERGING" in r["channels"]
                     and "STRONG" not in r["channels"]]
    reserve = min(max(1, review_cap // 3), len(emerging_only))
    selected = [r for r in unique if "STRONG" in r["channels"]][:review_cap - reserve]
    selected += emerging_only[:reserve]
    selected_ids = {r["id"] for r in selected}
    for row in unique:
        if len(selected) >= review_cap:
            break
        if row["id"] not in selected_ids:
            selected.append(row)
            selected_ids.add(row["id"])
    for row in unique:
        row["reason"] = "MODEL_REVIEW" if row["id"] in selected_ids else "CAPACITY_DEFERRED"

    coverage = build_coverage_review(rows, trade_date, selected_ids, sw2_indices, price_anchors)
    audit = {
        "schema_version": 1, "trade_date": trade_date,
        "scan_inputs": {"industry_index": "data/research/company_industry_index.json",
                        "quotes": "data/latest.json",
                        "momentum": "data/shards/*.json#trend.momentum_evidence",
                        "daily_structure": "data/history_shards/*.json#stocks.history"},
        "daily_structure_contract": {
            "role": "OBJECTIVE_EVIDENCE_ONLY",
            "membership": "ASOF_CURRENT_MAPPED_SW3_MAIN_BOARD",
            "session_window": 5,
            "historical_return": "adjacent observed market sessions, adjusted history closes",
            "current_return": "completed quote change_pct",
            "prior_range": "prior session high/low, not confirmed technical support",
            "missing_values_are_not_zero": True,
            "affects_scores_or_state": False,
        },
        "industry_count": len(industries), "scan_scope": "MAPPED_SW_LEVEL3_ONLY",
        # Documentation only: the upstream quote collector deliberately limits
        # this research universe to Shanghai/Shenzhen main-board A shares.
        "equity_universe_scope": "SH_SZ_MAIN_BOARD_A_SHARES",
        "excluded_equity_boards": ["CHINEXT", "STAR", "BSE"],
        "benchmark_scope": "VALID_QUOTED_MAPPED_MAIN_BOARD_STOCKS",
        "mapped_stocks": len(mapped),
        "market_median_return_1d_pct": round(market_median, 3),
        "review_capacity": review_cap, "eligible_count": len(unique),
        "selected_count": len(selected), "deferred_count": len(unique) - len(selected),
        "overlap_deduplicated_count": len(pool) - len(unique),
        "discovery_coverage_audit": coverage,
        "sectors": sorted(rows, key=lambda r: r["id"])
    }
    # Ancillary sector evidence for cross-checking independent market research
    # research; optional grouping/refill only within supplemental review work.
    # Never choose, rank, admit, invalidate or replace official themes.
    candidate_overview = [
        {"id": row["id"], "name": row["name"], "kind": row["kind"],
         "industry_code": row["id"].split(":", 1)[1] if row["kind"] == "industry" else None,
         "channels": row["channels"], "score": row["score"],
         "relative_strength": row["relative_1d_vs_market_median_pct"],
         "advance_ratio": row["advance_ratio"], "research_queue_status": row["reason"]}
        for row in unique
    ]
    industry_rows = {
        row["id"].split(":", 1)[1]: row for row in rows if row["kind"] == "industry"
    }
    # Same SW level-2 branch is only a lookup clue, not proof of common
    # catalysts/profitability. Models may review unrelated branches too.
    peer_hints = []
    for anchor in selected:
        if anchor["kind"] != "industry":
            continue
        code = anchor["id"].split(":", 1)[1]
        peers = sorted(
            (item for other_code, item in industry_rows.items()
             if other_code != code and other_code[:5] == code[:5]),
            key=lambda item: (-item["score"], item["id"])
        )
        peer_hints.append({
            "anchor_industry_code": code,
            "classification_only": True,
            "nearby_industries": [
                {"code": item["id"].split(":", 1)[1], "name": item["name"],
                 "sample_quality": item["sample_quality"], "reason": item["reason"]}
                for item in peers[:8]
            ],
        })
    snapshot = {
        "schema_version": 1, "result_kind": "sector_discovery_snapshot",
        "trade_date": trade_date, "generated_at": datetime.now(TZ).isoformat(),
        "status": "COMPLETE",
        "no_trade_signal": True,
        "audit_path": "data/research/sector_discovery_audit.json",
        "scan_audit": {k: v for k, v in audit.items() if k != "sectors"},
        "discovery_role": {
            "mode": "AUXILIARY_EVIDENCE_ONLY",
            "primary_research": "independent_full_market_research",
            "may_determine_trend_state": False,
            "may_set_new_position_priority": False,
            "may_override_independent_existing_trend": False,
            "missing_discovery_blocks_primary_research": False,
        },
        "model_research_candidates": selected,
        "deferred_candidates": [r for r in unique if r["id"] not in selected_ids],
        "theme_research_budget": {
            "scope": "supplemental_program_discovery_only",
            "does_not_limit_model_independent_research": True,
            "optional_refill_uses_independent_industry_evidence": True,
            "unit": "evidence_verified_theme_not_industry",
            "max_new_theme_deep_research": THEME_CROSSCHECK_LIMIT,
            "initial_seed_industry_count": len(selected),
            "seed_industries_are_not_hard_theme_limit": True,
            "refill_from_candidate_overview_after_merging": True,
            "existing_registry_theme_rechecks_excluded_from_budget": True,
            "cross_industry_driver_validation_required": True,
            "routable_codes_only_after_model_verification": True,
        },
        "candidate_overview": candidate_overview,
        "discovery_coverage_audit": coverage,
        "classification_peer_hints": peer_hints,
        "all_industry_metrics": "data/research/sector_discovery_audit.json#sectors",
        "handoff_routing_reference": "data/low_risk/index.json",
    }
    return snapshot, audit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--latest", default="data/latest.json")
    parser.add_argument("--industry-index", default="data/research/company_industry_index.json")
    parser.add_argument("--shard-dir", default="data/shards")
    parser.add_argument("--history-dir", default="data/history_shards")
    parser.add_argument("--sw2-indices", default="data/research/sw2_index_asof.json")
    parser.add_argument("--price-anchors", default="data/research/price_anchors_asof.json")
    parser.add_argument("--output", default="data/research/sector_discovery_snapshot.json")
    parser.add_argument("--audit", default="data/research/sector_discovery_audit.json")
    parser.add_argument("--review-cap", type=int, default=3)
    args = parser.parse_args()
    if args.review_cap < 1:
        parser.error("review-cap must be positive")
    sw2_path, anchors_path = Path(args.sw2_indices), Path(args.price_anchors)
    sw2 = read_json(sw2_path) if sw2_path.exists() else None
    anchors = read_json(anchors_path) if anchors_path.exists() else None
    latest, industry_index = read_json(args.latest), read_json(args.industry_index)
    trade_date = latest["trade_date"]
    history = load_daily_history(
        (code for code, item in industry_index["companies"].items()
         if item.get("mapping_status") == "mapped"),
        args.history_dir, trade_date)
    snapshot, audit = build(latest, industry_index,
                            load_momentum_shards(trade_date, args.shard_dir),
                            args.review_cap, sw2, anchors, history)
    for path, payload in ((args.output, snapshot), (args.audit, audit)):
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
    print(json.dumps({"date": snapshot["trade_date"], "status": snapshot["status"],
                      "industries": audit["industry_count"], "scan_scope": audit["scan_scope"],
                      "eligible": audit["eligible_count"], "selected": audit["selected_count"],
                      "deferred": audit["deferred_count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
