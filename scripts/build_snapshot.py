#!/usr/bin/env python3
"""Build the compact industry-first snapshot for the low-risk task.

V6 fixes the selection order:
1. prequalify industries from earnings evidence + market attention;
2. only then scan all eligible companies inside those industries;
3. keep stock technical structure broad enough for the runtime lifecycle gate;
4. do NOT require a stock to have already re-accelerated before it can be seen.

The model later performs public research on leading industry prosperity signals.
Repository financial aggregation is an earnings base, not a substitute for that
leading-indicator research.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from contracts import ELIGIBILITY_MAX_PRICE as MAX_PRICE, YOY_UNIT
from snapshot_io import write_snapshot


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def number(value: Any) -> float | None:
    return float(value) if is_number(value) else None


def industry_earnings_stage(item: dict[str, Any] | None) -> str | None:
    """Repository-side earnings prequalification, deliberately not T1/T2 prosperity.

    Final industry prosperity is researched later from leading variables such as
    price/spread, orders, inventory, demand and capacity. This gate only prevents
    clearly weak earnings bases from flooding the stock scan.
    """
    if not item:
        return None
    confidence = str(item.get("confidence") or "")
    trend = str(item.get("trend") or "")
    strength = str(item.get("strength") or "")
    revenue = number(item.get("aggregate_revenue_yoy"))
    profit = number(item.get("aggregate_parent_profit_yoy"))
    breadth = number(item.get("core_improving_breadth"))

    if confidence not in {"medium", "high"}:
        return None
    if revenue is None or profit is None or breadth is None:
        return None

    if (
        trend == "improving"
        and strength == "strong"
        and revenue >= 5.0
        and profit >= 20.0
        and breadth >= 0.60
    ):
        return "PROFIT_TREND_CONFIRMED"

    if (
        trend == "improving"
        and revenue >= 0.0
        and profit >= 5.0
        and breadth >= 0.55
    ):
        return "EARNINGS_IMPROVING"

    # Important early window: demand/revenue can lead profit recognition by one
    # or more reporting periods. PCB-like cases must stay visible here.
    if (
        trend in {"stable", "improving"}
        and revenue >= 8.0
        and profit >= 0.0
        and breadth >= 0.45
    ):
        return "EARNINGS_TRANSMITTING"

    return None


def industry_funds_stage(item: dict[str, Any] | None) -> str | None:
    """Industry market attention, allowing relative resilience in risk-off tape.

    FUNDS_ENTERING requires broad + active participation. FUNDS_ATTENTION is a
    weaker but useful state: the industry is broadly outperforming/holding up
    even if absolute turnover is below its 20-day norm because the whole market
    is de-risking.
    """
    if not item:
        return None
    breadth = str(item.get("market_breadth") or "")
    activity = str(item.get("market_activity") or "")
    confirmation = str(item.get("market_confirmation") or "")
    metrics = item.get("market_metrics") or {}
    breadth_score = number(metrics.get("breadth_score"))
    volume_ratio = number(metrics.get("median_volume_ratio_vs_20d"))
    expanding_share = number(metrics.get("expanding_volume_share"))
    day_up_ratio = number(metrics.get("day_up_ratio"))
    strong_up_ratio = number(metrics.get("strong_up_ratio"))

    if None in {breadth_score, volume_ratio, expanding_share}:
        return None

    if (
        confirmation == "strong"
        and breadth == "broad"
        and activity == "active"
        and volume_ratio >= 1.00
        and expanding_share >= 0.50
        and breadth_score >= 0.55
    ):
        return "FUNDS_ENTERING"

    if breadth == "broad" and breadth_score >= 0.55:
        normal_participation = volume_ratio >= 0.80 and expanding_share >= 0.25
        relative_resilience = (
            day_up_ratio is not None
            and strong_up_ratio is not None
            and day_up_ratio >= 0.75
            and strong_up_ratio >= 0.40
            and volume_ratio >= 0.60
        )
        if normal_participation or relative_resilience:
            return "FUNDS_ATTENTION"

    return None


def compact_industries(raw: dict[str, Any]) -> dict[str, Any]:
    if raw.get("yoy_unit") != YOY_UNIT:
        raise RuntimeError(
            f"industry_state.yoy_unit must be {YOY_UNIT}, got {raw.get('yoy_unit')!r}"
        )
    result: dict[str, Any] = {}
    for code, item in (raw.get("level3_profitability") or {}).items():
        compact = {
            "name": item.get("name"),
            "trend": item.get("trend"),
            "strength": item.get("strength"),
            "breadth": item.get("breadth"),
            "confidence": item.get("confidence"),
            "last_verified_at": item.get("last_verified_at"),
            "core_improving_breadth": item.get("core_improving_breadth"),
            "aggregate_revenue_yoy": item.get("aggregate_revenue_yoy"),
            "aggregate_parent_profit_yoy": item.get("aggregate_parent_profit_yoy"),
            "market_breadth": item.get("market_breadth"),
            "market_activity": item.get("market_activity"),
            "market_confirmation": item.get("market_confirmation"),
            "market_metrics": item.get("market_metrics") or {},
        }
        compact["earnings_stage"] = industry_earnings_stage(compact)
        compact["funds_stage"] = industry_funds_stage(compact)
        compact["prequalified"] = bool(
            compact["earnings_stage"] and compact["funds_stage"]
        )
        result[code] = compact
    return result


def industry_allowed(item: dict[str, Any] | None) -> bool:
    return bool(item and item.get("prequalified") is True)


def company_exclusion_reason(raw: dict[str, Any]) -> str | None:
    """Deterministic company hygiene only; no valuation ranking."""
    name = str(raw.get("name") or "").upper()
    if "ST" in name or "退" in str(raw.get("name") or ""):
        return "risk_name"

    price = raw.get("price")
    if not is_number(price) or price <= 0 or price > MAX_PRICE:
        return "price_rule"

    fundamentals = raw.get("fundamentals") or {}
    if not fundamentals.get("report_date"):
        return "data_or_trend_incomplete"

    net_profit = fundamentals.get("net_profit")
    if not is_number(net_profit) or net_profit <= 0:
        return "non_positive_profit"

    if not any(
        is_number(fundamentals.get(key))
        for key in ("pe_ttm", "pe_dynamic", "pb", "market_cap")
    ):
        return "data_or_trend_incomplete"

    revenue_yoy = fundamentals.get("revenue_yoy")
    net_profit_yoy = fundamentals.get("net_profit_yoy")
    if (
        is_number(revenue_yoy)
        and is_number(net_profit_yoy)
        and revenue_yoy < -20
        and net_profit_yoy < -50
    ):
        return "severe_revenue_profit_deterioration"

    trend = raw.get("trend") or {}
    if (trend.get("points") or 0) < 20:
        return "data_or_trend_incomplete"
    if not (trend.get("structure_60d") or {}):
        return "data_or_trend_incomplete"

    return None


def structural_tier(technical: dict[str, Any] | None) -> str | None:
    """Broad structural mapping; lifecycle quality is decided later.

    This deliberately does NOT require the stock to already be strongly active.
    That prevents the snapshot from hiding good pullbacks or pre-breakout names
    before the industry-first runtime gets a chance to evaluate them.
    """
    if not technical or technical.get("data_status") != "verified":
        return None
    if technical.get("chase_risk") == "high":
        return None

    stype = technical.get("structure_type")
    if stype == "breakout":
        return "starting_breakout"
    if stype == "trend_continuation":
        return "early_trend"
    if stype == "pullback":
        return "active_pullback"
    if stype == "transition":
        return "pre_breakout"
    if stype == "base_not_started":
        return "accumulation_base"
    return None


def nearest_zone(
    zones: list[dict[str, Any]], price: float, *, side: str
) -> dict[str, Any] | None:
    candidates: list[tuple[float, dict[str, Any]]] = []
    for zone in zones:
        center = zone.get("center")
        if not is_number(center):
            continue
        if side == "below" and center > price * 1.01:
            continue
        if side == "above" and center < price * 0.99:
            continue
        candidates.append((abs(center - price), zone))
    if not candidates:
        return None
    zone = min(candidates, key=lambda x: x[0])[1]
    keep = {
        "low": zone.get("low"),
        "high": zone.get("high"),
        "center": zone.get("center"),
    }
    for key in ("touches", "volume_share_pct", "last_date", "last_touch_date"):
        if zone.get(key) is not None:
            keep[key] = zone.get(key)
    return keep


def compact_candidate(
    raw: dict[str, Any], technical: dict[str, Any], tier: str
) -> dict[str, Any]:
    price = float(raw["price"])
    prev_close = raw.get("prev_close")
    day_change_pct = None
    if is_number(prev_close) and prev_close != 0:
        day_change_pct = (price / prev_close - 1) * 100

    fundamentals = raw.get("fundamentals") or {}
    trend = raw.get("trend") or {}
    structure = trend.get("structure_60d") or {}
    evolution = structure.get("structure_evolution") or {}

    return {
        "name": raw.get("name"),
        "price": raw.get("price"),
        "day_change_pct": day_change_pct,
        "industry_code": raw.get("sw_level3_code"),
        "industry_name": raw.get("sw_level3_name"),
        "fundamentals": {
            "report_date": fundamentals.get("report_date"),
            "pe_ttm": fundamentals.get("pe_ttm"),
            "pe_dynamic": fundamentals.get("pe_dynamic"),
            "pb": fundamentals.get("pb"),
            "market_cap": fundamentals.get("market_cap"),
            "roe": fundamentals.get("roe"),
            "revenue_yoy": fundamentals.get("revenue_yoy"),
            "net_profit_yoy": fundamentals.get("net_profit_yoy"),
            "deduct_basic_eps_yoy": fundamentals.get("deduct_basic_eps_yoy"),
            "operating_cashflow_per_share": fundamentals.get("operating_cashflow_per_share"),
            "gross_margin": fundamentals.get("gross_margin"),
            "net_profit": fundamentals.get("net_profit"),
            "basic_eps": fundamentals.get("basic_eps"),
            "deduct_basic_eps": fundamentals.get("deduct_basic_eps"),
        },
        "market_activation": {
            "activation_tier": tier,
            "structure_type": technical.get("structure_type"),
            "action": technical.get("action"),
            "chase_risk": technical.get("chase_risk"),
            "return_10d_pct": technical.get("return_10d_pct"),
            "return_20d_pct": technical.get("return_20d_pct"),
            "relative_strength_20d_vs_market_pct": technical.get(
                "relative_strength_20d_vs_market_pct"
            ),
            "volume_ratio_1d_vs_20d": technical.get("volume_ratio_1d_vs_20d"),
            "volume_ratio_5d_vs_20d": technical.get("volume_ratio_5d_vs_20d"),
            "distance_to_ma20_pct": technical.get("distance_to_ma20_pct"),
            "distance_to_ma60_pct": technical.get("distance_to_ma60_pct"),
            "breakout_confirmed": technical.get("breakout_confirmed"),
            "breakout_volume_confirmed": technical.get("breakout_volume_confirmed"),
            "breakout_close_confirmed": technical.get("breakout_close_confirmed"),
            "price_discovery": technical.get("price_discovery"),
            "downside_to_invalidation_pct": technical.get(
                "downside_to_invalidation_pct"
            ),
            "support_invalidation": technical.get("support_invalidation"),
        },
        "price_structure": {
            "high_20d": trend.get("high_20d"),
            "low_20d": trend.get("low_20d"),
            "close_change_5d_pct": trend.get("close_change_5d_pct"),
            "close_change_20d_pct": trend.get("close_change_20d_pct"),
            "high_60d": structure.get("high"),
            "low_60d": structure.get("low"),
            "ma20": structure.get("ma20"),
            "ma60": structure.get("ma60"),
            "position_pct": structure.get("position_pct"),
            "trend_state": evolution.get("trend_state"),
            "break_state": evolution.get("break_state"),
            "invalidation": evolution.get("invalidation"),
            "nearest_support": nearest_zone(
                structure.get("support_zones") or [], price, side="below"
            ),
            "nearest_volume_zone": nearest_zone(
                structure.get("volume_profile_zones") or [], price, side="below"
            ),
            "nearest_resistance": nearest_zone(
                structure.get("resistance_zones") or [], price, side="above"
            ),
        },
    }


def build_snapshot(source: Path) -> dict[str, Any]:
    shard_dir = source / "data" / "shards"
    shard_paths = sorted(shard_dir.glob("*.json"))
    if not shard_paths:
        raise RuntimeError(f"no upstream shards found in {shard_dir}")

    industry_path = source / "data" / "research" / "industry_state.json"
    technical_path = source / "data" / "research" / "full_market_price_structure.json"
    if not industry_path.exists():
        raise RuntimeError("industry_state.json is required")
    if not technical_path.exists():
        raise RuntimeError("full_market_price_structure.json is required")

    industry_raw = load_json(industry_path)
    industries = compact_industries(industry_raw)
    industry_pool = {
        code: item for code, item in industries.items() if industry_allowed(item)
    }

    technical_raw = load_json(technical_path)
    technical_companies = technical_raw.get("companies") or {}

    trade_dates: set[str] = set()
    statuses: set[str] = set()
    generated_times: list[str] = []
    universe_count = 0
    price_count = 0
    fundamentals_count = 0
    trend_count = 0
    mapping_count = 0
    candidates: dict[str, Any] = {}
    eligibility_reasons: Counter[str] = Counter()

    for shard_path in shard_paths:
        shard = load_json(shard_path)
        if shard.get("trade_date"):
            trade_dates.add(str(shard["trade_date"]))
        if shard.get("market_status"):
            statuses.add(str(shard["market_status"]))
        if shard.get("generated_at"):
            generated_times.append(str(shard["generated_at"]))

        for code, raw in (shard.get("stocks") or {}).items():
            code = str(code).zfill(6)
            universe_count += 1
            price = raw.get("price")
            if is_number(price) and price > 0:
                price_count += 1

            fundamentals = raw.get("fundamentals") or {}
            if fundamentals.get("report_date") and any(
                is_number(fundamentals.get(key))
                for key in ("pe_ttm", "pe_dynamic", "pb", "net_profit")
            ):
                fundamentals_count += 1

            trend = raw.get("trend") or {}
            if (trend.get("points") or 0) >= 20 and trend.get("last_date"):
                trend_count += 1

            industry_code = raw.get("sw_level3_code")
            if raw.get("industry_mapping_status") == "mapped" and industry_code:
                mapping_count += 1

            # Critical invariant: industry first. A stock is invisible unless its
            # industry passed the earnings + market-attention prequalification.
            if industry_code not in industry_pool:
                eligibility_reasons["industry_prefilter_ineligible"] += 1
                continue

            exclusion_reason = company_exclusion_reason(raw)
            if exclusion_reason:
                eligibility_reasons[exclusion_reason] += 1
                continue

            technical = technical_companies.get(code) or {}
            tier = structural_tier(technical)
            if tier is None:
                eligibility_reasons["technical_structure_ineligible"] += 1
                continue

            eligibility_reasons["eligible"] += 1
            candidates[code] = compact_candidate(raw, technical, tier)

    if len(trade_dates) != 1:
        raise RuntimeError(
            f"upstream shards do not share one trade_date: {sorted(trade_dates)}"
        )
    if universe_count == 0:
        raise RuntimeError("empty upstream universe")

    trade_date = next(iter(trade_dates))
    if technical_raw.get("reference_trade_date") != trade_date:
        raise RuntimeError(
            "full-market technical state is stale: "
            f"{technical_raw.get('reference_trade_date')} != {trade_date}"
        )

    upstream_generated_at = max(generated_times) if generated_times else None
    audited_total = sum(eligibility_reasons.values())
    if audited_total != universe_count:
        raise RuntimeError(
            f"eligibility audit mismatch: universe={universe_count} audit={audited_total}"
        )
    if eligibility_reasons["eligible"] != len(candidates):
        raise RuntimeError(
            "eligibility eligible count does not match candidate count: "
            f"audit={eligibility_reasons['eligible']} candidates={len(candidates)}"
        )

    exclusion_keys = (
        "industry_prefilter_ineligible",
        "risk_name",
        "price_rule",
        "non_positive_profit",
        "severe_revenue_profit_deterioration",
        "data_or_trend_incomplete",
        "technical_structure_ineligible",
    )
    eligibility_audit = {
        "universe_count": universe_count,
        "eligible_count": len(candidates),
        "exclusive_first_failure_counts": {
            key: eligibility_reasons.get(key, 0) for key in exclusion_keys
        },
        "audit_total_matches_universe": audited_total == universe_count,
        "rules": {
            "selection_order": "industry prequalification before stock structure",
            "industry_earnings": (
                "profit trend confirmed OR earnings improving OR strong revenue with "
                "non-negative profit and >=45% improving breadth"
            ),
            "industry_market": (
                "FUNDS_ENTERING from broad active participation OR FUNDS_ATTENTION "
                "from broad relative resilience/participation"
            ),
            "leading_prosperity": (
                "not claimed by repository gate; must be confirmed later from public "
                "leading indicators"
            ),
            "risk_name": "exclude ST / delisting-risk names",
            "price_rule": f"0 < price <= {MAX_PRICE:g}",
            "non_positive_profit": "company net_profit must be > 0",
            "valuation": "PE/PB retained as risk context; no PE hard ceiling",
            "severe_revenue_profit_deterioration": (
                "exclude when revenue_yoy < -20 and net_profit_yoy < -50"
            ),
            "technical_structure": (
                "keep broad non-overheated base/transition/trend/pullback/breakout "
                "states; lifecycle quality is evaluated later"
            ),
            "data_or_trend_incomplete": (
                "report_date + usable valuation context + >=20 trend points + 60d "
                "structure required"
            ),
        },
    }

    return {
        "generated_at": upstream_generated_at,
        "trade_date": trade_date,
        "market_status": next(iter(statuses)) if len(statuses) == 1 else "mixed",
        "source": {
            "repository": "xwan008/a-market-data",
            "ref": "main",
            "latest_upstream_generated_at": upstream_generated_at,
            "industry_state_generated_at": industry_raw.get("generated_at"),
            "full_market_price_structure_generated_at": technical_raw.get(
                "generated_at"
            ),
        },
        "units": {"company_yoy": YOY_UNIT, "industry_yoy": YOY_UNIT},
        "eligibility_audit": eligibility_audit,
        "counts": {
            "universe_stocks": universe_count,
            "candidates": len(candidates),
            "industries": len(industries),
            "prequalified_industries": len(industry_pool),
            "shards": len(shard_paths),
        },
        "coverage": {
            "price_pct": price_count / universe_count,
            "fundamentals_pct": fundamentals_count / universe_count,
            "trend_pct": trend_count / universe_count,
            "industry_mapping_pct": mapping_count / universe_count,
        },
        "industry_pool": industry_pool,
        "industry_state": {
            "status": industry_raw.get("status"),
            "baseline_trade_date": industry_raw.get("baseline_trade_date"),
            "generated_at": industry_raw.get("generated_at"),
            "yoy_unit": YOY_UNIT,
            "level3": industries,
        },
        "candidates": candidates,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="path to source repository")
    parser.add_argument("--output", default="data/snapshot.json")
    args = parser.parse_args()

    snapshot = build_snapshot(Path(args.source).resolve())
    output = Path(args.output)
    write_snapshot(output, snapshot)

    audit = snapshot["eligibility_audit"]["exclusive_first_failure_counts"]
    print(
        f"snapshot ready: trade_date={snapshot['trade_date']} "
        f"universe={snapshot['counts']['universe_stocks']} "
        f"industry_pool={snapshot['counts']['prequalified_industries']} "
        f"candidates={snapshot['counts']['candidates']} "
        f"industries={snapshot['counts']['industries']} "
        f"eligibility_exclusions={sum(audit.values())}"
    )


if __name__ == "__main__":
    main()
