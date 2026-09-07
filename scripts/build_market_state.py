from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
LATEST = DATA / "latest.json"
TREND = DATA / "trend_summary.json"
HISTORY = DATA / "history_shards"
OUTPUT = DATA / "market_state.json"
TZ = ZoneInfo("Asia/Shanghai")


def fnum(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def ratio(n: int, d: int) -> float | None:
    return n / d if d else None


def market_turnover_series() -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for path in sorted(HISTORY.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in (payload.get("stocks") or {}).values():
            for row in (item.get("history") or [])[-25:]:
                d = str(row.get("date") or "")
                close = fnum(row.get("close"))
                volume = fnum(row.get("volume"))
                if d and close is not None and close > 0 and volume is not None and volume > 0:
                    totals[d] += close * volume
    return dict(totals)


def classify_trend(above_ma20: float | None, median_20d: float | None) -> str:
    if above_ma20 is None or median_20d is None:
        return "unknown"
    if above_ma20 >= 0.58 and median_20d > 0:
        return "bullish"
    if above_ma20 <= 0.42 and median_20d < 0:
        return "bearish"
    return "transition"


def classify_breadth(advance_ratio: float | None) -> str:
    if advance_ratio is None:
        return "unknown"
    if advance_ratio >= 0.58:
        return "strong"
    if advance_ratio <= 0.42:
        return "weak"
    return "neutral"


def classify_liquidity(turnover_ratio: float | None) -> str:
    if turnover_ratio is None:
        return "unknown"
    if turnover_ratio >= 1.15:
        return "high"
    if turnover_ratio <= 0.85:
        return "low"
    return "normal"


def classify_risk(
    trend: str,
    breadth: str,
    liquidity: str,
    median_20d: float | None,
    above_ma60: float | None,
) -> str:
    if trend == "bearish" and breadth == "weak":
        return "high"
    if median_20d is not None and median_20d <= -5 and above_ma60 is not None and above_ma60 < 0.40:
        return "high"
    if trend == "bullish" and breadth != "weak" and liquidity != "low":
        return "low"
    return "medium"


def main() -> int:
    latest = json.loads(LATEST.read_text(encoding="utf-8"))
    trend_payload = json.loads(TREND.read_text(encoding="utf-8"))
    quotes = latest.get("stocks") or {}
    trends = trend_payload.get("stocks") or {}

    advances = declines = flat = usable_changes = 0
    changes = []
    for quote in quotes.values():
        change = fnum(quote.get("change_pct"))
        if change is None:
            continue
        usable_changes += 1
        changes.append(change)
        if change > 0.01:
            advances += 1
        elif change < -0.01:
            declines += 1
        else:
            flat += 1

    ma20_total = ma60_total = above20 = above60 = 0
    returns_5d = []
    returns_20d = []
    for item in trends.values():
        current = fnum(item.get("last_close"))
        structure = item.get("structure_60d") or {}
        ma20 = fnum(structure.get("ma20"))
        ma60 = fnum(structure.get("ma60"))
        if current is not None and ma20 is not None:
            ma20_total += 1
            above20 += int(current >= ma20)
        if current is not None and ma60 is not None:
            ma60_total += 1
            above60 += int(current >= ma60)
        value5 = fnum(item.get("close_change_5d_pct"))
        value20 = fnum(item.get("close_change_20d_pct"))
        if value5 is not None:
            returns_5d.append(value5)
        if value20 is not None:
            returns_20d.append(value20)

    turnover = market_turnover_series()
    trade_date = str(latest.get("trade_date") or "")
    current_turnover = turnover.get(trade_date)
    prior_dates = sorted(d for d in turnover if d < trade_date)[-20:]
    prior_values = [turnover[d] for d in prior_dates if turnover[d] > 0]
    turnover_median20 = median(prior_values) if prior_values else None
    turnover_ratio20 = (
        current_turnover / turnover_median20
        if current_turnover is not None and turnover_median20 not in (None, 0)
        else None
    )

    advance_ratio = ratio(advances, usable_changes)
    above_ma20_ratio = ratio(above20, ma20_total)
    above_ma60_ratio = ratio(above60, ma60_total)
    median_5d = median(returns_5d) if returns_5d else None
    median_20d = median(returns_20d) if returns_20d else None

    trend_state = classify_trend(above_ma20_ratio, median_20d)
    breadth_state = classify_breadth(advance_ratio)
    liquidity_state = classify_liquidity(turnover_ratio20)
    risk_level = classify_risk(trend_state, breadth_state, liquidity_state, median_20d, above_ma60_ratio)

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(TZ).isoformat(),
        "trade_date": latest.get("trade_date"),
        "universe": "A-share main-board stocks tracked by this repository",
        "trend": trend_state,
        "breadth": breadth_state,
        "liquidity": liquidity_state,
        "risk_level": risk_level,
        "metrics": {
            "advancers": advances,
            "decliners": declines,
            "flat": flat,
            "advance_ratio": advance_ratio,
            "above_ma20_ratio": above_ma20_ratio,
            "above_ma60_ratio": above_ma60_ratio,
            "median_5d_change_pct": median_5d,
            "median_20d_change_pct": median_20d,
            "turnover_proxy": current_turnover,
            "turnover_proxy_median20": turnover_median20,
            "turnover_ratio_vs_20d": turnover_ratio20,
        },
        "method": {
            "trend": "cross-sectional MA20 participation plus median 20d stock return",
            "breadth": "daily advancers / stocks with usable daily change",
            "liquidity": "sum(close*volume) across tracked stocks versus prior-20-session median",
            "risk": "deterministic combination of trend, breadth and liquidity; context only, not a hard buy/sell gate",
        },
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "trade_date": payload["trade_date"],
        "trend": trend_state,
        "breadth": breadth_state,
        "liquidity": liquidity_state,
        "risk_level": risk_level,
        "advance_ratio": advance_ratio,
        "above_ma20_ratio": above_ma20_ratio,
        "turnover_ratio_vs_20d": turnover_ratio20,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
