from __future__ import annotations

import json
import math
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
LATEST = ROOT / "data/latest.json"
HISTORY_DIR = ROOT / "data/history_shards"
OUT = ROOT / "data/research/full_market_price_structure.json"
TZ = ZoneInfo("Asia/Shanghai")
MIN_POINTS = 120
TARGET_POINTS = 180
RS_FLOOR = -0.02


def f(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def load(path: Path, default=None):
    if not path.exists():
        return {} if default is None else default
    return json.loads(path.read_text(encoding="utf-8"))


def risk_warning(name: str) -> tuple[bool, str | None]:
    text = str(name or "").strip()
    upper = text.upper()
    if "ST" in upper:
        return True, "ST_or_star_ST"
    if "退" in text:
        return True, "delisting_risk_name"
    return False, None


@lru_cache(maxsize=24)
def load_prefix_history(prefix: str) -> dict:
    """Bounded cache: parse each 4-digit OHLCV shard once, not once per stock."""
    return load(HISTORY_DIR / f"{prefix}.json", {})


def rows_for(code: str) -> list[dict]:
    shard = load_prefix_history(code[:4])
    item = (shard.get("stocks") or {}).get(code) or {}
    rows = []
    for r in item.get("history", []):
        close, high, low = f(r.get("close")), f(r.get("high")), f(r.get("low"))
        if close is None or high is None or low is None or close <= 0:
            continue
        rows.append(
            {
                "date": str(r.get("date") or ""),
                "open": f(r.get("open")),
                "close": close,
                "high": high,
                "low": low,
                "volume": f(r.get("volume")),
            }
        )
    return sorted([r for r in rows if r["date"]], key=lambda x: x["date"])[-TARGET_POINTS:]


def sma(values: list[float], n: int, offset: int = 0):
    end = len(values) - offset if offset else len(values)
    start = end - n
    if start < 0:
        return None
    part = values[start:end]
    return sum(part) / n if len(part) == n else None


def pivots(rows: list[dict], window: int = 3):
    highs, lows = [], []
    for i in range(window, len(rows) - window):
        hi, lo = rows[i]["high"], rows[i]["low"]
        if all(hi >= rows[j]["high"] for j in range(i - window, i + window + 1)):
            highs.append({"date": rows[i]["date"], "price": hi})
        if all(lo <= rows[j]["low"] for j in range(i - window, i + window + 1)):
            lows.append({"date": rows[i]["date"], "price": lo})
    return highs, lows


def atr_pct(rows: list[dict], n: int = 14):
    if len(rows) < n + 1:
        return None
    trs = []
    for i in range(len(rows) - n, len(rows)):
        prev = rows[i - 1]["close"]
        trs.append(
            max(
                rows[i]["high"] - rows[i]["low"],
                abs(rows[i]["high"] - prev),
                abs(rows[i]["low"] - prev),
            )
        )
    return (sum(trs) / len(trs)) / rows[-1]["close"]


def volume_metrics(rows: list[dict]):
    prev20 = [
        r["volume"]
        for r in rows[-21:-1]
        if isinstance(r.get("volume"), (int, float)) and r["volume"] > 0
    ]
    recent5 = [
        r["volume"]
        for r in rows[-5:]
        if isinstance(r.get("volume"), (int, float)) and r["volume"] > 0
    ]
    current = rows[-1].get("volume")
    avg20 = sum(prev20) / len(prev20) if len(prev20) >= 10 else None
    avg5 = sum(recent5) / len(recent5) if recent5 else None
    ratio1 = current / avg20 if avg20 and current else None
    ratio5 = avg5 / avg20 if avg20 and avg5 else None
    last = rows[-1]
    span = last["high"] - last["low"]
    close_location = (last["close"] - last["low"]) / span if span > 0 else 0.5
    return ratio1, ratio5, close_location




def trend_phase_metrics(rows, ma20, ma60, current, ratio1, ratio5, close_location):
    """Compute compact, past-only price/volume evidence once in the data layer.

    No OHLCV arrays are forwarded to the research model. These diagnostics
    describe *new-entry* opportunities rather than the quality of an existing
    holding, and never assert the identity of capital flows.
    """
    recent = rows[-11:]
    closes = [r["close"] for r in recent]
    prev20_vol = [r["volume"] for r in rows[-21:-1] if f(r.get("volume")) and r["volume"] > 0]
    avg20 = sum(prev20_vol) / len(prev20_vol) if len(prev20_vol) >= 10 else None
    changes = [(recent[i], recent[i]["close"] / recent[i-1]["close"] - 1)
               for i in range(1, len(recent))]
    last5 = changes[-5:]
    up = [bar["volume"] for bar, ret in last5 if ret > 0 and f(bar.get("volume"))]
    down = [bar["volume"] for bar, ret in last5 if ret < 0 and f(bar.get("volume"))]
    def volume_ratio(xs):
        return round(sum(xs) / len(xs) / avg20, 3) if avg20 and xs else None
    def pct(a, b):
        return round((a / b - 1) * 100, 2) if b else None

    previous5_high = max(r["high"] for r in rows[-6:-1])
    previous20_low = min(r["low"] for r in rows[-21:-1])
    recent3_low = min(r["low"] for r in rows[-3:])
    last3_locs = [
        (r["close"] - r["low"]) / (r["high"] - r["low"])
        for r in rows[-3:] if r["high"] > r["low"]
    ]
    recent_3d_return = pct(current, closes[-4])
    recent_5d_return = pct(current, closes[-6])
    earlier_5d_return = pct(closes[-6], closes[0])
    peak = closes[0]
    max_dd = 0.0
    for close in closes[1:]:
        peak = max(peak, close)
        max_dd = min(max_dd, close / peak - 1)

    up_volume = volume_ratio(up)
    down_volume = volume_ratio(down)
    positive_days = sum(ret > 0 for _, ret in last5)
    negative_days = sum(ret < 0 for _, ret in last5)
    pullback_low_holds = current >= previous20_low * 0.98
    strong_close = close_location >= 0.6
    weak_close = close_location <= 0.35
    meaningful_volume = bool(ratio1 is not None and ratio1 >= 1.4)
    improving = (recent_3d_return is not None and recent_3d_return > 1
                 and positive_days >= 2 and (ratio5 or 0) >= 1.05)
    prior_advance = earlier_5d_return is not None and earlier_5d_return > 4
    fresh_break = current > previous5_high * 1.002
    short_advance = recent_5d_return is not None and recent_5d_return > 10
    cooling_signal = (
        (short_advance or current > ma20 * 1.08)
        and meaningful_volume and weak_close
        and (last5[-1][1] < 0 or last3_locs and sum(last3_locs)/len(last3_locs) < .45)
    )
    broken_structure = (current < previous20_low * .98
                        and recent_5d_return is not None and recent_5d_return < -5
                        and negative_days >= 3)
    if broken_structure:
        phase = "FAILED"
    elif cooling_signal:
        phase = "COOLING"
    elif improving and (current < ma60 or current < ma20):
        phase = "REPAIRING"
    elif (improving and fresh_break and prior_advance
          and pullback_low_holds and strong_close):
        phase = "REACCELERATING"
    elif (improving and fresh_break and strong_close and meaningful_volume):
        phase = "INITIATING"
    elif prior_advance and recent_5d_return is not None and recent_5d_return < 1 and pullback_low_holds:
        phase = "PULLBACK"
    elif improving:
        phase = "REPAIRING" if current < ma60 else "TRANSITION"
    else:
        phase = "TRANSITION"

    return {
        "trend_phase": phase,
        "phase_evidence": {
            "return_3d_pct": recent_3d_return,
            "return_5d_pct": recent_5d_return,
            "previous_5d_return_pct": earlier_5d_return,
            "positive_days_5d": positive_days,
            "negative_days_5d": negative_days,
            "up_day_volume_ratio_5d": up_volume,
            "down_day_volume_ratio_5d": down_volume,
            "volume_ratio_1d": round(ratio1, 3) if ratio1 is not None else None,
            "volume_ratio_5d": round(ratio5, 3) if ratio5 is not None else None,
            "close_location_pct": round(close_location * 100, 2),
            "close_location_3d_avg_pct": round(sum(last3_locs)/len(last3_locs)*100, 2) if last3_locs else None,
            "max_close_drawdown_10d_pct": round(max_dd * 100, 2),
            "prior_5d_high": round(previous5_high, 4),
            "prior_20d_low": round(previous20_low, 4),
            "recent_3d_low": round(recent3_low, 4),
            "fresh_break": fresh_break,
            "pullback_low_holds": pullback_low_holds,
            "weak_close_high_volume": meaningful_volume and weak_close,
            "signal_uses_completed_bars_only": True
        }
    }

def base_metrics(code: str, name: str, rows: list[dict], quote: dict, reference_date: str):
    flagged, flag_reason = risk_warning(name)
    base_flags = {
        "risk_warning": flagged,
        "risk_warning_reason": flag_reason,
        "low_risk_eligible": not flagged,
    }
    if len(rows) < MIN_POINTS:
        return {
            "code": code,
            "name": name,
            **base_flags,
            "data_status": "unavailable",
            "reason": f"history_insufficient:{len(rows)}",
        }
    if rows[-1]["date"] != reference_date:
        return {
            "code": code,
            "name": name,
            **base_flags,
            "data_status": "unavailable",
            "reason": f"history_stale:{rows[-1]['date']}!={reference_date}",
        }

    closes = [r["close"] for r in rows]
    current = f(quote.get("price")) or closes[-1]
    ma20, ma60 = sma(closes, 20), sma(closes, 60)
    ma20_5, ma60_5 = sma(closes, 20, 5), sma(closes, 60, 5)
    highs, lows = pivots(rows[-120:], 3)
    recent_highs, recent_lows = highs[-3:], lows[-3:]
    hh = len(recent_highs) >= 2 and recent_highs[-1]["price"] > recent_highs[-2]["price"]
    hl = len(recent_lows) >= 2 and recent_lows[-1]["price"] > recent_lows[-2]["price"]
    ret10 = current / closes[-11] - 1
    ret20 = current / closes[-21] - 1
    dist20 = current / ma20 - 1
    dist60 = current / ma60 - 1
    slope20 = ma20 / ma20_5 - 1
    slope60 = ma60 / ma60_5 - 1
    prev60_high = max(r["high"] for r in rows[-61:-1])
    prev120_high = max(r["high"] for r in rows[-121:-1])
    ratio1, ratio5, close_loc = volume_metrics(rows)
    phase = trend_phase_metrics(rows, ma20, ma60, current, ratio1, ratio5, close_loc)

    resistance = None
    above = [p for p in highs if p["price"] > current * 1.005]
    if above:
        resistance = min(above, key=lambda x: x["price"])
    elif current < prev120_high * 0.995:
        resistance = {"date": None, "price": prev120_high, "source": "prior_120d_high"}

    supports = [x["price"] for x in recent_lows if x["price"] < current]
    if ma20 < current:
        supports.append(ma20)
    if ma60 < current:
        supports.append(ma60)
    support = max(supports) if supports else min(r["low"] for r in rows[-20:])

    return {
        "code": code,
        "name": name,
        **base_flags,
        "data_status": "verified",
        "data_date": rows[-1]["date"],
        "history_points": len(rows),
        **phase,
        "current_price": round(current, 4),
        "ma20": round(ma20, 4),
        "ma60": round(ma60, 4),
        "ma20_slope_5d_pct": round(slope20 * 100, 2),
        "ma60_slope_5d_pct": round(slope60 * 100, 2),
        "return_10d_pct": round(ret10 * 100, 2),
        "return_20d_pct": round(ret20 * 100, 2),
        "distance_to_ma20_pct": round(dist20 * 100, 2),
        "distance_to_ma60_pct": round(dist60 * 100, 2),
        "atr14_pct": round((atr_pct(rows) or 0) * 100, 2),
        "prior_60d_high": round(prev60_high, 4),
        "prior_120d_high": round(prev120_high, 4),
        "higher_high": hh,
        "higher_low": hl,
        "first_effective_resistance": resistance,
        "support_invalidation": round(support, 4),
        "volume_ratio_1d_vs_20d": round(ratio1, 3) if ratio1 is not None else None,
        "volume_ratio_5d_vs_20d": round(ratio5, 3) if ratio5 is not None else None,
        "close_location_pct": round(close_loc * 100, 2),
        "previous_close": closes[-2],
        "current_day_open": rows[-1].get("open"),
        "current_day_low": rows[-1]["low"],
        "current_day_high": rows[-1]["high"],
        "raw_return_20d": ret20,
    }


def classify(row: dict, market_ret20: float):
    if row.get("data_status") != "verified":
        row.update({"structure_type": "unavailable", "action": "unavailable", "chase_risk": None})
        return row

    p, ma20, ma60 = row["current_price"], row["ma20"], row["ma60"]
    d20, d60 = row["distance_to_ma20_pct"] / 100, row["distance_to_ma60_pct"] / 100
    r10, r20 = row["return_10d_pct"] / 100, row.pop("raw_return_20d")
    s20, s60 = row["ma20_slope_5d_pct"] / 100, row["ma60_slope_5d_pct"] / 100
    atr = row["atr14_pct"] / 100
    rs20 = r20 - market_ret20
    row["relative_strength_20d_vs_market_pct"] = round(rs20 * 100, 2)

    chase = (
        "high"
        if d20 > 0.12 or r10 > 0.18 or (atr > 0.06 and r10 > 0.12)
        else ("medium" if d20 > 0.07 or r10 > 0.12 or d60 > 0.18 else "low")
    )
    above = p > ma20 > ma60
    slopes_up = s20 > 0 and s60 >= 0
    structure_up = row.get("higher_high") or row.get("higher_low")

    levels = [row["prior_60d_high"], row["prior_120d_high"]]
    touched = [lvl for lvl in levels if row["current_day_high"] >= lvl]
    breakout_level = max(touched) if touched else None
    price_confirmed = bool(breakout_level and p >= breakout_level * 0.995)
    volume_confirmed = bool(
        (row.get("volume_ratio_1d_vs_20d") or 0) >= 1.15
        or (row.get("volume_ratio_5d_vs_20d") or 0) >= 1.05
    )
    close_confirmed = (row.get("close_location_pct") or 0) >= 55
    breakout_confirmed = price_confirmed and volume_confirmed and close_confirmed
    near_breakout = p >= row["prior_60d_high"] * 0.995 or p >= row["prior_120d_high"] * 0.995
    row.update(
        {
            "breakout_level": round(breakout_level, 4) if breakout_level else None,
            "breakout_price_confirmed": price_confirmed,
            "breakout_volume_confirmed": volume_confirmed,
            "breakout_close_confirmed": close_confirmed,
            "breakout_confirmed": breakout_confirmed,
        }
    )

    if above and slopes_up and breakout_confirmed and chase == "high":
        stype, action = "overheated", "wait_pullback"
    elif above and slopes_up and breakout_confirmed:
        stype, action = "breakout", "participate" if chase == "low" else "watch_breakout"
    elif above and slopes_up and structure_up and rs20 >= RS_FLOOR:
        stype, action = (
            "trend_continuation",
            "participate"
            if chase == "low"
            else ("watch_trend" if chase == "medium" else "wait_pullback"),
        )
    elif ma20 > ma60 and s60 >= 0 and p > ma60 and abs(d20) <= 0.035 and row.get("higher_low") and rs20 >= RS_FLOOR:
        stype, action = "pullback", "participate" if chase != "high" else "wait_pullback"
    elif above and slopes_up and near_breakout and not breakout_confirmed:
        stype, action = "transition", "watch_breakout"
    elif p < ma60 and ma20 < ma60 and s20 < 0:
        stype, action = "damaged", "avoid"
    elif abs(ma20 / ma60 - 1) <= 0.03 and abs(d20) <= 0.05 and abs(r20) <= 0.10:
        stype, action = "base_not_started", "wait_breakout"
    else:
        stype, action = "transition", "observe"

    row.update({"chase_risk": chase, "structure_type": stype, "action": action})
    row["price_discovery"] = bool(
        breakout_confirmed
        and p >= row["prior_120d_high"] * 0.995
        and row.get("first_effective_resistance") is None
    )
    row["resistance_context"] = (
        "price_discovery_or_new_high; absence of overhead resistance is not a negative signal"
        if row["price_discovery"]
        else (
            "below_known_resistance"
            if row.get("first_effective_resistance")
            else "no_nearby_mapped_resistance"
        )
    )

    if not row.get("low_risk_eligible") and action not in {"avoid", "unavailable"}:
        row["technical_action"] = action
        row["action"] = "diagnostic_only_risk_warning"

    support = row.get("support_invalidation")
    row["downside_to_invalidation_pct"] = (
        round((p / support - 1) * 100, 2) if support and support < p else None
    )
    res = row.get("first_effective_resistance")
    row["upside_to_first_resistance_pct"] = (
        round((res["price"] / p - 1) * 100, 2)
        if isinstance(res, dict) and f(res.get("price")) and res["price"] > p
        else None
    )
    return row


def main():
    latest = load(LATEST, {})
    stocks = latest.get("stocks", {})
    reference_date = str(latest.get("trade_date") or "")

    base = {}
    market_returns = []
    for code, quote in stocks.items():
        code = str(code).zfill(6)
        row = base_metrics(
            code,
            (quote or {}).get("name") or code,
            rows_for(code),
            quote or {},
            reference_date,
        )
        base[code] = row
        if row.get("data_status") == "verified" and isinstance(row.get("raw_return_20d"), (int, float)):
            market_returns.append(row["raw_return_20d"])

    market_ret20 = median(market_returns) if market_returns else 0.0
    results = {code: classify(row, market_ret20) for code, row in base.items()}
    candidates = sorted(
        code
        for code, row in results.items()
        if row.get("low_risk_eligible")
        and row.get("structure_type") in {"trend_continuation", "breakout", "pullback"}
        and row.get("chase_risk") != "high"
    )
    unavailable = sorted(code for code, row in results.items() if row.get("data_status") != "verified")

    counts = {}
    risk_count = 0
    for row in results.values():
        counts[row.get("structure_type")] = counts.get(row.get("structure_type"), 0) + 1
        risk_count += int(bool(row.get("risk_warning")))

    payload = {
        "contract_id": "a-share-low-risk-price-structure",
        "generated_at": datetime.now(TZ).isoformat(),
        "reference_trade_date": reference_date,
        "universe_source": "all_mainboard_codes_from_data/latest.json",
        "universe_count": len(stocks),
        "verified_count": len(stocks) - len(unavailable),
        "unavailable_count": len(unavailable),
        "risk_warning_scanned_count": risk_count,
        "market_median_return_20d_pct": round(market_ret20 * 100, 2),
        "structure_type_counts": counts,
        "right_candidate_codes": candidates,
        "unavailable_codes": unavailable,
        "companies": results,
        "method_note": (
            "Full mainboard mechanical scan independent from fundamentals. "
            "Breakouts require price, volume and close confirmation; pullbacks "
            "require relative strength not materially below market."
        ),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "ok",
                "reference_trade_date": reference_date,
                "universe": len(stocks),
                "verified": payload["verified_count"],
                "right_candidates": len(candidates),
                "types": counts,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
