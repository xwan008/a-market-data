from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from statistics import median

import fetch_market as market

ROOT = Path(__file__).resolve().parents[1]
RESEARCH_DIR = ROOT / "research"
TREND_PATH = RESEARCH_DIR / "trend_handoff.json"
LOW_RISK_PATH = RESEARCH_DIR / "low_risk_handoff.json"
SNAPSHOT_PATH = RESEARCH_DIR / "intraday_market_snapshot.json"
MANIFEST_ROOT = ROOT / "data" / "low_risk" / "by_industry"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def round_or_none(value, digits: int = 4):
    if value is None:
        return None
    return round(float(value), digits)


def choose_quote(code: str, sina: dict[str, dict], tencent: dict[str, dict], trade_date: str | None) -> dict:
    s = sina.get(code) or {}
    t = tencent.get(code) or {}

    fresh_sources = []
    if market.source_is_fresh(s, trade_date):
        fresh_sources.append(("sina", s, t))
    if market.source_is_fresh(t, trade_date):
        fresh_sources.append(("tencent", t, s))

    if not fresh_sources:
        return {
            "name": s.get("name") or t.get("name"),
            "price": None,
            "prev_close": None,
            "change_pct": None,
            "quote_time": None,
            "primary_source": "none",
            "confidence": "invalid",
            "warnings": ["no_fresh_quote"],
        }

    source, base, other = fresh_sources[0]
    primary = market.positive_number(base.get("price"))
    secondary = market.positive_number(other.get("price")) if other else None
    validation = market.validate_price(
        primary_price=primary,
        secondary_price=secondary,
    )
    change_pct = market.calculate_change_pct(base.get("price"), base.get("prev_close"))
    warnings = list(validation.warnings)
    for name, item in (("sina", s), ("tencent", t)):
        if (
            item
            and market.positive_number(item.get("price")) is not None
            and not market.source_is_fresh(item, trade_date)
        ):
            warnings.append(f"{name}_date_unverified")
    warnings += market.validate_quote_fields(
        {
            "price": base.get("price"),
            "prev_close": base.get("prev_close"),
            "change_pct": change_pct,
        }
    )

    return {
        "name": base.get("name") or s.get("name") or t.get("name"),
        "price": round_or_none(base.get("price")),
        "prev_close": round_or_none(base.get("prev_close")),
        "change_pct": round_or_none(change_pct),
        "quote_time": market.parse_quote_time(base.get("date"), base.get("time")),
        "primary_source": source,
        "source_prices": {
            "sina": round_or_none(s.get("price")) if s else None,
            "tencent": round_or_none(t.get("price")) if t else None,
        },
        "confidence": validation.confidence,
        "warnings": sorted(set(warnings)),
    }


def metrics_for_codes(codes: list[str], quotes: dict[str, dict]) -> dict:
    usable = [
        quotes[code]
        for code in codes
        if code in quotes
        and quotes[code].get("confidence") in {"high", "medium"}
        and quotes[code].get("change_pct") is not None
    ]
    changes = [float(item["change_pct"]) for item in usable]
    up = sum(1 for x in changes if x > 0)
    down = sum(1 for x in changes if x < 0)
    flat = sum(1 for x in changes if x == 0)
    total = len(codes)
    quoted = len(usable)
    coverage = quoted / total if total else 0.0

    return {
        "company_count": total,
        "quoted_count": quoted,
        "coverage_ratio": round(coverage, 4),
        "up_count": up,
        "down_count": down,
        "flat_count": flat,
        "up_ratio": round(up / quoted, 4) if quoted else None,
        "median_change_pct": round(median(changes), 4) if changes else None,
        "max_change_pct": round(max(changes), 4) if changes else None,
        "min_change_pct": round(min(changes), 4) if changes else None,
        "data_quality": (
            "READY"
            if coverage >= 0.90
            else "DEGRADED"
            if coverage >= 0.80
            else "DATA_INSUFFICIENT"
        ),
    }


