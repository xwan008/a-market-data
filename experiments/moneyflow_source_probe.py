#!/usr/bin/env python3
"""Read-only live probe for Eastmoney's per-stock daily money-flow endpoint.

This is a source-availability diagnostic only. It does not write market data,
change candidate selection, or publish any trend-buy result.
"""
from __future__ import annotations

import json
import math
import time
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
URL = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
SOURCE = "eastmoney_push2his_fflow_daykline"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Referer": "https://data.eastmoney.com/zjlx/detail.html",
}
UT = "b2884a393a59ad64002292a3e90d46a5"
FIELDS1 = "f1,f2,f3,f7"
FIELDS2 = "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65"
SAMPLE_CODES = ("600519", "600547", "000001", "002517")
SH_PREFIXES = ("600", "601", "603", "605", "688", "689")


def market_id(code: str) -> int:
    if len(code) != 6 or not code.isdigit():
        raise ValueError("INVALID_A_SHARE_CODE:" + code)
    return 1 if code.startswith(SH_PREFIXES) else 0


def finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number)


def fetch_once(code: str) -> dict:
    response = requests.get(
        URL,
        params={
            "lmt": "10",
            "klt": "101",
            "secid": f"{market_id(code)}.{code}",
            "fields1": FIELDS1,
            "fields2": FIELDS2,
            "ut": UT,
        },
        headers=HEADERS,
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("MONEYFLOW_DATA_MISSING")
    raw = data.get("klines")
    if not isinstance(raw, list):
        raise ValueError("MONEYFLOW_KLINES_MISSING")

    rows = []
    for item in raw:
        fields = str(item).split(",")
        if len(fields) < 13:
            continue
        day = fields[0]
        # Eastmoney field order follows AKShare's maintained parser:
        # f52 main net amount; f55 large; f56 super-large; f57 main net ratio.
        if not day or not all(finite(fields[i]) for i in (1, 4, 5, 6, 11, 12)):
            continue
        rows.append({
            "date": day,
            "main_net_inflow": float(fields[1]),
            "large_net_inflow": float(fields[4]),
            "super_large_net_inflow": float(fields[5]),
            "main_net_inflow_pct": float(fields[6]),
            "close": float(fields[11]),
            "change_pct": float(fields[12]),
        })

    rows.sort(key=lambda row: row["date"])
    recent = rows[-5:]
    dates = [row["date"] for row in recent]
    if len(recent) != 5 or len(set(dates)) != 5:
        raise ValueError("MONEYFLOW_LESS_THAN_FIVE_UNIQUE_DAILY_ROWS")
    return {
        "latest_date": dates[-1],
        "dates": dates,
        "row_count_returned": len(raw),
        "valid_five_day_rows": len(recent),
        "five_day_main_net_inflow": round(sum(x["main_net_inflow"] for x in recent), 2),
        "positive_main_net_inflow_days": sum(x["main_net_inflow"] > 0 for x in recent),
        "rows": recent,
    }


def fetch_datacenter_once(code: str) -> dict:
    """Try the separate datacenter host, which is not the push2 quote cluster."""
    response = requests.get(
        "https://datacenter-web.eastmoney.com/api/data/v1/get",
        params={
            "reportName": "RPT_DMSK_TS_STOCKNEW",
            "columns": "ALL",
            "filter": f'(SECURITY_CODE="{code}")',
            "sortColumns": "TRADE_DATE",
            "sortTypes": "-1",
            "pageSize": 10,
            "pageNumber": 1,
            "source": "WEB",
            "client": "WEB",
        },
        headers=HEADERS,
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    result = payload.get("result") or {}
    raw = result.get("data") or []
    if not raw:
        raise ValueError("DATACENTER_MONEYFLOW_NO_ROWS")
    rows = []
    for item in raw:
        day = str(item.get("TRADE_DATE") or item.get("TRADEDATE") or "")[:10]
        amount = item.get("PRIME_INFLOW")
        if day and finite(amount):
            rows.append({
                "date": day,
                "main_net_inflow": float(amount),
                "raw_field_keys": sorted(item.keys()),
            })
    rows.sort(key=lambda row: row["date"])
    recent = rows[-5:]
    dates = [row["date"] for row in recent]
    if len(recent) != 5 or len(set(dates)) != 5:
        raise ValueError(
            "DATACENTER_MONEYFLOW_LESS_THAN_FIVE_ROWS:"
            + json.dumps({
                "raw_count": len(raw),
                "parsed_count": len(rows),
                "field_keys": sorted(raw[0].keys()) if raw else [],
            }, ensure_ascii=False)
        )
    return {
        "latest_date": dates[-1],
        "dates": dates,
        "valid_five_day_rows": len(recent),
        "five_day_main_net_inflow": round(
            sum(x["main_net_inflow"] for x in recent), 2
        ),
        "positive_main_net_inflow_days": sum(
            x["main_net_inflow"] > 0 for x in recent
        ),
        "field_keys": sorted(raw[0].keys()),
        "rows": recent,
    }


def main() -> int:
    results = {}
    for code in SAMPLE_CODES:
        try:
            first = fetch_datacenter_once(code)
            time.sleep(0.5)
            second = fetch_datacenter_once(code)
            results[code] = {
                "source": "eastmoney_datacenter_RPT_DMSK_TS_STOCKNEW",
                "attempts": [
                    {"ok": True, **first},
                    {"ok": True, **second},
                ],
                "both_attempts_passed": True,
                "five_day_date_window_stable": first["dates"] == second["dates"],
            }
            if first["dates"] != second["dates"]:
                results[code]["error"] = "REPEATED_DATACENTER_DATE_WINDOW_MISMATCH"
        except Exception as exc:
            results[code] = {
                "source": "eastmoney_datacenter_RPT_DMSK_TS_STOCKNEW",
                "both_attempts_passed": False,
                "five_day_date_window_stable": False,
                "error": f"{type(exc).__name__}:{str(exc)[:350]}",
            }

    all_passed = all(
        item.get("both_attempts_passed")
        and item.get("five_day_date_window_stable")
        for item in results.values()
    )
    report = {
        "source": "eastmoney_datacenter_RPT_DMSK_TS_STOCKNEW",
        "endpoint": "https://datacenter-web.eastmoney.com/api/data/v1/get",
        "status": "PASS" if all_passed else "INCOMPLETE",
        "sample_codes": list(SAMPLE_CODES),
        "repeats_per_code": 2,
        "request_count": len(SAMPLE_CODES) * 2,
        "no_repository_data_written": True,
        "results": results,
    }
    print("EASTMONEY_MONEYFLOW_SOURCE_PROBE " + json.dumps(report, ensure_ascii=False))
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
