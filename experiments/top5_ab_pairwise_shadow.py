#!/usr/bin/env python3
"""A/B Top5: A = published PR56 order, B = PR54 evidence pairwise shadow.

Read ONLY the pinned same-day formal Top5 (or a fixture created from it).
This tool NEVER changes Top5 membership, official ranking, READY, stops,
handoff, research inputs or future trading records.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

DEFAULT_INPUT = Path(__file__).resolve().parent / "fixtures/top5_ab_2026-10-23.json"
SUPPORT_MODES = {"LOCAL_SUPPORT_HOLD", "SAME_DAY_SWEEP_RECLAIM"}
# Predeclared material differences, purely provisional, not backtest-fitted:
LIMITS = {
    "trend": (("return_5d_pct", 2.0), ("positive_days_5d", 1.0),
              ("max_close_drawdown_10d_pct", 3.0)),
    "volume": (("volume_ratio_1d_vs_20d", 0.30),
               ("volume_ratio_5d_vs_20d", 0.20),
               ("close_location_pct", 8.0),
               ("relative_strength_20d_vs_market_pct", 3.0),
               ("up_to_down_volume_ratio_5d", 0.30)),
    "position": (("abs_distance_to_ma20_pct", 1.0),),
}
SCALES = (0.75, 1.0, 1.25)


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def evidence(row, asof):
    if row.get("data_date") != asof:
        raise ValueError("mismatched_or_future_company_date:" + str(row.get("code")))
    ctx, ev = row.get("technical_context") or {}, row.get("phase_evidence") or {}
    recent = ctx.get("recent_acceptance") or {}
    if recent and (recent.get("data_date") != asof
                   or recent.get("lookback_trading_days") not in (1, 2, 3)):
        raise ValueError("unverified_PR54_observation:" + str(row.get("code")))
    dates = recent.get("support_dates") or []
    if any(not isinstance(d, str) or not d < asof for d in dates):
        raise ValueError("future_support_dates:" + str(row.get("code")))
    mode = recent.get("pattern") or "UNVERIFIED"
    if mode in SUPPORT_MODES and (len(dates) != 2
                                  or not isinstance(recent.get("support_close_band"), list)
                                  or len(recent["support_close_band"]) != 2):
        raise ValueError("unsupported_recent_support_without_prior_closes")
    r1 = ctx.get("volume_ratio_1d_vs_20d")
    loc = ctx.get("close_location_pct")
    fresh = ev.get("fresh_break") is True  # previous completed 5 daily highs
    verified_recent_support = (mode in SUPPORT_MODES and fresh
                               and numeric(r1) and r1 >= 1.3
                               and numeric(loc) and loc >= 65)
    up = ev.get("up_day_volume_ratio_5d")
    down = ev.get("down_day_volume_ratio_5d")
    flow = up / down if numeric(up) and numeric(down) and down > 0 else None
    gap = ctx.get("distance_to_ma20_pct")
    return {
        "code": row["code"], "name": row["company_name"],
        "status": row.get("status"), "asof_close": row.get("current_price"),
        "pattern": mode, "support_close_band": recent.get("support_close_band"),
        "support_dates": dates,
        "support_intraday_broken": recent.get("intraday_support_broken"),
        "formal_R_for_annotation_only": row.get("upside_to_resistance_R"),
        "observation_stop": None,  # no new executable/observation stop
        "five_day_break": fresh,
        "recent_support_with_volume": verified_recent_support,
        "return_5d_pct": ev.get("return_5d_pct"),
        "positive_days_5d": ev.get("positive_days_5d"),
        "max_close_drawdown_10d_pct": ev.get("max_close_drawdown_10d_pct"),
        "volume_ratio_1d_vs_20d": r1,
        "volume_ratio_5d_vs_20d": ctx.get("volume_ratio_5d_vs_20d"),
        "close_location_pct": loc,
        "relative_strength_20d_vs_market_pct": ctx.get("relative_strength_20d_vs_market_pct"),
        "up_to_down_volume_ratio_5d": round(flow, 6) if flow is not None else None,
        "abs_distance_to_ma20_pct": abs(gap) if numeric(gap) else None,
        "overextended_8pct": numeric(gap) and gap > 8,
    }


def compare_numeric(a, b, field, tol):
    x, y = a.get(field), b.get(field)
    if not numeric(x) or not numeric(y):
        return 0
    # Larger is better for all sub-evidence except distance-to-MA20.
    delta = y-x if field == "abs_distance_to_ma20_pct" else x-y
    return 1 if delta > tol else -1 if delta < -tol else 0


def compare_domains(a, b, threshold_scale=1.0):
    outcome, diagnostics = {}, {}
    for domain in ("trend", "volume"):
        votes = [compare_numeric(a,b,k,t * threshold_scale) for k,t in LIMITS[domain]]
        count_a, count_b = votes.count(1), votes.count(-1)
        outcome[domain] = (1 if count_a >= 2 and count_a > count_b
                           else -1 if count_b >= 2 and count_b > count_a else 0)
        diagnostics[domain] = {"a_metrics_ahead": [
            k for (k,_),v in zip(LIMITS[domain], votes) if v == 1],
            "b_metrics_ahead": [
            k for (k,_),v in zip(LIMITS[domain], votes) if v == -1],
            "result": outcome[domain]}
    ea = int(a["five_day_break"]) + int(a["recent_support_with_volume"])
    eb = int(b["five_day_break"]) + int(b["recent_support_with_volume"])
    outcome["structure"] = 1 if ea > eb else -1 if eb > ea else 0
    outcome["position"] = compare_numeric(a,b,"abs_distance_to_ma20_pct",
                                           LIMITS["position"][0][1]*threshold_scale)
    positive = sum(v == 1 for v in outcome.values())
    negative = sum(v == -1 for v in outcome.values())
    # Material majority, but NOT automatic if a meaningful contrary dimension exists.
    strong_a = ((positive >= 2 and negative == 0) or
                (positive >= 3 and negative <= 1))
    strong_b = ((negative >= 2 and positive == 0) or
                (negative >= 3 and positive <= 1))
    lead = 1 if strong_a and not strong_b else -1 if strong_b and not strong_a else 0
    return {"a": a["code"], "b": b["code"], "lead": lead,
            "domains": outcome, "detail": diagnostics,
            "domain_advantages": {"a": positive, "b": negative},
            "interpretation": "A_MATERIAL_LEAD" if lead == 1 else
                              "B_MATERIAL_LEAD" if lead == -1 else
                              "TRADEOFF_OR_INSUFFICIENT_DIFFERENCE"}


def layers(codes, comparisons):
    remaining = set(codes)
    edges = set()
    for c in comparisons:
        if c["lead"] != 0:
            w,l = (c["a"],c["b"]) if c["lead"] == 1 else (c["b"],c["a"])
            edges.add((w,l))
    out, cycle_detected = [], False
    order = {code:i for i,code in enumerate(codes)}
    while remaining:
        roots = [x for x in remaining if not any(a in remaining and b == x
                                                for a,b in edges)]
        if not roots:
            # Do not invent tie-breakers for possible nontransitive evidence.
            roots, cycle_detected = list(remaining), True
        roots.sort(key=order.__getitem__)
        out.append(roots)
        remaining.difference_update(roots)
    return out, cycle_detected


def shadow(frozen, asof, scale=1.0):
    if frozen.get("trade_date") != asof:
        raise ValueError("snapshot_asof_mismatch")
    by_code = {r["code"]:r for r in frozen.get("rows",[])}
    if len(by_code) != len(frozen.get("rows",[])):
        raise ValueError("duplicate_stock_in_frozen_snapshot")
    reports = []
    for group in frozen.get("top5_by_theme",[]):
        original = [x["code"] for x in group["items"]]
        if len(original) > 5 or len(original) != len(set(original)):
            raise ValueError("top5_member_cap_or_duplicate")
        if any(code not in by_code for code in original):
            raise ValueError("frozen_top5_member_missing")
        views = [evidence(by_code[c], asof) for c in original]
        comparisons = [compare_domains(a,b,scale)
                       for i,a in enumerate(views) for b in views[i+1:]]
        tiers, cycles = layers(original, comparisons)
        reports.append({
            "theme":group["trend_name"],
            "A_formal_order":original,
            "B_evidence_tiers":tiers,
            "B_ties_are_not_ranked_within_tier":True,
            "pairwise":comparisons,
            "candidate_evidence":views,
            "non_transitive_conflict":cycles,
            "membership_unchanged":sorted(original)==sorted(c for tier in tiers for c in tier),
        })
    return reports


def run(frozen, asof):
    report = {
        "kind":"TOP5_PR54_PAIRWISE_AB_SHADOW",
        "asof":asof,
        "source_run_id":frozen.get("source_run_id"),
        "source_formal_blob_sha":frozen.get("source_sha"),
        "read_only":True,
        "modifies_formal_or_ready":False,
        "risk_and_R_from_PR54_sweep":None,
        "method": {
            "domains":["recent_trend","PR54_structure","volume_price","position"],
            "material_thresholds":LIMITS,
            "domain_rule":"trend_and_volume: >=2 material metric wins and more wins than losses",
            "dominance_rule":"at least 2 winning dimensions and no losing ones, or >=3 wins and at most 1 loss",
            "tie_rule":"material trade-offs/unresolved differences stay in same evidence tier",
            "no_new_weights":True,
            "limitations":"Single 2026-10-23 snapshot cannot validate profit/outcomes; do not interpret tiers as BUY orders"
        },
        "main":shadow(frozen, asof),
    }
    for main in report["main"]:
        comparisons = {c["a"]+"|"+c["b"]:c["lead"] for c in main["pairwise"]}
        settings=[]
        for scale in SCALES:
            replay=next(x for x in shadow(frozen,asof,scale)
                        if x["theme"]==main["theme"])
            leads={c["a"]+"|"+c["b"]:c["lead"] for c in replay["pairwise"]}
            settings.append({
                "material_threshold_scale":scale,
                "tiers":replay["B_evidence_tiers"],
                "changed_pair_decisions_vs_base":sum(v!=comparisons[k] for k,v in leads.items())
            })
        main["sensitivity"]=settings
    return report


def cli():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",type=Path,default=DEFAULT_INPUT)
    parser.add_argument("--asof",default="2026-10-23")
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    source=args.input.resolve()
    # No future-data promotion; contract requires explicit matching asof.
    raw=source.read_bytes()
    frozen=json.loads(raw)
    result=run(frozen,args.asof)
    result["input_sha256"]=hashlib.sha256(raw).hexdigest()
    payload=json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n"
    if args.output:
        out=args.output.resolve()
        root=Path(__file__).resolve().parents[1]
        blocked={root/"research/trend_buy_formal_result.json",
                 root/"research/trend_buy_handoff.json",
                 root/"research/trend_buy_company_reviews/latest.json"}
        if out in blocked or out == source:
            raise ValueError("protected_formal_or_snapshot_file")
        out.write_text(payload,encoding="utf-8")
    else:
        print(payload,end="")


if __name__=="__main__":
    cli()
