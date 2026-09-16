#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def write_row_json(
    path: Path,
    header: dict[str, Any],
    columns: list[str],
    rows: list[list[Any]],
) -> None:
    lines = ["{"]
    for key, value in header.items():
        lines.append(
            f"  {json.dumps(key, ensure_ascii=False)}: "
            f"{json.dumps(value, ensure_ascii=False, separators=(',', ':'))},"
        )
    lines.append(
        '  "columns": '
        + json.dumps(columns, ensure_ascii=False, separators=(",", ":"))
        + ","
    )
    lines.append('  "rows": [')
    for i, row in enumerate(rows):
        suffix = "," if i < len(rows) - 1 else ""
        lines.append(
            "    "
            + json.dumps(row, ensure_ascii=False, separators=(",", ":"))
            + suffix
        )
    lines.append("  ]")
    lines.append("}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def at(row: list[Any], index: dict[str, int], name: str) -> Any:
    pos = index.get(name)
    if pos is None or pos >= len(row):
        return None
    return row[pos]


def industry_fundamental_stage(
    row: list[Any], index: dict[str, int]
) -> str | None:
    trend = str(at(row, index, "industry_trend") or "")
    strength = str(at(row, index, "industry_strength") or "")
    confidence = str(at(row, index, "industry_confidence") or "")
    revenue = num(at(row, index, "industry_aggregate_revenue_yoy"))
    profit = num(at(row, index, "industry_aggregate_parent_profit_yoy"))
    breadth = num(at(row, index, "industry_core_improving_breadth"))

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
        return "T2_PROFIT_TREND"

    if (
        trend == "improving"
        and revenue >= 0.0
        and profit >= 10.0
        and breadth >= 0.55
    ):
        return "T1_PROSPERITY_CONFIRMED"

    return None


def industry_market_stage(
    row: list[Any], index: dict[str, int]
) -> str | None:
    breadth = str(at(row, index, "industry_market_breadth") or "")
    activity = str(at(row, index, "industry_market_activity") or "")
    confirmation = str(at(row, index, "industry_market_confirmation") or "")
    breadth_score = num(at(row, index, "industry_market_breadth_score"))
    volume_ratio = num(at(row, index, "industry_median_volume_ratio_vs_20d"))
    expanding_share = num(at(row, index, "industry_expanding_volume_share"))

    if None in {breadth_score, volume_ratio, expanding_share}:
        return None

    if (
        confirmation == "strong"
        and breadth == "broad"
        and activity == "active"
        and volume_ratio >= 1.05
        and expanding_share >= 0.50
        and breadth_score >= 0.55
    ):
        return "TREND_FORMING"

    if (
        breadth == "broad"
        and activity in {"normal", "active"}
        and volume_ratio >= 1.05
        and expanding_share >= 0.55
        and breadth_score >= 0.55
    ):
        return "FUNDS_TESTING"

    return None


def drawdown_from_high(
    row: list[Any], index: dict[str, int]
) -> float | None:
    price = num(at(row, index, "price"))
    high = num(at(row, index, "high_20d"))
    if price is None or high is None or high <= 0:
        return None
    return max(0.0, (high - price) / high * 100.0)


def is_reacceleration(row: list[Any], index: dict[str, int]) -> bool:
    price = num(at(row, index, "price"))
    ma20 = num(at(row, index, "ma20"))
    day = num(at(row, index, "day_change_pct"))
    close5 = num(at(row, index, "close_change_5d_pct"))
    ret20 = num(at(row, index, "return_20d_pct"))
    rs20 = num(at(row, index, "relative_strength_20d_vs_market_pct"))
    vol1 = num(at(row, index, "volume_ratio_1d_vs_20d"))
    dd = drawdown_from_high(row, index)

    return bool(
        price is not None
        and ma20 is not None
        and day is not None
        and close5 is not None
        and ret20 is not None
        and rs20 is not None
        and vol1 is not None
        and dd is not None
        and price >= ma20
        and day >= 2.0
        and close5 >= 0.0
        and ret20 <= 10.0
        and rs20 > 0.0
        and vol1 >= 1.50
        and dd <= 4.0
    )


def stock_lifecycle_stage(
    row: list[Any], index: dict[str, int]
) -> str | None:
    tier = str(at(row, index, "activation_tier") or "")
    chase = str(at(row, index, "chase_risk") or "")
    price = num(at(row, index, "price"))
    ma20 = num(at(row, index, "ma20"))
    day = num(at(row, index, "day_change_pct"))
    ret20 = num(at(row, index, "return_20d_pct"))
    rs20 = num(at(row, index, "relative_strength_20d_vs_market_pct"))
    vol1 = num(at(row, index, "volume_ratio_1d_vs_20d"))
    vol5 = num(at(row, index, "volume_ratio_5d_vs_20d"))
    close5 = num(at(row, index, "close_change_5d_pct"))
    position = num(at(row, index, "position_pct"))
    breakout = at(row, index, "breakout_confirmed") is True
    dd = drawdown_from_high(row, index)

    if chase == "high" or price is None or ret20 is None or rs20 is None:
        return None
    if dd is None:
        return None

    reaccel = is_reacceleration(row, index)

    # Explicit fade / distribution protection. A stock that already had a run
    # must prove fresh re-acceleration before it can re-enter the research pool.
    if dd >= 5.0 and not reaccel:
        return None
    if dd >= 3.0 and close5 is not None and close5 < 0.0 and not reaccel:
        return None
    if (
        day is not None
        and day < 0.0
        and vol1 is not None
        and vol1 >= 1.50
        and dd >= 3.0
    ):
        return None
    if (
        position is not None
        and position >= 70.0
        and dd >= 3.0
        and (day is None or day <= 0.0)
        and not reaccel
    ):
        return None
    if (
        ma20 is not None
        and price < ma20
        and close5 is not None
        and close5 < 0.0
        and not reaccel
    ):
        return None

    if (
        tier == "starting_breakout"
        and breakout
        and ret20 <= 12.0
        and rs20 > 0.0
        and dd <= 2.0
        and (day is None or day >= 0.0)
        and (
            (vol1 is not None and vol1 >= 1.30)
            or (vol5 is not None and vol5 >= 1.15)
        )
    ):
        return "FRESH_ACTIVATION"

    if (
        tier == "pre_breakout"
        and ret20 <= 10.0
        and rs20 >= 0.0
        and dd <= 5.0
        and (
            (vol1 is not None and vol1 >= 1.20)
            or (vol5 is not None and vol5 >= 1.10)
        )
    ):
        return "PRE_BREAKOUT"

    if (
        tier == "accumulation_base"
        and ret20 <= 8.0
        and rs20 >= -1.0
        and vol1 is not None
        and vol1 >= 1.20
        and vol5 is not None
        and vol5 >= 1.05
    ):
        return "ACCUMULATION_READY"

    if (
        tier == "early_trend"
        and ret20 <= 10.0
        and rs20 > 0.0
        and dd <= 3.0
        and close5 is not None
        and close5 >= 1.0
        and (ma20 is None or price >= ma20)
        and (
            (vol1 is not None and vol1 >= 1.20)
            or (vol5 is not None and vol5 >= 1.15)
        )
    ):
        return "EARLY_EXPANSION"

    if tier == "active_pullback" and reaccel:
        return "REACCELERATION"

    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", default="data/runtime")
    args = parser.parse_args()

    runtime_dir = Path(args.runtime_dir)
    meta_path = runtime_dir / "meta.json"
    meta = load_json(meta_path)
    candidate_path = Path(meta["candidate_file"])
    candidate = load_json(candidate_path)
    columns = candidate.get("columns") or []
    rows = candidate.get("rows") or []
    index = {name: i for i, name in enumerate(columns)}

    required = {
        "code",
        "price",
        "industry_code",
        "industry_trend",
        "industry_strength",
        "industry_confidence",
        "industry_core_improving_breadth",
        "industry_aggregate_revenue_yoy",
        "industry_aggregate_parent_profit_yoy",
        "industry_market_breadth",
        "industry_market_activity",
        "industry_market_confirmation",
        "industry_market_breadth_score",
        "industry_median_volume_ratio_vs_20d",
        "industry_expanding_volume_share",
        "activation_tier",
        "chase_risk",
        "volume_ratio_1d_vs_20d",
        "volume_ratio_5d_vs_20d",
        "relative_strength_20d_vs_market_pct",
        "return_20d_pct",
        "close_change_5d_pct",
        "high_20d",
        "ma20",
        "position_pct",
        "breakout_confirmed",
    }
    missing = sorted(required - set(columns))
    if missing:
        raise SystemExit(f"industry-activation gate missing columns: {missing}")

    kept: list[list[Any]] = []
    fundamental_counts: Counter[str] = Counter()
    market_counts: Counter[str] = Counter()
    lifecycle_counts: Counter[str] = Counter()
    rejection_counts: Counter[str] = Counter()
    eligible_industries: set[str] = set()

    for row in rows:
        fundamental_stage = industry_fundamental_stage(row, index)
        if not fundamental_stage:
            rejection_counts["industry_fundamental_gate"] += 1
            continue
        fundamental_counts[fundamental_stage] += 1

        market_stage = industry_market_stage(row, index)
        if not market_stage:
            rejection_counts["industry_money_flow_gate"] += 1
            continue
        market_counts[market_stage] += 1

        lifecycle = stock_lifecycle_stage(row, index)
        if not lifecycle:
            rejection_counts["stock_not_early_activation"] += 1
            continue
        lifecycle_counts[lifecycle] += 1

        kept.append(row)
        eligible_industries.add(str(at(row, index, "industry_code") or ""))

    source_count = int(candidate.get("source_candidate_count") or len(rows))
    rule = {
        "selection_mode": "industry_dual_confirm_then_early_stock",
        "industry_fundamental_gate": ["T1_PROSPERITY_CONFIRMED", "T2_PROFIT_TREND"],
        "industry_market_gate": ["FUNDS_TESTING", "TREND_FORMING"],
        "stock_lifecycle_gate": [
            "PRE_BREAKOUT",
            "ACCUMULATION_READY",
            "FRESH_ACTIVATION",
            "EARLY_EXPANSION",
            "REACCELERATION",
        ],
        "post_peak_fade_allowed": False,
        "distribution_risk_allowed": False,
        "active_pullback_requires_reacceleration": True,
        "valuation_hard_ceiling": None,
        "note": (
            "industry prosperity/profitability is the first gate; industry money flow "
            "is the second gate; only then may early-stage stocks enter research"
        ),
    }

    header = {
        key: value
        for key, value in candidate.items()
        if key not in {"columns", "rows", "candidate_count", "structural_rule"}
    }
    header["source_candidate_count"] = source_count
    header["candidate_count"] = len(kept)
    header["structural_rule"] = rule
    header["selection_funnel"] = {
        "pre_gate_rows": len(rows),
        "post_gate_rows": len(kept),
        "eligible_industry_count": len(eligible_industries),
        "industry_fundamental_stage_counts": dict(fundamental_counts),
        "industry_market_stage_counts": dict(market_counts),
        "stock_lifecycle_stage_counts": dict(lifecycle_counts),
        "rejection_counts": dict(rejection_counts),
    }
    write_row_json(candidate_path, header, columns, kept)

    meta["source_candidate_count"] = source_count
    meta["candidate_count"] = len(kept)
    meta["structural_relevance_count"] = len(kept)
    meta["structural_rule"] = rule
    meta["selection_funnel"] = header["selection_funnel"]
    validation = meta.get("runtime_validation") or {}
    validation["status"] = "passed"
    validation["industry_dual_confirm_gate_applied"] = True
    validation["post_gate_candidate_count"] = len(kept)
    validation["eligible_industry_count"] = len(eligible_industries)
    meta["runtime_validation"] = validation
    write_json(meta_path, meta)

    print(
        json.dumps(
            {
                "pre_gate": len(rows),
                "post_gate": len(kept),
                "industries": len(eligible_industries),
                "fundamental_stages": dict(fundamental_counts),
                "market_stages": dict(market_counts),
                "lifecycle_stages": dict(lifecycle_counts),
                "rejections": dict(rejection_counts),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