def main() -> int:
    now = datetime.now(market.TZ)
    trend = read_json(TREND_PATH)
    low_risk = read_json(LOW_RISK_PATH)
    source_trend_trade_date = trend.get("trade_date")
    source_low_risk_trade_date = low_risk.get("trade_date")
    source_handoff_trade_date_consistent = bool(
        source_trend_trade_date
        and source_low_risk_trade_date
        and source_trend_trade_date == source_low_risk_trade_date
    )

    industries: dict[str, dict] = {}
    trends: dict[str, dict] = {}
    target_codes: set[str] = set()
    manifest_errors: list[str] = []

    for signal in trend.get("signals") or []:
        trend_name = str(signal.get("trend_name") or "")
        grouped_codes: list[str] = []

        for industry_code, expected_name in zip(
            signal.get("industry_codes") or [],
            signal.get("industry_names") or [],
        ):
            manifest_path = MANIFEST_ROOT / industry_code / "manifest.json"
            try:
                manifest = read_json(manifest_path)
            except Exception as exc:
                manifest_errors.append(
                    f"{industry_code}:manifest_read_failed:{type(exc).__name__}:{exc}"
                )
                continue

            if manifest.get("industry_code") != industry_code:
                manifest_errors.append(f"{industry_code}:manifest_identity_mismatch")
                continue
            if (
                source_low_risk_trade_date
                and manifest.get("trade_date") != source_low_risk_trade_date
            ):
                manifest_errors.append(
                    f"{industry_code}:manifest_trade_date_mismatch:"
                    f"{manifest.get('trade_date')}!={source_low_risk_trade_date}"
                )
                continue

            company_codes = [str(code).zfill(6) for code in manifest.get("universe_company_codes") or []]
            target_codes.update(company_codes)
            grouped_codes.extend(company_codes)

            industries[industry_code] = {
                "industry_code": industry_code,
                "industry_name": manifest.get("industry_name") or expected_name,
                "manifest_trade_date": manifest.get("trade_date"),
                "trend_rank": signal.get("rank"),
                "trend_name": trend_name,
                "trend_state": signal.get("trend_state"),
                "market_state": signal.get("market_state"),
                "source_scope": "trend",
                "company_codes": company_codes,
            }

        trends[trend_name] = {
            "rank": signal.get("rank"),
            "trend_name": trend_name,
            "trend_state": signal.get("trend_state"),
            "market_state": signal.get("market_state"),
            "industry_codes": list(signal.get("industry_codes") or []),
            "company_codes": sorted(set(grouped_codes)),
        }

    low_risk_items = [
        item
        for item in (low_risk.get("items") or [])
        if item.get("status") in {"READY", "WAIT"}
    ]
    low_risk_only_attempted: set[str] = set()
    for item in low_risk_items:
        target_codes.add(str(item.get("code") or "").zfill(6))
        industry_code = str(item.get("industry_code") or "")
        if (
            not industry_code
            or industry_code in industries
            or industry_code in low_risk_only_attempted
        ):
            continue

        low_risk_only_attempted.add(industry_code)
        manifest_path = MANIFEST_ROOT / industry_code / "manifest.json"
        try:
            manifest = read_json(manifest_path)
        except Exception as exc:
            manifest_errors.append(
                f"{industry_code}:low_risk_only_manifest_read_failed:"
                f"{type(exc).__name__}:{exc}"
            )
            continue

        if manifest.get("industry_code") != industry_code:
            manifest_errors.append(
                f"{industry_code}:low_risk_only_manifest_identity_mismatch"
            )
            continue
        if (
            source_low_risk_trade_date
            and manifest.get("trade_date") != source_low_risk_trade_date
        ):
            manifest_errors.append(
                f"{industry_code}:low_risk_only_manifest_trade_date_mismatch:"
                f"{manifest.get('trade_date')}!={source_low_risk_trade_date}"
            )
            continue

        company_codes = [
            str(code).zfill(6)
            for code in manifest.get("universe_company_codes") or []
        ]
        target_codes.update(company_codes)
        industries[industry_code] = {
            "industry_code": industry_code,
            "industry_name": manifest.get("industry_name")
            or item.get("industry_name"),
            "manifest_trade_date": manifest.get("trade_date"),
            "trend_rank": None,
            "trend_name": item.get("trend_name"),
            "trend_state": None,
            "market_state": None,
            "source_scope": "low_risk_only",
            "company_codes": company_codes,
        }

    sina, sina_error = market.safe_fetch(market.fetch_sina_snapshot, "sina")
    tencent, tencent_error = market.safe_fetch(market.fetch_tencent_snapshot, "tencent")
    if not sina and not tencent:
        print(
            json.dumps(
                {"error": "all_sources_failed", "details": [sina_error, tencent_error]},
                ensure_ascii=False,
            )
        )
        return 2

    trade_date = market.infer_trade_date([sina, tencent], now)
    quotes = {
        code: choose_quote(code, sina, tencent, trade_date)
        for code in sorted(target_codes)
    }

    for industry_code, industry in industries.items():
        codes = industry["company_codes"]
        industry["metrics"] = metrics_for_codes(codes, quotes)
        industry["stocks"] = {code: quotes.get(code) for code in codes}

    for trend_name, trend_item in trends.items():
        trend_item["metrics"] = metrics_for_codes(trend_item["company_codes"], quotes)

    low_risk_stocks: dict[str, dict] = {}
    for item in low_risk_items:
        code = str(item.get("code") or "").zfill(6)
        quote = quotes.get(code) or {}
        industry = industries.get(str(item.get("industry_code") or "")) or {}
        industry_median = ((industry.get("metrics") or {}).get("median_change_pct"))
        stock_change = quote.get("change_pct")
        relative_to_industry = None
        if stock_change is not None and industry_median is not None:
            relative_to_industry = round(float(stock_change) - float(industry_median), 4)

        low_risk_stocks[code] = {
            "rank": item.get("rank"),
            "code": code,
            "company_name": item.get("company_name"),
            "trend_name": item.get("trend_name"),
            "industry_code": item.get("industry_code"),
            "industry_name": item.get("industry_name"),
            "formal_status": item.get("status"),
            "formal_current_price": item.get("current_price"),
            "reasonable_buy_range": item.get("reasonable_buy_range"),
            "low_risk_buy_range": item.get("low_risk_buy_range"),
            "wait_or_trigger_condition": item.get("wait_or_trigger_condition"),
            "invalidation_condition": item.get("invalidation_condition"),
            "reentry_trigger": item.get("reentry_trigger"),
            "price": quote.get("price"),
            "prev_close": quote.get("prev_close"),
            "change_pct": quote.get("change_pct"),
            "quote_time": quote.get("quote_time"),
            "confidence": quote.get("confidence"),
            "warnings": quote.get("warnings") or [],
            "industry_median_change_pct": industry_median,
            "relative_to_industry_pct": relative_to_industry,
            "in_monitored_industry_universe": code in set(industry.get("company_codes") or []),
            "trend_in_current_handoff": str(item.get("trend_name") or "") in trends,
        }

    usable_quotes = sum(
        1
        for quote in quotes.values()
        if quote.get("confidence") in {"high", "medium"}
        and quote.get("change_pct") is not None
    )
    total_quotes = len(quotes)
    quote_coverage = usable_quotes / total_quotes if total_quotes else 0.0

    payload = {
        "schema_version": 1,
        "result_kind": "a_share_intraday_market_snapshot",
        "trade_date": trade_date,
        "captured_at": now.isoformat(),
        "timezone": "Asia/Shanghai",
        "market_status": market.clock_market_status(now),
        "source_trend_trade_date": source_trend_trade_date,
        "source_low_risk_trade_date": source_low_risk_trade_date,
        "source_status": {
            "sina": "ok" if sina else "failed",
            "tencent": "ok" if tencent else "failed",
            "errors": [x for x in (sina_error, tencent_error) if x],
        },
        "validation": {
            "status": (
                "passed"
                if trade_date == now.date().isoformat()
                and source_handoff_trade_date_consistent
                and quote_coverage >= 0.90
                and not manifest_errors
                else "degraded"
            ),
            "source_handoff_dates_present": bool(
                source_trend_trade_date and source_low_risk_trade_date
            ),
            "source_handoff_trade_date_consistent": source_handoff_trade_date_consistent,
            "target_company_count": total_quotes,
            "usable_quote_count": usable_quotes,
            "quote_coverage": round(quote_coverage, 4),
            "manifest_errors": manifest_errors,
        },
        "trends": trends,
        "industries": industries,
        "low_risk_stocks": low_risk_stocks,
    }

    SNAPSHOT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "trade_date": trade_date,
                "captured_at": now.isoformat(),
                "target_company_count": total_quotes,
                "usable_quote_count": usable_quotes,
                "quote_coverage": round(quote_coverage, 4),
                "industry_count": len(industries),
                "low_risk_stock_count": len(low_risk_stocks),
                "validation_status": payload["validation"]["status"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
