from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SHARDS = DATA / "shards"
LATEST = DATA / "latest.json"
OUTPUT = DATA / "research" / "industry_state.json"
TZ = ZoneInfo("Asia/Shanghai")


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


def main() -> int:
    latest = json.loads(LATEST.read_text(encoding="utf-8"))
    existing = {}
    if OUTPUT.exists():
        existing = json.loads(OUTPUT.read_text(encoding="utf-8"))
    preferred_codes = set((existing.get("level3_profitability") or {}).keys())

    groups: dict[str, list[dict]] = defaultdict(list)
    names: dict[str, str] = {}
    for path in sorted(SHARDS.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for stock in (payload.get("stocks") or {}).values():
            code = stock.get("sw_level3_code")
            name = stock.get("sw_level3_name")
            if not code or stock.get("industry_mapping_status") != "mapped":
                continue
            if preferred_codes and code not in preferred_codes:
                continue
            fundamentals = stock.get("fundamentals") or {}
            revenue_yoy = fnum(fundamentals.get("revenue_yoy"))
            profit_yoy = fnum(fundamentals.get("net_profit_yoy"))
            if revenue_yoy is None and profit_yoy is None:
                continue
            groups[code].append({
                "revenue_yoy": revenue_yoy,
                "profit_yoy": profit_yoy,
            })
            if name:
                names[code] = str(name)

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
            "method": "median company YoY growth plus positive-profit-growth breadth",
        }

    if preferred_codes:
        missing = preferred_codes - set(result)
        for code in sorted(missing):
            old = (existing.get("level3_profitability") or {}).get(code)
            if old:
                carry = dict(old)
                carry["confidence"] = "low"
                carry["warnings"] = sorted(set((carry.get("warnings") or []) + ["weekly_refresh_insufficient_company_data"]))
                result[code] = carry

    payload = {
        "schema_version": 2,
        "status": "valid" if result else "invalid",
        "generated_at": now,
        "baseline_trade_date": latest.get("trade_date"),
        "method": "weekly deterministic aggregation from repository company financials",
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
    }, ensure_ascii=False))
    return 0 if result else 2


if __name__ == "__main__":
    raise SystemExit(main())
