#!/usr/bin/env python3
"""Apply the V6 stock lifecycle gate after the industry-first snapshot.

Important invariant: industry selection has already happened upstream. This file
must NOT recreate a strict financial/volume industry gate from each stock row.
Its only job is to classify stocks inside the prequalified industry pool into
useful early/low-risk lifecycle states and reject genuine fade/distribution.
"""

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


def drawdown_from_high(row: list[Any], index: dict[str, int]) -> float | None:
    price = num(at(row, index, "price"))
    high = num(at(row, index, "high_20d"))
    if price is None or high is None or high <= 0:
        return None
    return max(0.0, (high - price) / high * 100.0)


def prior_swing_pct(row: list[Any], index: dict[str, int]) -> float | None:
    high = num(at(row, index, "high_20d"))
    low = num(at(row, index, "low_20d"))
    if high is None or low is None or low <= 0:
        return None
    return max(0.0, (high / low - 1.0) * 100.0)


def reacceleration(row: list[Any], index: dict[str, int]) -> bool:
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
        and price >= ma20 * 0.99
        and day >= 2.0
        and close5 >= -1.0
        and ret20 <= 12.0
        and rs20 > 0.0
        and vol1 >= 1.50
        and dd <= 6.0
    )


def classify_lifecycle(
    row: list[Any], index: dict[str, int]
) -> tuple[str | None, str | None, float | None, float | None]:
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
    support_distance = num(at(row, index, "support_distance_pct"))
    distance_ma20 = num(at(row, index, "distance_to_ma20_pct"))
    breakout = at(row, index, "breakout_confirmed") is True
    strong_volume_zone = at(row, index, "strong_volume_zone") is True
    dd = drawdown_from_high(row, index)
    swing = prior_swing_pct(row, index)

    if chase == "high":
        return None, "high_chase_risk", dd, swing
    if price is None or ret20 is None or rs20 is None or dd is None:
        return None, "lifecycle_data_missing", dd, swing

    is_reaccel = reacceleration(row, index)

    # Distribution is directional: high volume on a falling day after a pullback
    # is not interpreted as fresh money entering.
    if (
        day is not None
        and day < 0.0
        and vol1 is not None
        and vol1 >= 1.50
        and dd >= 3.0
    ):
        return None, "distribution_risk", dd, swing

    # A completed large swing followed by a weakening pullback is the pattern we
    # previously misclassified as low-risk. Exclude it unless a fresh reaccel is
    # already visible.
    if (
        swing is not None
        and swing >= 18.0
        and dd >= 5.0
        and close5 is not None
        and close5 < 0.0
        and not is_reaccel
    ):
        return None, "post_peak_fade", dd, swing

    if (
        ma20 is not None
        and price < ma20 * 0.97
        and close5 is not None
        and close5 < 0.0
        and not is_reaccel
    ):
        return None, "structure_lost", dd, swing

    if (
        position is not None
        and position >= 75.0
        and dd >= 5.0
        and close5 is not None
        and close5 < 0.0
        and vol5 is not None
        and vol5 >= 1.10
        and not is_reaccel
    ):
        return None, "high_zone_fade", dd, swing

    if tier == "active_pullback" and is_reaccel:
        return "REACCELERATION", None, dd, swing

    if (
        tier == "starting_breakout"
        and breakout
        and ret20 <= 15.0
        and rs20 > 0.0
        and dd <= 3.0
        and (day is None or day >= 0.0)
        and (
            (vol1 is not None and vol1 >= 1.20)
            or (vol5 is not None and vol5 >= 1.10)
        )
    ):
        return "FRESH_ACTIVATION", None, dd, swing

    if (
        tier == "pre_breakout"
        and ret20 <= 12.0
        and rs20 >= -0.5
        and dd <= 8.0
        and (ma20 is None or price >= ma20 * 0.97)
        and (
            (vol1 is not None and vol1 >= 1.00)
            or (vol5 is not None and vol5 >= 1.00)
            or strong_volume_zone
        )
    ):
        return "PRE_BREAKOUT", None, dd, swing

    if (
        tier == "accumulation_base"
        and ret20 <= 10.0
        and rs20 >= -1.0
        and dd <= 10.0
        and (
            (vol1 is not None and vol1 >= 1.00)
            or (vol5 is not None and vol5 >= 1.00)
            or strong_volume_zone
        )
    ):
        return "ACCUMULATION_READY", None, dd, swing

    if (
        tier == "early_trend"
        and ret20 <= 12.0
        and rs20 > 0.0
        and dd <= 5.0
        and close5 is not None
        and close5 >= 0.0
        and (ma20 is None or price >= ma20 * 0.98)
        and (
            (vol1 is not None and vol1 >= 1.10)
            or (vol5 is not None and vol5 >= 1.05)
        )
    ):
        return "EARLY_EXPANSION", None, dd, swing

    # The key V6 repair: a broad-market selloff can create a better entry in a
    # strong industry. A healthy first pullback is allowed when the prior move was
    # not excessive, relative strength remains intact, the stock stays near MA20/
    # support, and volume does not look like distribution.
    if tier in {"active_pullback", "early_trend"}:
        near_structure = (
            (distance_ma20 is not None and abs(distance_ma20) <= 3.0)
            or (support_distance is not None and support_distance <= 4.0)
            or strong_volume_zone
        )
        pullback_volume_ok = (
            vol5 is None
            or vol5 <= 1.10
            or (day is not None and day > 0.0 and vol1 is not None and vol1 >= 1.10)
        )
        prior_move_not_excessive = (
            swing is None or swing <= 18.0 or ret20 <= 8.0
        )
        if (
            2.0 <= dd <= 8.0
            and ret20 <= 12.0
            and rs20 >= 0.0
            and (ma20 is None or price >= ma20 * 0.97)
            and (close5 is None or close5 >= -6.0)
            and near_structure
            and pullback_volume_ok
            and prior_move_not_excessive
        ):
            return "HEALTHY_FIRST_PULLBACK", None, dd, swing

    return None, "stock_not_early_or_low_risk", dd, swing


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", default="data/runtime")
    args = parser.parse_args()

    runtime_dir = Path(args.runtime_dir)
    meta_path = runtime_dir / "meta.json"
    meta = load_json(meta_path)
    candidate_path = Path(meta["candidate_file"])
    candidate = load_json(candidate_path)
    columns = list(candidate.get("columns") or [])
    rows = candidate.get("rows") or []
    index = {name: i for i, name in enumerate(columns)}

    industry_pool = ((meta.get("snapshot") or {}).get("industry_pool") or {})
    if not isinstance(industry_pool, dict) or not industry_pool:
        raise SystemExit("V6 requires snapshot.industry_pool to be non-empty")

    required = {
        "code",
        "price",
        "industry_code",
        "activation_tier",
        "chase_risk",
        "volume_ratio_1d_vs_20d",
        "volume_ratio_5d_vs_20d",
        "relative_strength_20d_vs_market_pct",
        "return_20d_pct",
        "distance_to_ma20_pct",
        "close_change_5d_pct",
        "high_20d",
        "low_20d",
        "ma20",
        "position_pct",
        "support_distance_pct",
        "strong_volume_zone",
        "breakout_confirmed",
    }
    missing = sorted(required - set(columns))
    if missing:
        raise SystemExit(f"stock lifecycle gate missing columns: {missing}")

    kept: list[list[Any]] = []
    lifecycle_counts: Counter[str] = Counter()
    rejection_counts: Counter[str] = Counter()
    kept_industries: set[str] = set()

    for row in rows:
        industry_code = str(at(row, index, "industry_code") or "")
        if industry_code not in industry_pool:
            rejection_counts["industry_pool_mismatch"] += 1
            continue

        stage, reason, dd, swing = classify_lifecycle(row, index)
        if not stage:
            rejection_counts[str(reason or "unknown")] += 1
            continue

        kept.append([*row, stage, dd, swing])
        lifecycle_counts[stage] += 1
        kept_industries.add(industry_code)

    output_columns = [
        *columns,
        "stock_lifecycle_stage",
        "drawdown_from_20d_high_pct",
        "prior_20d_swing_pct",
    ]

    source_count = int(candidate.get("source_candidate_count") or len(rows))
    rule = {
        "selection_mode": "industry_first_leading_prosperity_then_stock",
        "industry_prefilter": [
            "PROFIT_TREND_CONFIRMED",
            "EARNINGS_IMPROVING",
            "EARNINGS_TRANSMITTING",
        ],
        "industry_market_prefilter": ["FUNDS_ATTENTION", "FUNDS_ENTERING"],
        "leading_prosperity_public_research_required": True,
        "stock_universe_scope": (
            "all structurally usable profitable companies inside prequalified industries"
        ),
        "stock_lifecycle_gate": [
            "PRE_BREAKOUT",
            "ACCUMULATION_READY",
            "FRESH_ACTIVATION",
            "EARLY_EXPANSION",
            "HEALTHY_FIRST_PULLBACK",
            "REACCELERATION",
        ],
        "post_peak_fade_allowed": False,
        "distribution_risk_allowed": False,
        "valuation_hard_ceiling": None,
        "note": (
            "industry comes first; public leading-indicator research confirms prosperity; "
            "healthy first pullbacks are allowed, completed-wave fades are not"
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
        "prequalified_industry_count": len(industry_pool),
        "pre_lifecycle_rows": len(rows),
        "post_lifecycle_rows": len(kept),
        "post_lifecycle_industry_count": len(kept_industries),
        "stock_lifecycle_stage_counts": dict(sorted(lifecycle_counts.items())),
        "rejection_counts": dict(sorted(rejection_counts.items())),
        # Compatibility aliases for older display code only.
        "pre_gate_rows": len(rows),
        "post_gate_rows": len(kept),
        "eligible_industry_count": len(kept_industries),
    }
    write_row_json(candidate_path, header, output_columns, kept)

    meta["source_candidate_count"] = source_count
    meta["candidate_count"] = len(kept)
    meta["structural_relevance_count"] = len(kept)
    meta["candidate_columns"] = output_columns
    meta["structural_rule"] = rule
    meta["selection_funnel"] = header["selection_funnel"]
    validation = meta.get("runtime_validation") or {}
    validation["status"] = "passed"
    validation["industry_first_pool_applied"] = True
    validation["stock_lifecycle_gate_applied"] = True
    validation["prequalified_industry_count"] = len(industry_pool)
    validation["post_lifecycle_candidate_count"] = len(kept)
    validation["post_lifecycle_industry_count"] = len(kept_industries)
    validation.pop("industry_dual_confirm_gate_applied", None)
    validation.pop("post_gate_candidate_count", None)
    validation.pop("eligible_industry_count", None)
    meta["runtime_validation"] = validation
    write_json(meta_path, meta)

    print(
        json.dumps(
            {
                "prequalified_industries": len(industry_pool),
                "pre_lifecycle": len(rows),
                "post_lifecycle": len(kept),
                "post_lifecycle_industries": len(kept_industries),
                "lifecycle_stages": dict(sorted(lifecycle_counts.items())),
                "rejections": dict(sorted(rejection_counts.items())),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
