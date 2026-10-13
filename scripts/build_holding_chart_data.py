"""Publish public-only five completed-session OHLC and four intraday holding points.

The holdings watchlist supplies codes only. Neither Airtable trades nor account
information are serialized. This chart data never changes formal trading signals.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from holding_watchlist import load_watchlist

ROOT = Path(__file__).resolve().parents[1]
WATCHLIST_PATH = ROOT / "research" / "holding_watchlist.json"
SNAPSHOT_PATH = ROOT / "research" / "intraday_market_snapshot.json"
HISTORY_DIR = ROOT / "data" / "history_shards"
OUTPUT_PATH = ROOT / "research" / "holding_chart_data.json"
TZ = ZoneInfo("Asia/Shanghai")


def finite_positive(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def completed_bars(code, trade_date, history_dir=HISTORY_DIR):
    """Return up to five genuine completed OHLC bars; never synthesize missing days."""
    path = history_dir / (code[:4] + ".json")
    if not path.is_file():
        return [], None
    shard = read_json(path)
    stock = (shard.get("stocks") or {}).get(code) or {}
    candidates = []
    seen = set()
    for row in stock.get("history") or []:
        raw_date = row.get("date")
        if not isinstance(raw_date, str):
            continue
        try:
            parsed_date = date.fromisoformat(raw_date)
        except ValueError:
            continue
        if parsed_date.isoformat() != raw_date or raw_date >= trade_date or raw_date in seen:
            continue
        seen.add(raw_date)
        values = {key: finite_positive(row.get(key)) for key in ("open", "high", "low", "close")}
        if any(v is None for v in values.values()):
            continue
        if values["low"] > min(values["open"], values["close"]) or values["high"] < max(values["open"], values["close"]) or values["low"] > values["high"]:
            continue
        basis = str(row.get("basis") or stock.get("basis") or "unspecified")
        candidates.append({"date": raw_date, **values, "basis": basis})
    candidates.sort(key=lambda row: row["date"])
    if not candidates:
        return [], None
    # Do not join discontinuous adjusted/unadjusted series into one five-bar chart.
    latest_basis = candidates[-1]["basis"]
    consecutive = []
    for row in reversed(candidates):
        if row["basis"] != latest_basis:
            break
        consecutive.append(row)
        if len(consecutive) == 5:
            break
    bars = [{key: row[key] for key in ("date", "open", "high", "low", "close")}
            for row in reversed(consecutive)]
    return bars, latest_basis


def scan_slot(timestamp):
    """Existing four Beijing snapshot windows, never interpolate a missing scan."""
    try:
        clock = datetime.fromisoformat(timestamp)
    except (TypeError, ValueError):
        return None
    if clock.tzinfo is None:
        return None
    clock = clock.astimezone(TZ)
    minute = clock.hour * 60 + clock.minute
    for slot, start, end in ((1, 570, 625), (2, 625, 690),
                             (3, 780, 850), (4, 850, 900)):
        if start <= minute < end:
            return slot
    return None


def build_chart_data(snapshot, watchlist, previous, history_dir=HISTORY_DIR):
    if snapshot.get("result_kind") != "a_share_intraday_market_snapshot":
        raise ValueError("INVALID_HOLDING_SNAPSHOT_KIND")
    trade_date = snapshot.get("trade_date")
    try:
        if date.fromisoformat(trade_date).isoformat() != trade_date:
            raise ValueError()
    except (TypeError, ValueError):
        raise ValueError("INVALID_HOLDING_TRADE_DATE") from None
    captured_at = snapshot.get("captured_at")
    if not isinstance(captured_at, str) or not captured_at.startswith(trade_date) or scan_slot(captured_at) is None:
        raise ValueError("INVALID_HOLDING_SNAPSHOT_TIME")
    if (snapshot.get("validation") or {}).get("status") != "passed":
        raise ValueError("HOLDING_SNAPSHOT_NOT_VALIDATED")
    holding_quotes = snapshot.get("holding_stocks")
    if not isinstance(holding_quotes, dict):
        raise ValueError("HOLDING_QUOTES_NOT_PUBLISHED")
    codes = {row["code"] for row in watchlist}
    if set(holding_quotes) != codes:
        raise ValueError("HOLDING_QUOTES_COVERAGE_MISMATCH")
    if not isinstance(previous, dict) or previous.get("result_kind") != "a_share_holding_charts" or previous.get("trade_date") != trade_date:
        previous = {}
    old_stocks = previous.get("stocks") or {}
    if not isinstance(old_stocks, dict):
        old_stocks = {}
    slot = scan_slot(captured_at)
    stocks = {}
    for code in sorted(codes):
        bars, basis = completed_bars(code, trade_date, history_dir)
        old = old_stocks.get(code) or {}
        points = {}
        for item in old.get("intraday_points") or []:
            if (isinstance(item, dict) and item.get("slot") in (1, 2, 3, 4)
                and isinstance(item.get("scan_at"), str)
                and item["scan_at"].startswith(trade_date)
                and scan_slot(item["scan_at"]) == item["slot"]
                and finite_positive(item.get("price")) is not None):
                points[item["slot"]] = {key: item[key] for key in ("slot", "scan_at", "quote_time", "price") if key in item}
        quote = holding_quotes[code]
        if (isinstance(quote, dict) and quote.get("code") == code
            and quote.get("source_scope") == "holding_watchlist"
            and quote.get("confidence") in ("high", "medium")
            and finite_positive(quote.get("price")) is not None
            and isinstance(quote.get("quote_time"), str)
            and quote["quote_time"].startswith(trade_date)):
            current = {"slot": slot, "scan_at": captured_at,
                       "quote_time": quote["quote_time"], "price": quote["price"]}
            if slot not in points or points[slot]["scan_at"] < captured_at:
                points[slot] = current
        stocks[code] = {
            "daily_bars": bars, "daily_basis": basis,
            "daily_last_date": bars[-1]["date"] if bars else None,
            "intraday_points": [points[n] for n in sorted(points)],
        }
    return {
        "schema_version": 1, "result_kind": "a_share_holding_charts",
        "trade_date": trade_date, "timezone": "Asia/Shanghai",
        "source_snapshot_at": captured_at, "stocks": stocks,
    }


def main():
    snapshot = read_json(SNAPSHOT_PATH)
    watchlist = load_watchlist(WATCHLIST_PATH)
    previous = read_json(OUTPUT_PATH) if OUTPUT_PATH.exists() else {}
    result = build_chart_data(snapshot, watchlist, previous)
    OUTPUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("HOLDING_CHARTS_OK", result["trade_date"], len(result["stocks"]),
          "intraday_points", {c: len(v["intraday_points"]) for c, v in result["stocks"].items()})


if __name__ == "__main__":
    main()
