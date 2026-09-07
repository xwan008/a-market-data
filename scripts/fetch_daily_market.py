from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import fetch_market as base
from fetch_market_resilient import install_resilient_adapters

ROOT = Path(__file__).resolve().parents[1]
LATEST_PATH = ROOT / "data" / "latest.json"


def read_previous() -> dict:
    if not LATEST_PATH.exists():
        return {}
    return json.loads(LATEST_PATH.read_text(encoding="utf-8"))


def build_daily_fundamentals(
    codes: list[str],
    previous_stocks: dict[str, dict],
    trade_date: str | None,
) -> tuple[dict[str, dict], dict]:
    valuation, valuation_error = base.safe_fetch(
        lambda: base.fetch_eastmoney_valuation_snapshot(codes, trade_date),
        "eastmoney_valuation",
    )

    out: dict[str, dict] = {}
    fresh_count = stale_count = financial_count = 0

    for code in codes:
        previous = ((previous_stocks.get(code) or {}).get("fundamentals") or {})
        item = dict(previous)
        warnings = [
            warning
            for warning in (item.get("warnings") or [])
            if warning not in {"valuation_unavailable", "valuation_stale_fallback"}
        ]
        sources = dict(item.get("sources") or {})
        fresh = valuation.get(code) or {}

        if fresh:
            fresh_count += 1
            for key in ("valuation_date", "pe_dynamic", "pe_ttm", "pb", "market_cap"):
                if key in fresh:
                    item[key] = fresh.get(key)
            sources["valuation"] = "eastmoney_market_cross_section"
        elif any(item.get(key) is not None for key in ("pe_dynamic", "pe_ttm", "pb", "market_cap")):
            stale_count += 1
            warnings.append("valuation_stale_fallback")
        else:
            warnings.append("valuation_unavailable")

        if item.get("report_date"):
            financial_count += 1
        sources.setdefault("financial", "weekly_verified_snapshot" if item.get("report_date") else None)
        item["sources"] = sources
        item["warnings"] = sorted(set(warnings))
        out[code] = item

    valuation_usable = sum(
        1
        for item in out.values()
        if any(item.get(key) is not None for key in ("pe_dynamic", "pe_ttm", "pb", "market_cap"))
    )
    stats = {
        "valuation_usable": valuation_usable,
        "valuation_fresh_usable": fresh_count,
        "valuation_stale_fallback": stale_count,
        "financial_usable": financial_count,
        "financial_refresh_mode": "carried_forward_from_weekly_refresh",
        "pe_dynamic_usable": sum(1 for x in out.values() if x.get("pe_dynamic") is not None),
        "pe_ttm_usable": sum(1 for x in out.values() if x.get("pe_ttm") is not None),
        "pb_usable": sum(1 for x in out.values() if x.get("pb") is not None),
        "roe_usable": sum(1 for x in out.values() if x.get("roe") is not None),
        "deduct_profit_growth_usable": sum(
            1
            for x in out.values()
            if x.get("deduct_net_profit_yoy") is not None
            or x.get("deduct_basic_eps_yoy") is not None
        ),
        "errors": [valuation_error] if valuation_error else [],
    }
    return out, stats


def main() -> int:
    install_resilient_adapters()
    previous_payload = read_previous()
    previous_stocks = previous_payload.get("stocks") or {}
    now = datetime.now(base.TZ)

    sina, sina_error = base.safe_fetch(base.fetch_sina_snapshot, "sina")
    tencent, tencent_error = base.safe_fetch(base.fetch_tencent_snapshot, "tencent")
    if not sina and not tencent:
        print(json.dumps({"error": "all_sources_failed", "details": [sina_error, tencent_error]}, ensure_ascii=False))
        return 2

    trade_date = base.infer_trade_date([sina, tencent], now)
    status = base.clock_market_status(now)
    if trade_date is None:
        status = "date_unverified"
    elif trade_date != now.date().isoformat():
        status = "closed_or_no_trade"

    codes = sorted(set(sina) | set(tencent))
    fundamentals, fundamental_stats = build_daily_fundamentals(codes, previous_stocks, trade_date)

    stocks: dict[str, dict] = {}
    stats = {"high": 0, "medium": 0, "invalid": 0}

    for code in codes:
        s, t = sina.get(code, {}), tencent.get(code, {})
        fresh = [("sina", s), ("tencent", t)]
        fresh = [(name, item) for name, item in fresh if base.source_is_fresh(item, trade_date)]

        if fresh:
            source, quote = fresh[0]
            primary = base.positive_number(quote.get("price"))
            other = t if source == "sina" else s
            secondary = base.positive_number(other.get("price")) if other else None
        else:
            source, quote, primary, secondary = "none", s or t, None, None

        change_pct = base.calculate_change_pct(quote.get("price"), quote.get("prev_close"))
        validation = base.validate_price(primary_price=primary, secondary_price=secondary)
        warnings = list(validation.warnings)
        for name, item in (("sina", s), ("tencent", t)):
            if item and base.positive_number(item.get("price")) is not None and not base.source_is_fresh(item, trade_date):
                warnings.append(f"{name}_date_unverified")
        warnings += base.validate_quote_fields(
            {"price": quote.get("price"), "prev_close": quote.get("prev_close"), "change_pct": change_pct}
        )
        quote_time = (
            base.parse_quote_time(quote.get("date"), quote.get("time"))
            if source in {"sina", "tencent"}
            else None
        )

        stocks[code] = {
            "name": quote.get("name") or s.get("name") or t.get("name"),
            "market": "SH" if code.startswith(base.SH_MAIN_PREFIXES) else "SZ",
            "price": quote.get("price"),
            "prev_close": quote.get("prev_close"),
            "open": quote.get("open"),
            "high": quote.get("high"),
            "low": quote.get("low"),
            "volume": quote.get("volume"),
            "change_pct": change_pct,
            "price_time": quote_time,
            "primary_source": source,
            "source_prices": {"sina": s.get("price") if s else None, "tencent": t.get("price") if t else None},
            "source_dates": {
                "sina": base.normalize_quote_date(s.get("date")) if s else None,
                "tencent": base.normalize_quote_date(t.get("date")) if t else None,
            },
            "confidence": validation.confidence,
            "warnings": sorted(set(warnings)),
            "fundamentals": fundamentals.get(code),
        }
        stats[validation.confidence] += 1

    payload = {
        "schema_version": 3,
        "generated_at": now.isoformat(),
        "trade_date": trade_date,
        "timezone": "Asia/Shanghai",
        "market_status": status,
        "refresh_mode": "daily_quotes_and_valuation",
        "source_status": {
            "sina": "ok" if sina else "failed",
            "tencent": "ok" if tencent else "failed",
            "errors": [x for x in (sina_error, tencent_error) if x],
        },
        "validation_stats": stats,
        "fundamental_stats": fundamental_stats,
        "stocks": stocks,
    }
    LATEST_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "trade_date": trade_date,
        "market_status": status,
        "stocks": len(stocks),
        "stats": stats,
        "fundamental_stats": fundamental_stats,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
