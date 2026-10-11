from __future__ import annotations

import json
import math
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from validate import normalize_quote_date, parse_quote_time, validate_price, validate_quote_fields

TZ = ZoneInfo("Asia/Shanghai")
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
LATEST_PATH = DATA_DIR / "latest.json"

SH_MAIN_PREFIXES = ("600", "601", "603", "605")
SZ_MAIN_PREFIXES = ("000", "001", "002", "003")

EASTMONEY_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://quote.eastmoney.com/",
}
EASTMONEY_UT = "bd1d9ddb04089700cf9c27f6f7426281"
EASTMONEY_LIST_URLS = (
    "https://push2delay.eastmoney.com/api/qt/clist/get",
    "https://push2.eastmoney.com/api/qt/clist/get",
)
EASTMONEY_FINANCE_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"


def is_main_board(code: str) -> bool:
    code = str(code).zfill(6)
    return code.startswith((*SH_MAIN_PREFIXES, *SZ_MAIN_PREFIXES))


def is_main_board_symbol(raw: str) -> bool:
    raw = str(raw).lower().strip()
    if raw.startswith("sh"):
        return raw[2:].zfill(6).startswith(SH_MAIN_PREFIXES)
    if raw.startswith("sz"):
        return raw[2:].zfill(6).startswith(SZ_MAIN_PREFIXES)
    return is_main_board(raw)


def normalize_code(raw: str) -> str:
    raw = str(raw).lower().strip()
    if raw.startswith(("sh", "sz", "bj")):
        raw = raw[2:]
    return raw.zfill(6)


