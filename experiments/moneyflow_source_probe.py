#!/usr/bin/env python3
"""Read-only diagnostic for Eastmoney's per-stock daily money-flow history.

The probe deliberately makes one request per candidate, serially. Eastmoney's
push2/push2his clusters can close connections after bursts; this diagnostic
must not hide that behavior with aggressive retries.
"""
from __future__ import annotations

import json
import math
import time
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
FALLBACK_CODES = ("600519", "600547", "000001", "002517")
SH_PREFIXES = ("600", "601", "603", "605", "688", "689")
REQUEST_GAP_SECONDS = 3.0
MAX_PROBE_CODES = 15


def candidate_codes() -> tuple[list[str], str]:
    path = ROOT / "research/trend_buy_candidates/latest.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        groups = payload.get("industries") or []
        codes = []
        for group in groups:
            codes.extend(group.get("selected_codes") or [])
        codes = list(dict.fromkeys(str(code).zfill(6) for code in codes))
        if codes:
            return codes[:MAX_PROBE_CODES], "latest_frozen_candidate_admission"
    except (OSError, ValueError, TypeError):
        pass
    return list(FALLBACK_CODES), "static_cross_market_fallback"


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


def fetch_five_days(code: str) -> dict:
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
        # f52=main net inflow; f55=large; f56=super-large; f57=main net ratio.
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
        "five_day_main_net_inflow": round(
            sum(x["main_net_inflow"] for x in recent), 2
        ),
        "positive_main_net_inflow_days": sum(
            x["main_net_inflow"] > 0 for x in recent
        ),
        "rows": recent,
    }


def main() -> int:
    codes, scope = candidate_codes()
    results = {}
    for index, code in enumerate(codes):
        try:
            results[code] = {"ok": True, **fetch_five_days(code)}
        except Exception as exc:
            results[code] = {
                "ok": False,
                "error": f"{type(exc).__name__}:{str(exc)[:220]}",
            }
        if index + 1 < len(codes):
            time.sleep(REQUEST_GAP_SECONDS)

    passed = sum(bool(item.get("ok")) for item in results.values())
    report = {
        "source": SOURCE,
        "endpoint": URL,
        "status": "PASS" if passed == len(codes) else "INCOMPLETE",
        "candidate_scope": scope,
        "sample_codes": codes,
        "request_count": len(codes),
        "request_gap_seconds": REQUEST_GAP_SECONDS,
        "passed_codes": passed,
        "total_codes": len(codes),
        "no_repository_data_written": True,
        "results": results,
    }
    print("EASTMONEY_MONEYFLOW_SOURCE_PROBE " + json.dumps(report, ensure_ascii=False))
    return 0 if passed == len(codes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
