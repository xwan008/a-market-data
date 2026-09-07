from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from .backfill_history import fetch_tencent_history
    from .history_store import HISTORY_SHARDS_DIR, read_json, write_history_shards
except ImportError:  # direct script execution
    from backfill_history import fetch_tencent_history
    from history_store import HISTORY_SHARDS_DIR, read_json, write_history_shards

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
LATEST_PATH = DATA_DIR / "latest.json"
STATUS_PATH = DATA_DIR / "repair_status.json"

# Yesterday's stored qfq close and today's exchange reference prev_close should
# normally be nearly identical. A material mismatch is a strong corporate-action
# signal. Keep both relative and absolute guards to avoid rounding noise.
MISMATCH_PCT = 0.004
MISMATCH_ABS = 0.02
USABLE_CONFIDENCE = {"high", "medium"}
SKIP_MARKET_STATUS = {"pre_open", "date_unverified", "closed_or_no_trade"}


def as_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def previous_completed_row(history: list[dict], trade_date: str) -> dict | None:
    rows = [r for r in history if str(r.get("date") or "") < trade_date]
    if not rows:
        return None
    return max(rows, key=lambda r: str(r.get("date") or ""))


def mismatch_ratio(history_close: float, prev_close: float) -> float:
    if history_close <= 0:
        return 0.0
    return abs(prev_close / history_close - 1.0)


def is_corporate_action_suspect(history_close: float, prev_close: float) -> bool:
    return (
        abs(prev_close - history_close) >= MISMATCH_ABS
        and mismatch_ratio(history_close, prev_close) >= MISMATCH_PCT
    )


def load_all_history_items() -> dict[str, dict]:
    """Read each history shard once instead of reparsing it per stock."""
    items: dict[str, dict] = {}
    for path in HISTORY_SHARDS_DIR.glob("*.json"):
        payload = read_json(path, {"stocks": {}})
        items.update(payload.get("stocks", {}))
    return items


def main() -> int:
    latest = read_json(LATEST_PATH, {})
    trade_date = latest.get("trade_date")
    market_status = latest.get("market_status")
    stocks = latest.get("stocks", {})
    refreshed_at = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()

    if not trade_date or not stocks or market_status in SKIP_MARKET_STATUS:
        status = {
            "schema_version": 1,
            "generated_at": refreshed_at,
            "trade_date": trade_date,
            "market_status": market_status,
            "detected": 0,
            "repaired": 0,
            "failed": 0,
            "reason": "no_current_trading_session_to_check",
        }
        STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(status, ensure_ascii=False))
        return 0

    history_items = load_all_history_items()
    suspects: dict[str, dict] = {}
    for code, quote in stocks.items():
        if quote.get("confidence") not in USABLE_CONFIDENCE:
            continue
        prev_close = as_float(quote.get("prev_close"))
        if prev_close is None or prev_close <= 0:
            continue
        item = history_items.get(code, {})
        previous = previous_completed_row(item.get("history", []), trade_date)
        if not previous:
            continue
        historical_close = as_float(previous.get("close"))
        if historical_close is None or historical_close <= 0:
            continue
        if is_corporate_action_suspect(historical_close, prev_close):
            suspects[code] = {
                "name": quote.get("name") or item.get("name"),
                "history_date": previous.get("date"),
                "history_close": historical_close,
                "prev_close": prev_close,
                "mismatch_pct": mismatch_ratio(historical_close, prev_close) * 100,
            }

    repaired: dict[str, dict] = {}
    failures: dict[str, str] = {}
    for code, meta in suspects.items():
        code_out, item, error = fetch_tencent_history(
            code,
            meta.get("name"),
            refreshed_at,
            exclude_date=trade_date,
        )
        if item is not None:
            repaired[code_out] = item
        else:
            failures[code] = error or "unknown"

    if repaired:
        write_history_shards(repaired, refreshed_at, replace=True)

    status = {
        "schema_version": 1,
        "generated_at": refreshed_at,
        "trade_date": trade_date,
        "market_status": market_status,
        "threshold_pct": MISMATCH_PCT * 100,
        "threshold_abs": MISMATCH_ABS,
        "history_shards_scanned": len(list(HISTORY_SHARDS_DIR.glob("*.json"))),
        "stocks_checked": len(stocks),
        "detected": len(suspects),
        "repaired": len(repaired),
        "failed": len(failures),
        "sample_suspects": dict(list(suspects.items())[:20]),
        "sample_failures": dict(list(failures.items())[:20]),
    }
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False))
    # A transient targeted repair failure should not block fresh quote publication;
    # history_confidence and the weekly full qfq refresh remain the safety net.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