def positive_number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def metric_number(value) -> float | None:
    if value in (None, "", "-", "--"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def first_metric(item: dict, *keys: str) -> float | None:
    for key in keys:
        value = metric_number(item.get(key))
        if value is not None:
            return value
    return None


def calculate_change_pct(price, prev_close) -> float | None:
    current = positive_number(price)
    previous = positive_number(prev_close)
    if current is None or previous is None:
        return None
    return (current / previous - 1) * 100


def fetch_easyquotation_snapshot(provider: str) -> dict[str, dict]:
    import easyquotation

    q = easyquotation.use(provider)
    raw = q.market_snapshot(prefix=True)
    out: dict[str, dict] = {}
    for symbol, item in raw.items():
        if not is_main_board_symbol(symbol):
            continue
        code = normalize_code(symbol)
        out[code] = {
            "name": item.get("name"),
            "price": item.get("now"),
            "prev_close": item.get("close"),
            "open": item.get("open"),
            "high": item.get("high"),
            "low": item.get("low"),
            "volume": item.get("turnover"),
            "date": item.get("date"),
            "time": item.get("time"),
        }
    return out


def fetch_sina_snapshot() -> dict[str, dict]:
    return fetch_easyquotation_snapshot("sina")


def fetch_tencent_snapshot() -> dict[str, dict]:
    return fetch_easyquotation_snapshot("tencent")


def safe_fetch(fn, label: str) -> tuple[dict[str, dict], str | None]:
    try:
        return fn(), None
    except Exception as exc:
        return {}, f"{label}:{type(exc).__name__}:{exc}"


def fetch_eastmoney_list_page(market_filter: str, page: int) -> dict:
    last_error: Exception | None = None
    for url in EASTMONEY_LIST_URLS:
        try:
            response = requests.get(
                url,
                params={
                    "pn": page,
                    "pz": 100,
                    "po": 1,
                    "np": 1,
                    "ut": EASTMONEY_UT,
                    "fltt": 2,
                    "invt": 2,
                    "fid": "f12",
                    "fs": market_filter,
                    "fields": "f12,f14,f9,f23,f20",
                },
                headers=EASTMONEY_HEADERS,
                timeout=15,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("data") is not None:
                return payload
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    raise RuntimeError("eastmoney list returned no data")


def fetch_eastmoney_pe_ttm(codes: set[str], trade_date: str | None) -> dict[str, dict]:
    if not trade_date:
        return {}
    out: dict[str, dict] = {}
    page = 1
    pages = 1
    while page <= pages:
        response = requests.get(
            EASTMONEY_FINANCE_URL,
            params={
                "sortColumns": "SECURITY_CODE",
                "sortTypes": "1",
                "pageSize": 500,
                "pageNumber": page,
                "reportName": "RPT_VALUEANALYSIS_DET",
                "columns": "SECURITY_CODE,TRADE_DATE,PE_TTM,PB_MRQ,TOTAL_MARKET_CAP",
                "filter": f"(TRADE_DATE='{trade_date}')",
                "source": "WEB",
                "client": "WEB",
            },
            headers=EASTMONEY_HEADERS,
            timeout=20,
        )
        response.raise_for_status()
        result = (response.json().get("result") or {})
        pages = int(result.get("pages") or 0)
        rows = result.get("data") or []
        if not rows:
            break
        for item in rows:
            code = normalize_code(item.get("SECURITY_CODE") or "")
            if code not in codes:
                continue
            row_date = item.get("TRADE_DATE")
            out[code] = {
                "valuation_date": str(row_date)[:10] if row_date else trade_date,
                "pe_ttm": metric_number(item.get("PE_TTM")),
                "pb": metric_number(item.get("PB_MRQ")),
                "market_cap": metric_number(item.get("TOTAL_MARKET_CAP")),
            }
        page += 1
    return out


def fetch_eastmoney_valuation_snapshot(codes: list[str], trade_date: str | None) -> dict[str, dict]:
    """Fetch main-board valuation cross-section without per-stock requests."""
    wanted = set(codes)
    out: dict[str, dict] = {}

    for market_filter in ("m:0+t:6", "m:1+t:2"):
        page = 1
        total = 1
        while (page - 1) * 100 < total:
            payload = fetch_eastmoney_list_page(market_filter, page)
            data = payload.get("data") or {}
            total = int(data.get("total") or 0)
            rows = data.get("diff") or []
            if not rows:
                break
            for item in rows:
                code = normalize_code(item.get("f12") or "")
                if code not in wanted:
                    continue
                out[code] = {
                    "valuation_date": trade_date,
                    "pe_dynamic": metric_number(item.get("f9")),
                    "pe_ttm": None,
                    "pb": metric_number(item.get("f23")),
                    "market_cap": metric_number(item.get("f20")),
                }
            page += 1

    try:
        ttm = fetch_eastmoney_pe_ttm(wanted, trade_date)
    except Exception:
        ttm = {}
    for code, item in ttm.items():
        base = out.setdefault(code, {})
        base["valuation_date"] = item.get("valuation_date") or base.get("valuation_date")
        base["pe_ttm"] = item.get("pe_ttm")
        if base.get("pb") is None:
            base["pb"] = item.get("pb")
        if base.get("market_cap") is None:
            base["market_cap"] = item.get("market_cap")
    return out


def completed_quarter_ends(as_of: date, count: int = 2) -> list[str]:
    candidates: list[date] = []
    for year in range(as_of.year - 2, as_of.year + 1):
        for month, day in ((3, 31), (6, 30), (9, 30), (12, 31)):
            qend = date(year, month, day)
            if qend <= as_of:
                candidates.append(qend)
    return [d.isoformat() for d in sorted(candidates, reverse=True)[:count]]


def year_ago(report_date: str) -> str:
    d = date.fromisoformat(report_date)
    return date(d.year - 1, d.month, d.day).isoformat()


def parse_financial_row(item: dict) -> dict:
    report_date = item.get("REPORTDATE") or item.get("REPORT_DATE") or item.get("QDATE")
    if report_date:
        report_date = str(report_date)[:10]
    notice_date = item.get("NOTICE_DATE") or item.get("UPDATE_DATE")
    if notice_date:
        notice_date = str(notice_date)[:10]
    return {
        "report_date": report_date,
        "notice_date": notice_date,
        "roe": first_metric(item, "WEIGHTAVG_ROE", "ROEJQ"),
        "revenue_yoy": first_metric(item, "YSTZ", "TOTALOPERATEREVETZ"),
        "net_profit_yoy": first_metric(item, "SJLTZ", "PARENTNETPROFITTZ"),
        "deduct_net_profit_yoy": first_metric(
            item,
            "KCFJCXSYJLRTZ",
            "DEDUCT_NETPROFIT_YOY",
        ),
        "operating_cashflow_per_share": first_metric(item, "MGJYXJJE"),
        "gross_margin": first_metric(item, "XSMLL"),
        "revenue": first_metric(item, "TOTAL_OPERATE_INCOME"),
        "net_profit": first_metric(item, "PARENT_NETPROFIT"),
        "basic_eps": first_metric(item, "BASIC_EPS"),
        "deduct_basic_eps": first_metric(item, "DEDUCT_BASIC_EPS"),
    }


def fetch_financial_period(report_date: str, wanted: set[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    page = 1
    pages = 1
    while page <= pages:
        response = requests.get(
            EASTMONEY_FINANCE_URL,
            params={
                "sortColumns": "REPORTDATE,SECURITY_CODE",
                "sortTypes": "-1,1",
                "pageSize": 500,
                "pageNumber": page,
                "reportName": "RPT_LICO_FN_CPD",
                "columns": "ALL",
                "filter": f"(REPORTDATE='{report_date}')",
                "source": "WEB",
                "client": "WEB",
            },
            headers=EASTMONEY_HEADERS,
            timeout=20,
        )
        response.raise_for_status()
        result = (response.json().get("result") or {})
        pages = int(result.get("pages") or 0)
        rows = result.get("data") or []
        if not rows:
            break
        for item in rows:
            code = normalize_code(item.get("SECURITY_CODE") or item.get("CODE") or "")
            if code in wanted:
                out[code] = parse_financial_row(item)
        page += 1
    return out


def fetch_eastmoney_financial_snapshot(codes: list[str], as_of: date) -> dict[str, dict]:
    """Fetch latest available quarter plus same-period prior-year core-EPS comparison."""
    wanted = set(codes)
    current_periods = completed_quarter_ends(as_of, count=2)
    all_periods = [*current_periods, *(year_ago(x) for x in current_periods)]
    period_data = {period: fetch_financial_period(period, wanted) for period in all_periods}

    out: dict[str, dict] = {}
    for code in codes:
        for period in current_periods:
            current = period_data.get(period, {}).get(code)
            if not current:
                continue
            item = dict(current)
            previous = period_data.get(year_ago(period), {}).get(code) or {}
            previous_deduct_eps = previous.get("deduct_basic_eps")
            item["deduct_basic_eps_prev_year"] = previous_deduct_eps
            current_deduct_eps = item.get("deduct_basic_eps")
            if (
                item.get("deduct_net_profit_yoy") is None
                and current_deduct_eps is not None
                and previous_deduct_eps is not None
                and previous_deduct_eps > 0
            ):
                item["deduct_basic_eps_yoy"] = (
                    current_deduct_eps / previous_deduct_eps - 1
                ) * 100
            else:
                item["deduct_basic_eps_yoy"] = None
            out[code] = item
            break
    return out


def build_fundamentals(
    codes: list[str],
    *,
    trade_date: str | None,
    now: datetime,
) -> tuple[dict[str, dict], dict]:
    valuation, valuation_error = safe_fetch(
        lambda: fetch_eastmoney_valuation_snapshot(codes, trade_date),
        "eastmoney_valuation",
    )
    financials, financial_error = safe_fetch(
        lambda: fetch_eastmoney_financial_snapshot(codes, now.date()),
        "eastmoney_financial",
    )

    out: dict[str, dict] = {}
    for code in codes:
        v = valuation.get(code) or {}
        f = financials.get(code) or {}
        warnings = []
        if not v:
            warnings.append("valuation_unavailable")
        if not f:
            warnings.append("financial_unavailable")
        out[code] = {
            "valuation_date": v.get("valuation_date") or trade_date,
            "pe_dynamic": v.get("pe_dynamic"),
            "pe_ttm": v.get("pe_ttm"),
            "pb": v.get("pb"),
            "market_cap": v.get("market_cap"),
            **f,
            "sources": {
                "valuation": "eastmoney_market_cross_section" if v else None,
                "financial": "eastmoney_RPT_LICO_FN_CPD" if f else None,
            },
            "warnings": warnings,
        }

    stats = {
        "valuation_usable": len(valuation),
        "financial_usable": len(financials),
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
        "errors": [x for x in (valuation_error, financial_error) if x],
    }
    return out, stats


def clock_market_status(now: datetime) -> str:
    hm = now.hour * 60 + now.minute
    if now.weekday() >= 5:
        return "closed"
    if hm < 9 * 60 + 15:
        return "pre_open"
    if hm <= 11 * 60 + 30:
        return "morning_session"
    if hm < 13 * 60:
        return "morning_closed"
    if hm <= 15 * 60:
        return "afternoon_session"
    return "closed"


def infer_trade_date(sources: list[dict[str, dict]], now: datetime) -> str | None:
    dates: list[str] = []
    for source in sources:
        for item in source.values():
            quote_date = normalize_quote_date(item.get("date"))
            if quote_date:
                dates.append(quote_date)
    if not dates:
        return None
    return Counter(dates).most_common(1)[0][0]


def source_is_fresh(item: dict, trade_date: str | None) -> bool:
    if not item or positive_number(item.get("price")) is None:
        return False
    quote_date = normalize_quote_date(item.get("date"))
    return quote_date is not None and trade_date is not None and quote_date == trade_date


def main() -> int:
    now = datetime.now(TZ)
    sina, sina_error = safe_fetch(fetch_sina_snapshot, "sina")
    tencent, tencent_error = safe_fetch(fetch_tencent_snapshot, "tencent")
    if not sina and not tencent:
        print(
            json.dumps(
                {"error": "all_sources_failed", "details": [sina_error, tencent_error]},
                ensure_ascii=False,
            )
        )
        return 2

    trade_date = infer_trade_date([sina, tencent], now)
    status = clock_market_status(now)
    if trade_date is None:
        status = "date_unverified"
    elif trade_date != now.date().isoformat():
        status = "closed_or_no_trade"

    codes = sorted(set(sina) | set(tencent))
    fundamentals, fundamental_stats = build_fundamentals(
        codes,
        trade_date=trade_date,
        now=now,
    )

    stocks: dict[str, dict] = {}
    stats = {"high": 0, "medium": 0, "invalid": 0}

    for code in codes:
        s, t = sina.get(code, {}), tencent.get(code, {})
        fresh = [("sina", s), ("tencent", t)]
        fresh = [(name, item) for name, item in fresh if source_is_fresh(item, trade_date)]

        if fresh:
            source, base = fresh[0]
            primary = positive_number(base.get("price"))
            other_realtime = t if source == "sina" else s
            secondary = positive_number(other_realtime.get("price")) if other_realtime else None
        else:
            source, base, primary, secondary = "none", s or t, None, None

        change_pct = calculate_change_pct(base.get("price"), base.get("prev_close"))
        validation = validate_price(primary_price=primary, secondary_price=secondary)
        warnings = list(validation.warnings)
        for name, item in (("sina", s), ("tencent", t)):
            if item and positive_number(item.get("price")) is not None and not source_is_fresh(item, trade_date):
                warnings.append(f"{name}_date_unverified")
        warnings += validate_quote_fields(
            {
                "price": base.get("price"),
                "prev_close": base.get("prev_close"),
                "change_pct": change_pct,
            }
        )
        quote_time = (
            parse_quote_time(base.get("date"), base.get("time"))
            if source in {"sina", "tencent"}
            else None
        )

        quote = {
            "name": base.get("name") or s.get("name") or t.get("name"),
            "market": "SH" if code.startswith(SH_MAIN_PREFIXES) else "SZ",
            "price": base.get("price"),
            "prev_close": base.get("prev_close"),
            "open": base.get("open"),
            "high": base.get("high"),
            "low": base.get("low"),
            "volume": base.get("volume"),
            "change_pct": change_pct,
            "price_time": quote_time,
            "primary_source": source,
            "source_prices": {
                "sina": s.get("price") if s else None,
                "tencent": t.get("price") if t else None,
            },
            "source_dates": {
                "sina": normalize_quote_date(s.get("date")) if s else None,
                "tencent": normalize_quote_date(t.get("date")) if t else None,
            },
            "confidence": validation.confidence,
            "warnings": sorted(set(warnings)),
            "fundamentals": fundamentals.get(code),
        }
        stocks[code] = quote
        stats[validation.confidence] += 1

    payload = {
        "schema_version": 3,
        "generated_at": now.isoformat(),
        "trade_date": trade_date,
        "timezone": "Asia/Shanghai",
        "market_status": status,
        "source_status": {
            "sina": "ok" if sina else "failed",
            "tencent": "ok" if tencent else "failed",
            "errors": [x for x in (sina_error, tencent_error) if x],
        },
        "validation_stats": stats,
        "fundamental_stats": fundamental_stats,
        "stocks": stocks,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "generated_at": payload["generated_at"],
                "trade_date": trade_date,
                "market_status": status,
                "stocks": len(stocks),
                "stats": stats,
                "fundamental_stats": fundamental_stats,
                "source_status": payload["source_status"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
