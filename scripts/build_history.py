from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
HISTORY_SHARDS_DIR = DATA_DIR / "history_shards"
OUTPUT = DATA_DIR / "trend_summary.json"
LATEST = DATA_DIR / "latest.json"

HISTORY_WINDOW = 65
STRUCTURE_WINDOW = 60
SWING_CONFIRMATION_WINDOW = 2
MAX_STRUCTURE_PIVOTS = 8
SWING_EQUAL_TOLERANCE_PCT = 0.001
INTRADAY_STATUSES = {"morning_session", "morning_closed", "afternoon_session"}
TENCENT_VOLUME_LOT_SIZE = 100


def read_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def fnum(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalized_volume(row: dict) -> float | None:
    """Return volume in shares across legacy qfq rows and live rows."""
    volume = fnum(row.get("volume"))
    if volume is None:
        return None
    if row.get("volume_unit") == "shares":
        return volume
    if row.get("basis") == "qfq" and row.get("source") == "tencent":
        return volume * TENCENT_VOLUME_LOT_SIZE
    return volume


def pct_change(first: float, last: float) -> float | None:
    if first == 0:
        return None
    return (last / first - 1) * 100


def _refresh_age_days(last_full_refresh: str | None, expected_trade_date: str | None) -> int | None:
    if not last_full_refresh or not expected_trade_date:
        return None
    try:
        refresh_date = datetime.fromisoformat(last_full_refresh).date()
        expected = date.fromisoformat(expected_trade_date)
    except ValueError:
        return None
    return (expected - refresh_date).days


def history_quality(
    rows: list[dict],
    *,
    expected_trade_date: str | None,
    last_full_refresh: str | None,
    history_may_end_before_trade_date: bool = False,
) -> tuple[str, list[str]]:
    warnings: list[str] = []
    if not rows:
        return "invalid", ["no_history"]

    dates = [str(r.get("date") or "") for r in rows]
    if any(not d for d in dates) or len(set(dates)) != len(dates):
        return "invalid", ["invalid_or_duplicate_dates"]

    for row in rows:
        o, h, l, c = map(fnum, (row.get("open"), row.get("high"), row.get("low"), row.get("close")))
        if c is None or c <= 0:
            return "invalid", ["invalid_close"]
        values = [x for x in (o, c, l) if x is not None]
        if h is not None and values and h + 1e-9 < max(values):
            return "invalid", ["ohlc_inconsistent"]
        values = [x for x in (o, c, h) if x is not None]
        if l is not None and values and l - 1e-9 > min(values):
            return "invalid", ["ohlc_inconsistent"]

    parsed = []
    for d in dates:
        try:
            parsed.append(date.fromisoformat(d))
        except ValueError:
            return "invalid", ["invalid_date_format"]

    last_date = dates[-1]
    if expected_trade_date:
        try:
            expected = date.fromisoformat(expected_trade_date)
            last_parsed = parsed[-1]
        except ValueError:
            return "invalid", ["invalid_expected_trade_date"]
        if history_may_end_before_trade_date:
            if last_parsed >= expected:
                return "invalid", ["intraday_or_future_date_in_completed_history"]
            if (expected - last_parsed).days > 10:
                warnings.append("completed_history_tail_too_old")
        elif last_date != expected_trade_date:
            warnings.append("last_date_not_latest_trade_date")

    if any((b - a).days > 14 for a, b in zip(parsed, parsed[1:])):
        warnings.append("large_calendar_gap")

    refresh_age = _refresh_age_days(last_full_refresh, expected_trade_date)
    if refresh_age is None:
        warnings.append("full_refresh_age_unknown")
    elif refresh_age > 10:
        warnings.append("full_refresh_older_than_10d")

    if len(rows) < 20:
        warnings.append("fewer_than_20_points")
        return "invalid", warnings
    if len(rows) < 60:
        warnings.append("fewer_than_60_points")
        return "medium", warnings
    if warnings:
        return "medium", warnings
    return "high", []


def _local_extrema(rows: list[dict], key: str, mode: str, window: int = 2) -> list[tuple[float, int, str]]:
    values = [fnum(r.get(key)) for r in rows]
    out: list[tuple[float, int, str]] = []
    for i in range(window, len(rows) - window):
        value = values[i]
        if value is None:
            continue
        neighbors = [v for v in values[i - window : i + window + 1] if v is not None]
        if not neighbors:
            continue
        if mode == "low" and value <= min(neighbors):
            out.append((value, i, str(rows[i].get("date"))))
        elif mode == "high" and value >= max(neighbors):
            out.append((value, i, str(rows[i].get("date"))))
    return out


def _cluster_levels(
    levels: list[tuple[float, int, str]],
    *,
    tolerance_pct: float = 0.025,
) -> list[dict]:
    clusters: list[list[tuple[float, int, str]]] = []
    for level in sorted(levels, key=lambda x: x[0]):
        if not clusters:
            clusters.append([level])
            continue
        center = mean(x[0] for x in clusters[-1])
        if center > 0 and abs(level[0] - center) / center <= tolerance_pct:
            clusters[-1].append(level)
        else:
            clusters.append([level])

    out = []
    for cluster in clusters:
        prices = [x[0] for x in cluster]
        center = mean(prices)
        if len(prices) == 1:
            zone_low, zone_high = center * 0.99, center * 1.01
        else:
            zone_low, zone_high = min(prices) * 0.995, max(prices) * 1.005
        latest = max(cluster, key=lambda x: x[1])
        out.append(
            {
                "low": round(zone_low, 4),
                "high": round(zone_high, 4),
                "center": round(center, 4),
                "touches": len(cluster),
                "last_touch_date": latest[2],
                "_last_index": latest[1],
            }
        )
    return out


def structure_zones(rows: list[dict], current_close: float) -> tuple[list[dict], list[dict]]:
    window = rows[-STRUCTURE_WINDOW:]
    lows = _local_extrema(window, "low", "low")
    highs = _local_extrema(window, "high", "high")

    supports = [z for z in _cluster_levels(lows) if z["center"] <= current_close * 1.02]
    resistances = [z for z in _cluster_levels(highs) if z["center"] >= current_close * 0.98]

    support_ranked = sorted(
        supports,
        key=lambda z: (-z["touches"], abs(current_close - z["center"]), -z["_last_index"]),
    )[:3]
    resistance_ranked = sorted(
        resistances,
        key=lambda z: (-z["touches"], abs(current_close - z["center"]), -z["_last_index"]),
    )[:3]

    for z in [*support_ranked, *resistance_ranked]:
        z.pop("_last_index", None)
    return support_ranked, resistance_ranked


def _swing_pivots(rows: list[dict], *, window: int = SWING_CONFIRMATION_WINDOW) -> list[dict]:
    """Return an alternating sequence of confirmed swing highs/lows.

    A pivot needs `window` completed sessions on both sides. A daily candle that is
    simultaneously a local high and low is skipped because daily OHLC does not reveal
    the intraday ordering needed to decide which pivot happened first.
    """
    lows = _local_extrema(rows, "low", "low", window=window)
    highs = _local_extrema(rows, "high", "high", window=window)
    by_index: dict[int, list[dict]] = {}
    for price, index, pivot_date in lows:
        by_index.setdefault(index, []).append(
            {"type": "low", "price": price, "date": pivot_date, "_index": index}
        )
    for price, index, pivot_date in highs:
        by_index.setdefault(index, []).append(
            {"type": "high", "price": price, "date": pivot_date, "_index": index}
        )

    candidates = [items[0] for _, items in sorted(by_index.items()) if len(items) == 1]
    pivots: list[dict] = []
    for pivot in candidates:
        if not pivots:
            pivots.append(pivot)
            continue
        previous = pivots[-1]
        if pivot["type"] != previous["type"]:
            pivots.append(pivot)
            continue

        more_extreme = (
            pivot["price"] <= previous["price"]
            if pivot["type"] == "low"
            else pivot["price"] >= previous["price"]
        )
        if more_extreme:
            pivots[-1] = pivot
    return pivots


def _label_swing_pivots(
    pivots: list[dict], *, tolerance_pct: float = SWING_EQUAL_TOLERANCE_PCT
) -> list[dict]:
    """Label confirmed highs/lows as HH/HL/LH/LL (or EH/EL when nearly equal)."""
    previous_price: dict[str, float] = {}
    labelled: list[dict] = []
    for pivot in pivots:
        item = dict(pivot)
        pivot_type = item["type"]
        price = float(item["price"])
        previous = previous_price.get(pivot_type)
        label = None
        if previous is not None:
            upper = previous * (1 + tolerance_pct)
            lower = previous * (1 - tolerance_pct)
            if pivot_type == "high":
                label = "HH" if price > upper else "LH" if price < lower else "EH"
            else:
                label = "HL" if price > upper else "LL" if price < lower else "EL"
        item["label"] = label
        labelled.append(item)
        previous_price[pivot_type] = price
    return labelled


def _structure_trend_state(pivots: list[dict]) -> str:
    latest_high = next((p for p in reversed(pivots) if p["type"] == "high" and p.get("label")), None)
    latest_low = next((p for p in reversed(pivots) if p["type"] == "low" and p.get("label")), None)
    if latest_high is None or latest_low is None:
        return "insufficient"
    if latest_high["label"] == "HH" and latest_low["label"] == "HL":
        return "bullish"
    if latest_high["label"] == "LH" and latest_low["label"] == "LL":
        return "bearish"
    return "transition"


def structure_evolution(
    rows: list[dict],
    current_close: float,
    *,
    pivot_window: int = SWING_CONFIRMATION_WINDOW,
    max_pivots: int = MAX_STRUCTURE_PIVOTS,
) -> dict:
    """Describe 60d swing evolution without treating unconfirmed bars as pivots."""
    window_rows = rows[-STRUCTURE_WINDOW:]
    pivots = _label_swing_pivots(_swing_pivots(window_rows, window=pivot_window))
    trend_state = _structure_trend_state(pivots)
    previous_state = _structure_trend_state(pivots[:-1]) if pivots else "insufficient"
    latest_high = next((p for p in reversed(pivots) if p["type"] == "high"), None)
    latest_low = next((p for p in reversed(pivots) if p["type"] == "low"), None)
    latest_pivot = pivots[-1] if pivots else None

    break_state = "insufficient" if trend_state == "insufficient" else "transition"
    invalidation = None
    if trend_state == "bullish" and latest_low is not None:
        invalidation = {"direction": "below", "price": round(float(latest_low["price"]), 4)}
        break_state = (
            "bullish_structure_under_threat"
            if current_close < float(latest_low["price"])
            else "intact"
        )
    elif trend_state == "bearish" and latest_high is not None:
        invalidation = {"direction": "above", "price": round(float(latest_high["price"]), 4)}
        break_state = (
            "bearish_structure_under_threat"
            if current_close > float(latest_high["price"])
            else "intact"
        )
    elif (
        previous_state == "bullish"
        and latest_pivot is not None
        and latest_pivot["type"] == "low"
        and latest_pivot.get("label") == "LL"
    ):
        break_state = "bullish_structure_break_confirmed"
    elif (
        previous_state == "bearish"
        and latest_pivot is not None
        and latest_pivot["type"] == "high"
        and latest_pivot.get("label") == "HH"
    ):
        break_state = "bearish_structure_break_confirmed"

    def public_pivot(pivot: dict | None) -> dict | None:
        if pivot is None:
            return None
        return {
            "date": pivot["date"],
            "type": pivot["type"],
            "price": round(float(pivot["price"]), 4),
            "label": pivot.get("label"),
        }

    return {
        "pivot_window": pivot_window,
        "confirmation_lag_sessions": pivot_window,
        "trend_state": trend_state,
        "break_state": break_state,
        "invalidation": invalidation,
        "latest_high": public_pivot(latest_high),
        "latest_low": public_pivot(latest_low),
        "pivots": [public_pivot(p) for p in pivots[-max_pivots:]],
    }


def price_density_zones(rows: list[dict], current_close: float) -> list[dict]:
    """Cluster repeated closing prices into compact 60d trading-density zones."""
    window = rows[-STRUCTURE_WINDOW:]
    observations: list[tuple[float, int, str]] = []
    for i, row in enumerate(window):
        value = fnum(row.get("close"))
        if value is not None and value > 0:
            observations.append((value, i, str(row.get("date"))))
    if len(observations) < 5:
        return []

    typical = median(x[0] for x in observations)
    bin_width = max(typical * 0.025, 0.01)
    bins: dict[int, list[tuple[float, int, str]]] = {}
    for obs in observations:
        bucket = int(obs[0] // bin_width)
        bins.setdefault(bucket, []).append(obs)

    zones: list[dict] = []
    for obs in bins.values():
        if len(obs) < 2:
            continue
        prices = [x[0] for x in obs]
        center = mean(prices)
        low = min(prices) * 0.995
        high = max(prices) * 1.005
        latest = max(obs, key=lambda x: x[1])
        if high < current_close * 0.99:
            relation = "below"
        elif low > current_close * 1.01:
            relation = "above"
        else:
            relation = "current"
        zones.append(
            {
                "low": round(low, 4),
                "high": round(high, 4),
                "center": round(center, 4),
                "closes": len(obs),
                "relation": relation,
                "last_date": latest[2],
                "_last_index": latest[1],
            }
        )

    zones = sorted(
        zones,
        key=lambda z: (-z["closes"], abs(current_close - z["center"]), -z["_last_index"]),
    )[:5]
    for z in zones:
        z.pop("_last_index", None)
    return zones


def volume_profile_zones(rows: list[dict], current_close: float) -> list[dict]:
    """Approximate 60d volume-at-price zones using normalized share volume."""
    window = rows[-STRUCTURE_WINDOW:]
    observations: list[tuple[float, float, int, str]] = []
    for i, row in enumerate(window):
        close = fnum(row.get("close"))
        high = fnum(row.get("high"))
        low = fnum(row.get("low"))
        volume = normalized_volume(row)
        if close is None or close <= 0 or volume is None or volume <= 0:
            continue
        typical_price = mean([x for x in (high, low, close) if x is not None])
        observations.append((typical_price, volume, i, str(row.get("date"))))
    if len(observations) < 5:
        return []

    typical = median(x[0] for x in observations)
    bin_width = max(typical * 0.025, 0.01)
    bins: dict[int, list[tuple[float, float, int, str]]] = {}
    total_volume = sum(x[1] for x in observations)
    for obs in observations:
        bucket = int(obs[0] // bin_width)
        bins.setdefault(bucket, []).append(obs)

    zones: list[dict] = []
    for obs in bins.values():
        bin_volume = sum(x[1] for x in obs)
        if bin_volume <= 0:
            continue
        prices = [x[0] for x in obs]
        center = sum(x[0] * x[1] for x in obs) / bin_volume
        low = min(prices) * 0.995
        high = max(prices) * 1.005
        latest = max(obs, key=lambda x: x[2])
        if high < current_close * 0.99:
            relation = "below"
        elif low > current_close * 1.01:
            relation = "above"
        else:
            relation = "current"
        zones.append(
            {
                "low": round(low, 4),
                "high": round(high, 4),
                "center": round(center, 4),
                "volume_share_pct": round(bin_volume / total_volume * 100, 2) if total_volume else 0.0,
                "days": len(obs),
                "relation": relation,
                "last_date": latest[3],
                "_last_index": latest[2],
            }
        )

    zones = sorted(
        zones,
        key=lambda z: (-z["volume_share_pct"], abs(current_close - z["center"]), -z["_last_index"]),
    )[:5]
    for z in zones:
        z.pop("_last_index", None)
    return zones


def build_stock_summary(
    item: dict,
    *,
    expected_trade_date: str | None,
    history_may_end_before_trade_date: bool = False,
) -> dict | None:
    rows = [r for r in item.get("history", []) if fnum(r.get("close")) not in (None, 0)]
    rows = sorted(rows, key=lambda r: str(r.get("date") or ""))[-HISTORY_WINDOW:]
    if not rows:
        return None

    closes = [float(r["close"]) for r in rows]
    points = len(rows)
    last5 = rows[-5:]
    last20 = rows[-20:]
    last60 = rows[-60:]
    last5_closes = [float(r["close"]) for r in last5]
    last20_closes = [float(r["close"]) for r in last20]
    last60_closes = [float(r["close"]) for r in last60]
    current_close = closes[-1]

    quality, quality_warnings = history_quality(
        rows,
        expected_trade_date=expected_trade_date,
        last_full_refresh=item.get("last_full_refresh"),
        history_may_end_before_trade_date=history_may_end_before_trade_date,
    )

    high20 = max(float(r.get("high") or r["close"]) for r in last20)
    low20 = min(float(r.get("low") or r["close"]) for r in last20)

    out = {
        "points": points,
        "last_date": rows[-1].get("date"),
        "last_close": current_close,
        "history_confidence": quality,
        "history_warnings": quality_warnings,
        "history_basis": item.get("history_basis"),
        "last_full_refresh": item.get("last_full_refresh"),
        "high_20d": high20,
        "low_20d": low20,
        "close_change_5d_pct": pct_change(last5_closes[0], last5_closes[-1]) if points >= 5 else None,
        "close_change_20d_pct": pct_change(last20_closes[0], last20_closes[-1]) if points >= 20 else None,
        "last5": [{"date": r.get("date"), "close": r.get("close")} for r in last5],
    }

    if points >= 60:
        high60 = max(float(r.get("high") or r["close"]) for r in last60)
        low60 = min(float(r.get("low") or r["close"]) for r in last60)
        supports, resistances = structure_zones(last60, current_close)
        evolution = structure_evolution(last60, current_close)
        dense_zones = price_density_zones(last60, current_close)
        volume_zones = volume_profile_zones(last60, current_close)
        out["structure_60d"] = {
            "points": len(last60),
            "high": high60,
            "low": low60,
            "close_change_pct": pct_change(last60_closes[0], last60_closes[-1]),
            "ma20": mean(last20_closes),
            "ma60": mean(last60_closes),
            "position_pct": (current_close - low60) / (high60 - low60) * 100 if high60 > low60 else 50.0,
            "support_zones": supports,
            "resistance_zones": resistances,
            "structure_evolution": evolution,
            "dense_price_zones": dense_zones,
            "volume_profile_method": "daily_typical_price_approx",
            "volume_profile_unit": "shares",
            "volume_profile_zones": volume_zones,
        }
    else:
        out["structure_60d"] = None

    return out


def main() -> int:
    latest = read_json(LATEST, {})
    expected_trade_date = latest.get("trade_date")
    history_may_end_before_trade_date = latest.get("market_status") in INTRADAY_STATUSES
    out = {
        "schema_version": 6,
        "history_storage": "rolling_shards",
        "history_window_days": HISTORY_WINDOW,
        "history_shard_key_length": 4,
        "structure_window_days": STRUCTURE_WINDOW,
        "volume_unit": "shares",
        "stocks": {},
    }
    shard_files = sorted(HISTORY_SHARDS_DIR.glob("*.json"))
    coverage_5d = coverage_20d = coverage_60d = 0
    quality_counts = {"high": 0, "medium": 0, "invalid": 0}
    max_points = 0

    for path in shard_files:
        payload = read_json(path, {"stocks": {}})
        for code, item in payload.get("stocks", {}).items():
            summary = build_stock_summary(
                item,
                expected_trade_date=expected_trade_date,
                history_may_end_before_trade_date=history_may_end_before_trade_date,
            )
            if summary is None:
                continue
            points = summary["points"]
            max_points = max(max_points, points)
            if points >= 5:
                coverage_5d += 1
            if points >= 20:
                coverage_20d += 1
            if points >= 60:
                coverage_60d += 1
            quality_counts[summary["history_confidence"]] += 1
            out["stocks"][code] = summary

    total = len(out["stocks"])
    out["coverage"] = {
        "stocks": total,
        "points_ge_5": coverage_5d,
        "points_ge_20": coverage_20d,
        "points_ge_60": coverage_60d,
        "history_confidence": quality_counts,
        "max_points": max_points,
        "shard_files": len(shard_files),
    }
    OUTPUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out["coverage"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
