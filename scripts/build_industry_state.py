from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SHARDS = DATA / "shards"
HISTORY_SHARDS = DATA / "history_shards"
LATEST = DATA / "latest.json"
OUTPUT = DATA / "research" / "industry_state.json"
TZ = ZoneInfo("Asia/Shanghai")
TENCENT_VOLUME_LOT_SIZE = 100


def fnum(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def classify_breadth(value: float) -> str:
    if value >= 0.60:
        return "broad"
    if value <= 0.40:
        return "narrow"
    return "divergent"


def classify_market_breadth(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value >= 0.55:
        return "broad"
    if value <= 0.35:
        return "narrow"
    return "divergent"


def classify_market_activity(volume_ratio: float | None, expanding_share: float | None) -> str:
    if volume_ratio is None or expanding_share is None:
        return "unknown"
    if volume_ratio >= 1.05 and expanding_share >= 0.50:
        return "active"
    if volume_ratio <= 0.80 and expanding_share <= 0.35:
        return "quiet"
    return "normal"


def classify_market_confirmation(market_breadth: str, market_activity: str) -> str:
    if market_breadth == "unknown" or market_activity == "unknown":
        return "unknown"
    if market_breadth == "broad" and market_activity == "active":
        return "strong"
    if market_breadth == "narrow":
        return "weak"
    return "neutral"


def classify_trend(revenue_yoy: float | None, profit_yoy: float | None, improving_breadth: float) -> str:
    if profit_yoy is not None and profit_yoy >= 10 and improving_breadth >= 0.55 and (revenue_yoy is None or revenue_yoy >= 0):
        return "improving"
    if (profit_yoy is not None and profit_yoy <= -10) or improving_breadth < 0.35:
        return "deteriorating"
    return "stable"


def classify_strength(revenue_yoy: float | None, profit_yoy: float | None) -> str:
    if profit_yoy is not None and profit_yoy >= 20 and (revenue_yoy is None or revenue_yoy >= 5):
        return "strong"
    if (profit_yoy is not None and profit_yoy < 0) or (revenue_yoy is not None and revenue_yoy < 0):
        return "weak"
    return "normal"


def classify_confidence(n: int) -> str:
    if n >= 8:
        return "high"
    if n >= 4:
        return "medium"
    return "low"


def normalized_volume(row: dict) -> float | None:
    volume = fnum(row.get("volume"))
    if volume is None:
        return None
    if row.get("volume_unit") == "shares":
        return volume
    if row.get("basis") == "qfq" and row.get("source") == "tencent":
        return volume * TENCENT_VOLUME_LOT_SIZE
    return volume


def load_volume_ratios(codes: set[str], latest: dict, trade_date: str | None) -> dict[str, float]:
    if not codes or not trade_date:
        return {}

    latest_stocks = latest.get("stocks") or {}
    by_prefix: dict[str, list[str]] = defaultdict(list)
    for code in codes:
        by_prefix[str(code)[:4]].append(str(code))

    ratios: dict[str, float] = {}
    for prefix, prefix_codes in by_prefix.items():
        path = HISTORY_SHARDS / f"{prefix}.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        history_stocks = payload.get("stocks") or {}

        for code in prefix_codes:
            current_volume = fnum((latest_stocks.get(code) or {}).get("volume"))
            if current_volume is None or current_volume <= 0:
                continue

            history = (history_stocks.get(code) or {}).get("history") or []
            prior_volumes: list[float] = []
            for row in history:
                row_date = str(row.get("date") or "")
                if not row_date or row_date >= trade_date:
                    continue
                volume = normalized_volume(row)
                if volume is not None and volume > 0:
                    prior_volumes.append(volume)

            prior_volumes = prior_volumes[-20:]
            if len(prior_volumes) < 10:
                continue
            avg_volume = mean(prior_volumes)
            if avg_volume > 0:
                ratios[code] = current_volume / avg_volume

    return ratios


def weighted_market_breadth(
    day_up_ratio: float | None,
    strong_up_ratio: float | None,
    five_day_up_ratio: float | None,
) -> float | None:
    components = []
    if day_up_ratio is not None:
        components.append((day_up_ratio, 0.50))
    if strong_up_ratio is not None:
        components.append((strong_up_ratio, 0.20))
    if five_day_up_ratio is not None:
        components.append((five_day_up_ratio, 0.30))
    if not components:
        return None
    total_weight = sum(weight for _, weight in components)
    return sum(value * weight for value, weight in components) / total_weight


def main() -> int:
    latest = json.loads(LATEST.read_text(encoding="utf-8"))
    existing = {}
    if OUTPUT.exists():
        existing = json.loads(OUTPUT.read_text(encoding="utf-8"))

    groups: dict[str, list[dict]] = defaultdict(list)
    names: dict[str, str] = {}
    market_codes: set[str] = set()

    for path in sorted(SHARDS.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for stock_code, stock in (payload.get("stocks") or {}).items():
            code = stock.get("sw_level3_code")
            name = stock.get("sw_level3_name")
            if not code or stock.get("industry_mapping_status") != "mapped":
                continue

            fundamentals = stock.get("fundamentals") or {}
            revenue_yoy = fnum(fundamentals.get("revenue_yoy"))
            profit_yoy = fnum(fundamentals.get("net_profit_yoy"))
            price = fnum(stock.get("price"))
            prev_close = fnum(stock.get("prev_close"))
            day_change = None
            if price is not None and prev_close is not None and prev_close > 0:
                day_change = (price / prev_close - 1) * 100
            change_5d = fnum((stock.get("trend") or {}).get("close_change_5d_pct"))

            if revenue_yoy is None and profit_yoy is None:
                continue

            stock_code = str(stock_code).zfill(6)
            groups[code].append({
                "stock_code": stock_code,
                "revenue_yoy": revenue_yoy,
                "profit_yoy": profit_yoy,
                "day_change": day_change,
                "change_5d": change_5d,
            })
            market_codes.add(stock_code)
            if name:
                names[code] = str(name)

    trade_date = latest.get("trade_date")
    volume_ratios = load_volume_ratios(market_codes, latest, str(trade_date) if trade_date else None)

    now = datetime.now(TZ).isoformat()
    result: dict[str, dict] = {}
    for code, rows in sorted(groups.items()):
        revenue_values = [x["revenue_yoy"] for x in rows if x["revenue_yoy"] is not None]
        profit_values = [x["profit_yoy"] for x in rows if x["profit_yoy"] is not None]
        if not profit_values:
            continue

        median_revenue = median(revenue_values) if revenue_values else None
        median_profit = median(profit_values)
        improving_breadth = sum(1 for x in profit_values if x > 0) / len(profit_values)
        sample_count = max(len(revenue_values), len(profit_values))

        day_changes = [x["day_change"] for x in rows if x["day_change"] is not None]
        five_day_changes = [x["change_5d"] for x in rows if x["change_5d"] is not None]
        day_up_ratio = (
            sum(1 for value in day_changes if value > 0) / len(day_changes)
            if day_changes else None
        )
        strong_up_ratio = (
            sum(1 for value in day_changes if value >= 1.0) / len(day_changes)
            if day_changes else None
        )
        five_day_up_ratio = (
            sum(1 for value in five_day_changes if value > 0) / len(five_day_changes)
            if five_day_changes else None
        )
        market_breadth_ratio = weighted_market_breadth(
            day_up_ratio,
            strong_up_ratio,
            five_day_up_ratio,
        )
        market_breadth = classify_market_breadth(market_breadth_ratio)

        industry_volume_ratios = [
            volume_ratios[x["stock_code"]]
            for x in rows
            if x["stock_code"] in volume_ratios
        ]
        median_volume_ratio = median(industry_volume_ratios) if industry_volume_ratios else None
        expanding_volume_share = (
            sum(1 for value in industry_volume_ratios if value >= 1.0) / len(industry_volume_ratios)
            if industry_volume_ratios else None
        )
        market_activity = classify_market_activity(median_volume_ratio, expanding_volume_share)
        market_confirmation = classify_market_confirmation(market_breadth, market_activity)

        result[code] = {
            "name": names.get(code) or ((existing.get("level3_profitability") or {}).get(code) or {}).get("name"),
            "trend": classify_trend(median_revenue, median_profit, improving_breadth),
            "strength": classify_strength(median_revenue, median_profit),
            "breadth": classify_breadth(improving_breadth),
            "confidence": classify_confidence(sample_count),
            "last_verified_at": now,
            "sample_count": sample_count,
            "core_improving_breadth": improving_breadth,
            "aggregate_revenue_yoy": median_revenue / 100 if median_revenue is not None else None,
            "aggregate_parent_profit_yoy": median_profit / 100 if median_profit is not None else None,
            "market_breadth": market_breadth,
            "market_activity": market_activity,
            "market_confirmation": market_confirmation,
            "market_metrics": {
                "day_up_ratio": day_up_ratio,
                "strong_up_ratio": strong_up_ratio,
                "five_day_up_ratio": five_day_up_ratio,
                "breadth_score": market_breadth_ratio,
                "median_volume_ratio_vs_20d": median_volume_ratio,
                "expanding_volume_share": expanding_volume_share,
                "breadth_sample_count": len(day_changes),
                "activity_sample_count": len(industry_volume_ratios),
            },
            "method": "median company YoY growth plus financial breadth, confirmed by market breadth and relative volume activity",
        }

    previous_industries = existing.get("level3_profitability") or {}
    missing = set(previous_industries) - set(result)
    for code in sorted(missing):
        old = previous_industries.get(code)
        if old:
            carry = dict(old)
            carry["confidence"] = "low"
            carry["warnings"] = sorted(set((carry.get("warnings") or []) + ["industry_refresh_insufficient_company_data"]))
            result[code] = carry

    payload = {
        "schema_version": 2,
        "status": "valid" if result else "invalid",
        "generated_at": now,
        "baseline_trade_date": latest.get("trade_date"),
        "method": "deterministic aggregation from repository company financials plus daily market breadth and relative volume activity",
        "industry_count": len(result),
        "level3_profitability": result,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "trade_date": payload["baseline_trade_date"],
        "industries": len(result),
        "improving": sum(1 for x in result.values() if x.get("trend") == "improving"),
        "stable": sum(1 for x in result.values() if x.get("trend") == "stable"),
        "deteriorating": sum(1 for x in result.values() if x.get("trend") == "deteriorating"),
        "market_confirmation_strong": sum(1 for x in result.values() if x.get("market_confirmation") == "strong"),
        "market_confirmation_weak": sum(1 for x in result.values() if x.get("market_confirmation") == "weak"),
    }, ensure_ascii=False))
    return 0 if result else 2


if __name__ == "__main__":
    raise SystemExit(main())
