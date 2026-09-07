from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import median

try:
    from .build_full_market_price_structure import (
        MIN_POINTS as PRICE_STRUCTURE_MIN_POINTS,
        TARGET_POINTS as PRICE_STRUCTURE_TARGET_POINTS,
    )
    from .history_store import ROLLING_DAYS
except ImportError:  # direct script execution
    from build_full_market_price_structure import (
        MIN_POINTS as PRICE_STRUCTURE_MIN_POINTS,
        TARGET_POINTS as PRICE_STRUCTURE_TARGET_POINTS,
    )
    from history_store import ROLLING_DAYS

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SHARDS = DATA / "shards"
HISTORY_SHARDS = DATA / "history_shards"
COMMODITY = DATA / "commodity" / "futures_daily.json"
SHARD_KEY_LENGTH = 5
SAMPLES = ("002475", "601138", "601899")


def read_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def fnum(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def pct(part: int, total: int) -> float | None:
    if total <= 0:
        return None
    return round(part / total * 100, 2)


def build_market_breadth(latest_stocks: dict, trend_stocks: dict) -> dict:
    """Build objective main-board breadth inputs for the downstream market regime check.

    This deliberately does not produce a mechanical risk-on/risk-off score. It only
    summarizes broad participation and structure so the analysis layer does not infer
    the whole market from a small candidate list.
    """
    advancers = decliners = flat = 0
    quote_usable = 0

    above_ma20 = above_ma60 = 0
    bullish_intact = bearish_intact = 0
    transition_or_other = 0
    structure_usable = 0
    change_5d: list[float] = []
    change_20d: list[float] = []

    for code, quote in latest_stocks.items():
        if quote.get("confidence") not in {"high", "medium"}:
            continue
        price = fnum(quote.get("price"))
        prev_close = fnum(quote.get("prev_close"))
        if price is not None and price > 0 and prev_close is not None and prev_close > 0:
            quote_usable += 1
            if price > prev_close:
                advancers += 1
            elif price < prev_close:
                decliners += 1
            else:
                flat += 1

        trend = trend_stocks.get(code) or {}
        if trend.get("history_confidence") not in {"high", "medium"}:
            continue
        structure = trend.get("structure_60d") or {}
        ma20 = fnum(structure.get("ma20"))
        ma60 = fnum(structure.get("ma60"))
        last_close = fnum(trend.get("last_close"))
        evolution = structure.get("structure_evolution") or {}
        if last_close is None or last_close <= 0 or ma20 is None or ma60 is None:
            continue

        structure_usable += 1
        if last_close >= ma20:
            above_ma20 += 1
        if last_close >= ma60:
            above_ma60 += 1

        trend_state = evolution.get("trend_state")
        break_state = evolution.get("break_state")
        if trend_state == "bullish" and break_state == "intact":
            bullish_intact += 1
        elif trend_state == "bearish" and break_state == "intact":
            bearish_intact += 1
        else:
            transition_or_other += 1

        c5 = fnum(trend.get("close_change_5d_pct"))
        c20 = fnum(trend.get("close_change_20d_pct"))
        if c5 is not None:
            change_5d.append(c5)
        if c20 is not None:
            change_20d.append(c20)

    return {
        "scope": "sh_sz_main_board",
        "quote_usable": quote_usable,
        "advancers": advancers,
        "decliners": decliners,
        "flat": flat,
        "advancers_pct": pct(advancers, quote_usable),
        "decliners_pct": pct(decliners, quote_usable),
        "structure_usable": structure_usable,
        "above_ma20": above_ma20,
        "above_ma20_pct": pct(above_ma20, structure_usable),
        "above_ma60": above_ma60,
        "above_ma60_pct": pct(above_ma60, structure_usable),
        "bullish_intact": bullish_intact,
        "bullish_intact_pct": pct(bullish_intact, structure_usable),
        "bearish_intact": bearish_intact,
        "bearish_intact_pct": pct(bearish_intact, structure_usable),
        "transition_or_other": transition_or_other,
        "transition_or_other_pct": pct(transition_or_other, structure_usable),
        "median_5d_change_pct": round(median(change_5d), 2) if change_5d else None,
        "median_20d_change_pct": round(median(change_20d), 2) if change_20d else None,
        "interpretation": "objective_inputs_only_no_mechanical_market_score",
    }


def build_history_storage_coverage() -> dict:
    """Measure the persisted history store itself, not the 65-day summary view."""
    stocks = points_ge_min = points_ge_target = 0
    max_points = 0
    shard_files = sorted(HISTORY_SHARDS.glob("*.json"))

    for path in shard_files:
        payload = read_json(path, {"stocks": {}})
        for item in payload.get("stocks", {}).values():
            rows = [
                row
                for row in item.get("history", [])
                if row.get("date") and fnum(row.get("close")) not in (None, 0)
            ]
            points = len(rows)
            if points <= 0:
                continue
            stocks += 1
            max_points = max(max_points, points)
            if points >= PRICE_STRUCTURE_MIN_POINTS:
                points_ge_min += 1
            if points >= PRICE_STRUCTURE_TARGET_POINTS:
                points_ge_target += 1

    return {
        "stocks": stocks,
        "points_ge_price_structure_min": points_ge_min,
        "points_ge_price_structure_target": points_ge_target,
        "max_persisted_points": max_points,
        "shard_files": len(shard_files),
    }


def build_commodity_anchor_health() -> dict:
    """Expose compact, reproducible commodity anchors through authoritative health.json.

    Raw futures history remains in data/commodity/futures_daily.json for audit. Formal
    research reads this compact health block so commodity inputs stay inside the existing
    authoritative market-health contract.
    """
    payload = read_json(COMMODITY, {})
    anchors = {}
    for symbol, item in (payload.get("anchors") or {}).items():
        anchors[symbol] = {
            key: value
            for key, value in item.items()
            if key != "history"
        }
    return {
        "schema_version": payload.get("schema_version"),
        "generated_at": payload.get("generated_at"),
        "reference_trade_date": payload.get("reference_trade_date"),
        "source": payload.get("source"),
        "status": payload.get("status", "unavailable"),
        "max_anchor_age_days": payload.get("max_anchor_age_days"),
        "neutral_window_sessions": payload.get("neutral_window_sessions"),
        "minimum_neutral_sessions": payload.get("minimum_neutral_sessions"),
        "required_symbols": payload.get("required_symbols") or [],
        "anchors": anchors,
        "errors": payload.get("errors") or {},
        "runtime_semantics": (
            "Machine-readable cycle anchors. Missing/degraded anchors are cycle-specific; "
            "they do not invalidate non-cycle market data and must route eligible cycle "
            "companies to the conservative anchorless valuation fallback."
        ),
    }


def main() -> int:
    latest = read_json(DATA / "latest.json", {})
    trends = read_json(DATA / "trend_summary.json", {"stocks": {}})
    repair = read_json(DATA / "repair_status.json", {})
    latest_stocks = latest.get("stocks", {})
    trend_stocks = trends.get("stocks", {})
    summary_coverage = trends.get("coverage", {})
    storage_coverage = build_history_storage_coverage()
    SHARDS.mkdir(parents=True, exist_ok=True)

    for old in SHARDS.glob("*.json"):
        old.unlink()

    common = {
        "schema_version": 7,
        "generated_at": latest.get("generated_at"),
        "trade_date": latest.get("trade_date"),
        "market_status": latest.get("market_status"),
        "shard_key_length": SHARD_KEY_LENGTH,
    }

    groups: dict[str, dict] = defaultdict(dict)
    for code, q in latest_stocks.items():
        key = code[:SHARD_KEY_LENGTH]
        groups[key][code] = {
            "name": q.get("name"),
            "price": q.get("price"),
            "prev_close": q.get("prev_close"),
            "open": q.get("open"),
            "high": q.get("high"),
            "low": q.get("low"),
            "price_time": q.get("price_time"),
            "confidence": q.get("confidence"),
            "primary_source": q.get("primary_source"),
            "source_prices": q.get("source_prices"),
            "fundamentals": q.get("fundamentals"),
            "trend": trend_stocks.get(code),
        }

    for key, stocks in groups.items():
        payload = {**common, "shard": key, "stocks": stocks}
        (SHARDS / f"{key}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    health = {
        **common,
        "source_status": latest.get("source_status"),
        "validation_stats": latest.get("validation_stats"),
        "fundamental_stats": latest.get("fundamental_stats"),
        "shard_count": len(groups),
        "market_breadth": build_market_breadth(latest_stocks, trend_stocks),
        "commodity_anchors": build_commodity_anchor_health(),
        "history": {
            "storage": trends.get("history_storage"),
            "history_shard_key_length": trends.get("history_shard_key_length"),
            "summary_window_days": trends.get("history_window_days"),
            "summary_structure_window_days": trends.get("structure_window_days"),
            "storage_window_days": ROLLING_DAYS,
            "price_structure_min_points": PRICE_STRUCTURE_MIN_POINTS,
            "price_structure_target_points": PRICE_STRUCTURE_TARGET_POINTS,
            "summary_coverage": summary_coverage,
            "storage_coverage": storage_coverage,
            "semantics": {
                "summary_window_is_storage_window": False,
                "summary_source": "data/trend_summary.json",
                "storage_source": "data/history_shards/*.json",
                "price_structure_source": "data/history_shards/*.json",
                "interpretation": (
                    "The 65-session value is only the lightweight trend-summary view. "
                    "It must never be interpreted as persisted history length. "
                    "Formal price structure reads history_shards directly, requires at least "
                    f"{PRICE_STRUCTURE_MIN_POINTS} sessions, and targets "
                    f"{PRICE_STRUCTURE_TARGET_POINTS} sessions from the "
                    f"{ROLLING_DAYS}-session rolling store."
                ),
            },
            "corporate_action_repair": repair,
        },
        "sample_quotes": {
            code: {
                **(latest_stocks.get(code) or {}),
                "trend": trend_stocks.get(code),
            }
            for code in SAMPLES
        },
    }
    (DATA / "health.json").write_text(
        json.dumps(health, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"wrote {len(groups)} {SHARD_KEY_LENGTH}-digit quote shards; "
        f"summary >=5d: {summary_coverage.get('points_ge_5', 0)}, "
        f">=20d: {summary_coverage.get('points_ge_20', 0)}, "
        f">=60d: {summary_coverage.get('points_ge_60', 0)}, "
        f"storage >={PRICE_STRUCTURE_MIN_POINTS}d: "
        f"{storage_coverage.get('points_ge_price_structure_min', 0)}, "
        f">={PRICE_STRUCTURE_TARGET_POINTS}d: "
        f"{storage_coverage.get('points_ge_price_structure_target', 0)}, "
        f"fundamentals: {(latest.get('fundamental_stats') or {}).get('financial_usable', 0)}, "
        f"commodity anchors: {build_commodity_anchor_health().get('status')}, "
        f"repairs: {repair.get('repaired', 0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
