from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
HISTORY_SHARDS_DIR = DATA_DIR / "history_shards"
LATEST_PATH = DATA_DIR / "latest.json"

# One bounded full-market history store. 5/20/60/120/180 views are derived from
# the same rows; the repository never grows beyond this window per stock.
ROLLING_DAYS = 180
HISTORY_SHARD_KEY_LENGTH = 4
USABLE_CONFIDENCE = {"high", "medium"}
COMPLETED_SESSION_STATUSES = {"closed", "closed_or_no_trade"}


def read_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def should_append_history(latest: dict) -> bool:
    """Accept any snapshot that represents an already-completed trading session."""
    return latest.get("market_status") in COMPLETED_SESSION_STATUSES


def compact_row(trade_date: str, quote: dict) -> dict:
    return {
        "date": trade_date,
        "open": quote.get("open"),
        "high": quote.get("high"),
        "low": quote.get("low"),
        "close": quote.get("price"),
        "volume": quote.get("volume"),
        "volume_unit": "shares",
        "prev_close": quote.get("prev_close"),
        "confidence": quote.get("confidence"),
        "basis": "live_close",
        "source": quote.get("primary_source"),
    }


def merge_rows(
    existing: list[dict],
    incoming: list[dict],
    limit: int = ROLLING_DAYS,
) -> list[dict]:
    by_date: dict[str, dict] = {}
    for row in [*existing, *incoming]:
        d = row.get("date")
        if not d or row.get("close") in (None, 0):
            continue
        by_date[str(d)] = row
    return [by_date[d] for d in sorted(by_date)[-limit:]]


def _basis_after_merge(old_basis: str | None, item: dict, replace: bool) -> str:
    incoming_basis = item.get("history_basis")
    if replace and incoming_basis:
        return str(incoming_basis)
    if incoming_basis:
        return str(incoming_basis)
    if old_basis in {"tencent_qfq", "tencent_qfq_plus_live_tail"}:
        return "tencent_qfq_plus_live_tail"
    return old_basis or "live_close_only"


def _merge_long_term_summary(old: dict, incoming: dict, rows: list[dict]) -> dict | None:
    """Keep the latest compact 52-week summary without storing 252 full bars.

    A weekly qfq refresh recomputes the summary exactly. Between full refreshes we
    only extend a new high/low if the newly appended completed sessions create one;
    expiry of an old 52-week extreme is handled by the next scheduled full refresh.
    """
    summary = dict(incoming or old or {})
    if not summary:
        return None
    for row in rows[-5:]:
        try:
            high = float(row.get("high"))
            low = float(row.get("low"))
        except (TypeError, ValueError):
            continue
        d = str(row.get("date") or "")
        old_high = summary.get("high_52w")
        old_low = summary.get("low_52w")
        if old_high is None or high > float(old_high):
            summary["high_52w"] = high
            summary["high_52w_date"] = d
        if old_low is None or low < float(old_low):
            summary["low_52w"] = low
            summary["low_52w_date"] = d
        if d:
            summary["latest_seen_date"] = max(str(summary.get("latest_seen_date") or ""), d)
    return summary


def write_history_shards(
    series: dict[str, dict],
    generated_at: str | None = None,
    *,
    replace: bool = False,
    prune_to_codes: Iterable[str] | None = None,
) -> int:
    HISTORY_SHARDS_DIR.mkdir(parents=True, exist_ok=True)
    groups: dict[str, dict] = defaultdict(dict)
    valid_codes = {str(c).zfill(6) for c in prune_to_codes} if prune_to_codes is not None else None

    for code, item in series.items():
        code = str(code).zfill(6)
        key = code[:HISTORY_SHARD_KEY_LENGTH]
        groups[key][code] = item

    keys = set(groups)
    if valid_codes is not None:
        keys.update(path.stem for path in HISTORY_SHARDS_DIR.glob("*.json"))

    written = 0
    for key in sorted(keys):
        path = HISTORY_SHARDS_DIR / f"{key}.json"
        current = read_json(path, {"stocks": {}})
        current_stocks = current.get("stocks", {})

        if valid_codes is not None:
            current_stocks = {c: v for c, v in current_stocks.items() if c in valid_codes}

        for code, item in groups.get(key, {}).items():
            old = current_stocks.get(code, {})
            rows = merge_rows(
                [] if replace else old.get("history", []),
                item.get("history", []),
            )
            summary = _merge_long_term_summary(
                old.get("long_term_summary") or {},
                item.get("long_term_summary") or {},
                rows,
            )
            incoming_fundamentals = item.get("fundamentals") or {}
            fundamentals = incoming_fundamentals if incoming_fundamentals else old.get("fundamentals")
            current_stocks[code] = {
                "name": item.get("name") or old.get("name"),
                "history_basis": _basis_after_merge(old.get("history_basis"), item, replace),
                "last_full_refresh": item.get("last_full_refresh") or old.get("last_full_refresh"),
                "long_term_summary": summary,
                "fundamentals": fundamentals,
                "history": rows,
            }

        if not current_stocks:
            if path.exists():
                path.unlink()
            continue

        payload = {
            "schema_version": 4,
            "generated_at": generated_at,
            "rolling_days": ROLLING_DAYS,
            "history_shard_key_length": HISTORY_SHARD_KEY_LENGTH,
            "volume_unit": "shares",
            "shard": key,
            "stocks": current_stocks,
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        written += 1

    return written


def append_latest_snapshot() -> tuple[int, int]:
    latest = read_json(LATEST_PATH, {})

    if not should_append_history(latest):
        print(
            json.dumps(
                {
                    "market_status": latest.get("market_status"),
                    "trade_date": latest.get("trade_date"),
                    "updated_stocks": 0,
                    "reason": "history_only_accepts_completed_sessions",
                },
                ensure_ascii=False,
            )
        )
        return 0, 0

    trade_date = latest.get("trade_date")
    stocks = latest.get("stocks", {})
    if not trade_date or not stocks:
        print("latest.json has no usable trade_date/stocks; history not updated")
        return 0, 0

    try:
        date.fromisoformat(trade_date)
    except ValueError:
        print(f"invalid trade_date: {trade_date}")
        return 0, 0

    updates: dict[str, dict] = {}
    for code, quote in stocks.items():
        if quote.get("confidence") not in USABLE_CONFIDENCE:
            continue
        if quote.get("price") in (None, 0):
            continue
        updates[code] = {
            "name": quote.get("name"),
            "fundamentals": quote.get("fundamentals"),
            "history": [compact_row(trade_date, quote)],
        }

    shard_count = write_history_shards(
        updates,
        latest.get("generated_at"),
        prune_to_codes=stocks.keys(),
    )
    print(
        json.dumps(
            {
                "trade_date": trade_date,
                "market_status": latest.get("market_status"),
                "updated_stocks": len(updates),
                "history_shards": shard_count,
                "rolling_days": ROLLING_DAYS,
            },
            ensure_ascii=False,
        )
    )
    return len(updates), shard_count


def main() -> int:
    append_latest_snapshot()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())