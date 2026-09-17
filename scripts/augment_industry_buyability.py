#!/usr/bin/env python3
"""Attach deterministic low-risk buyability context to industry_state.json.

The output is used only to rank Stage 0 industry entrances. It is not a
company-level admission gate and it does not alter Stage A / Gate / Deep
Research rules.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def median_or_none(values: list[float]) -> float | None:
    return median(values) if values else None


def positive_pe_proxy(fundamentals: dict[str, Any]) -> float | None:
    values = [
        float(value)
        for value in (fundamentals.get("pe_ttm"), fundamentals.get("pe_dynamic"))
        if is_number(value) and value > 0
    ]
    return min(values) if values else None


def core_profit_growth(fundamentals: dict[str, Any]) -> float | None:
    deduct = fundamentals.get("deduct_basic_eps_yoy")
    if is_number(deduct):
        return float(deduct)
    profit = fundamentals.get("net_profit_yoy")
    return float(profit) if is_number(profit) else None


def percentile_rank(
    value: float | None,
    population: list[float],
    *,
    higher_is_better: bool,
) -> float | None:
    if value is None or not population:
        return None
    ordered = sorted(population)
    if len(ordered) == 1:
        return 0.5
    lower = sum(1 for item in ordered if item < value)
    equal = sum(1 for item in ordered if item == value)
    rank = (lower + (equal - 1) / 2) / (len(ordered) - 1)
    return rank if higher_is_better else 1.0 - rank


def mean_available(values: list[float | None]) -> float | None:
    available = [float(value) for value in values if value is not None]
    return sum(available) / len(available) if available else None


def classify_buyability(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score >= 0.65:
        return "favorable"
    if score <= 0.35:
        return "stretched"
    return "balanced"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", default="data/snapshot.json")
    parser.add_argument("--industry-state", default="data/research/industry_state.json")
    args = parser.parse_args()

    snapshot_path = Path(args.snapshot)
    state_path = Path(args.industry_state)
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    state = json.loads(state_path.read_text(encoding="utf-8"))

    trade_date = str(snapshot.get("trade_date") or "")
    state_trade_date = str(state.get("baseline_trade_date") or "")
    if not trade_date or trade_date != state_trade_date:
        raise SystemExit(
            f"snapshot/industry_state trade_date mismatch: {trade_date!r} != {state_trade_date!r}"
        )

    industries = state.get("level3_profitability") or {}
    candidates = snapshot.get("candidates") or {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for candidate in candidates.values():
        industry_code = str(candidate.get("industry_code") or "")
        if not industry_code or industry_code not in industries:
            continue
        fundamentals = candidate.get("fundamentals") or {}
        structure = candidate.get("price_structure") or {}
        grouped[industry_code].append(
            {
                "pe_proxy": positive_pe_proxy(fundamentals),
                "roe": float(fundamentals["roe"]) if is_number(fundamentals.get("roe")) else None,
                "core_growth": core_profit_growth(fundamentals),
                "cashflow_positive": (
                    float(fundamentals["operating_cashflow_per_share"]) > 0
                    if is_number(fundamentals.get("operating_cashflow_per_share"))
                    else None
                ),
                "position_60d": (
                    float(structure["position_pct"])
                    if is_number(structure.get("position_pct"))
                    else None
                ),
                "change_20d": (
                    float(structure["close_change_20d_pct"])
                    if is_number(structure.get("close_change_20d_pct"))
                    else None
                ),
            }
        )

    raw: dict[str, dict[str, Any]] = {}
    for code, rows in grouped.items():
        pe_values = [row["pe_proxy"] for row in rows if row["pe_proxy"] is not None]
        roe_values = [row["roe"] for row in rows if row["roe"] is not None]
        growth_values = [row["core_growth"] for row in rows if row["core_growth"] is not None]
        position_values = [row["position_60d"] for row in rows if row["position_60d"] is not None]
        change_values = [row["change_20d"] for row in rows if row["change_20d"] is not None]
        cashflow_values = [
            row["cashflow_positive"]
            for row in rows
            if row["cashflow_positive"] is not None
        ]

        raw[code] = {
            "candidate_count": len(rows),
            "median_positive_pe": median_or_none(pe_values),
            "median_roe": median_or_none(roe_values),
            "median_core_profit_yoy": median_or_none(growth_values),
            "core_profit_positive_share": (
                sum(1 for value in growth_values if value > 0) / len(growth_values)
                if growth_values
                else None
            ),
            "positive_operating_cashflow_share": (
                sum(1 for value in cashflow_values if value) / len(cashflow_values)
                if cashflow_values
                else None
            ),
            "median_60d_position_pct": median_or_none(position_values),
            "median_20d_change_pct": median_or_none(change_values),
        }

    metric_populations: dict[str, list[float]] = defaultdict(list)
    for metrics in raw.values():
        for key, value in metrics.items():
            if key == "candidate_count" or value is None:
                continue
            metric_populations[key].append(float(value))

    for code, item in industries.items():
        metrics = raw.get(code)
        if not metrics:
            item["buyability"] = {
                "status": "unavailable",
                "label": "unknown",
                "score": None,
                "reason": "no research-eligible runtime candidates",
            }
            continue

        valuation = percentile_rank(
            metrics["median_positive_pe"],
            metric_populations["median_positive_pe"],
            higher_is_better=False,
        )
        price = mean_available(
            [
                percentile_rank(
                    metrics["median_60d_position_pct"],
                    metric_populations["median_60d_position_pct"],
                    higher_is_better=False,
                ),
                percentile_rank(
                    metrics["median_20d_change_pct"],
                    metric_populations["median_20d_change_pct"],
                    higher_is_better=False,
                ),
            ]
        )
        earnings = mean_available(
            [
                percentile_rank(
                    metrics["median_core_profit_yoy"],
                    metric_populations["median_core_profit_yoy"],
                    higher_is_better=True,
                ),
                percentile_rank(
                    metrics["core_profit_positive_share"],
                    metric_populations["core_profit_positive_share"],
                    higher_is_better=True,
                ),
                percentile_rank(
                    metrics["median_roe"],
                    metric_populations["median_roe"],
                    higher_is_better=True,
                ),
                percentile_rank(
                    metrics["positive_operating_cashflow_share"],
                    metric_populations["positive_operating_cashflow_share"],
                    higher_is_better=True,
                ),
            ]
        )

        weighted_parts = [
            (valuation, 0.35),
            (price, 0.30),
            (earnings, 0.35),
        ]
        available_parts = [(value, weight) for value, weight in weighted_parts if value is not None]
        score = (
            sum(value * weight for value, weight in available_parts)
            / sum(weight for _, weight in available_parts)
            if available_parts
            else None
        )

        item["buyability"] = {
            "status": "valid" if score is not None else "unavailable",
            "label": classify_buyability(score),
            "score": round(score, 6) if score is not None else None,
            "components": {
                "valuation_attractiveness": round(valuation, 6) if valuation is not None else None,
                "price_attractiveness": round(price, 6) if price is not None else None,
                "earnings_support": round(earnings, 6) if earnings is not None else None,
            },
            "metrics": metrics,
            "method": (
                "cross-industry percentile context from research-eligible candidates; "
                "35% valuation attractiveness + 30% price/crowding attractiveness + "
                "35% core-earnings/quality support; ranking context only, never a hard veto"
            ),
        }

    state["buyability_context"] = {
        "status": "valid" if raw else "invalid",
        "trade_date": trade_date,
        "eligible_industry_count": len(raw),
        "source": "data/snapshot.json research-eligible candidates",
        "usage": "Stage 0 industry ordering context only; not a company admission gate",
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    label_counts: dict[str, int] = defaultdict(int)
    for item in industries.values():
        label_counts[str((item.get("buyability") or {}).get("label") or "unknown")] += 1
    print(
        json.dumps(
            {
                "trade_date": trade_date,
                "eligible_industries": len(raw),
                "buyability_labels": dict(label_counts),
            },
            ensure_ascii=False,
        )
    )
    return 0 if raw else 2


if __name__ == "__main__":
    raise SystemExit(main())
