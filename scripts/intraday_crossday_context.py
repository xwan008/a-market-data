"""Bounded cross-day context for intraday snapshot; never mutates same-day previous_*.

Price history uses completed-session bars for the *current frozen membership*.
Persisted monitor history is a separate, clearly labelled last intraday scan,
not an official closing price or a same-day transition.
"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
HISTORY_SHARDS_DIR = ROOT / "data" / "history_shards"
MONITOR_PATH = ROOT / "research" / "intraday_monitor_state.json"
ARCHIVE_PATH = ROOT / "research" / "intraday_crossday_archive.json"
MAX_ARCHIVE_DAYS = 30
USABLE_QUALITY = {"READY", "DEGRADED"}
USABLE_CONFIDENCE = {"high", "medium"}


def read_archive() -> dict:
    if not ARCHIVE_PATH.exists():
        return {"schema_version": 1, "result_kind": "a_share_intraday_crossday_archive", "days": []}
    data = json.loads(ARCHIVE_PATH.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("result_kind") != "a_share_intraday_crossday_archive" or not isinstance(data.get("days"), list):
        raise ValueError("invalid_crossday_archive")
    return data


def extract_day(state: dict) -> dict | None:
    """Compact one *persisted* trading day's last valid board/stock observations."""
    day = state.get("trade_date")
    if (state.get("result_kind") != "a_share_intraday_monitor_state"
        or not isinstance(day, str) or len(day) != 10 or state.get("monitor_date") != day):
        return None
    frozen = {x.get("trend_name"): x for x in state.get("frozen_trends") or [] if isinstance(x, dict)}
    trends = {}
    for name, records in (state.get("industry_history") or {}).items():
        if not isinstance(records, list):
            continue
        valid = [r for r in records if isinstance(r, dict) and r.get("scan_at", "")[:10] == day and r.get("data_quality") in USABLE_QUALITY]
        if not valid:
            continue
        last = max(valid, key=lambda r: r["scan_at"])
        trends[name] = {
            "industry_codes": sorted(frozen.get(name, {}).get("industry_codes") or []),
            "scan_at": last["scan_at"],
            "trend_state": last.get("trend_state"),
            "market_state": last.get("market_state"),
            "last_intraday_state": last.get("current_state"),
            "last_intraday_momentum": last.get("structure_momentum"),
            "last_entry_action": last.get("entry_action"),
            "last_holding_action": last.get("holding_action"),
            "up_ratio": last.get("up_ratio"),
            "median_change_pct": last.get("median_change_pct"),
            "coverage_ratio": last.get("coverage_ratio"),
            "data_quality": last.get("data_quality"),
        }
    stocks = {}
    stock_scans = state.get("stock_history") or {}
    for scan in sorted(stock_scans):
        item = stock_scans[scan]
        if not isinstance(item, dict) or scan.removeprefix("scan_")[:10] != day or item.get("data_quality") not in USABLE_QUALITY:
            continue
        for code, row in (item.get("stocks") or {}).items():
            if row.get("data_quality") not in USABLE_QUALITY:
                continue
            stocks[code] = {
                "scan_at": scan.removeprefix("scan_"),
                "trend_name": row.get("trend_name"),
                "industry_code": row.get("industry_code"),
                "price": row.get("price"),
                "relative_strength": row.get("relative_strength"),
                "price_behavior": row.get("price_behavior"),
                "entry_action": row.get("entry_action"),
                "holding_action": row.get("holding_action"),
            }
    if not trends and not stocks:
        return None
    return {"trade_date": day, "source_last_scan_at": state.get("last_scan_at"), "trends": trends, "stocks": stocks}


def merge_archive(archive: dict, monitor_path: Path, today: str) -> dict:
    days = {d["trade_date"]: d for d in archive.get("days", []) if isinstance(d, dict) and isinstance(d.get("trade_date"), str) and d["trade_date"] < today}
    if monitor_path.exists():
        try:
            candidate = extract_day(json.loads(monitor_path.read_text(encoding="utf-8")))
            if candidate and candidate["trade_date"] < today:
                old = days.get(candidate["trade_date"])
                if not old or str(candidate.get("source_last_scan_at") or "") > str(old.get("source_last_scan_at") or ""):
                    days[candidate["trade_date"]] = candidate
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            # Optional enrichment must not turn corrupt previous state into valid history.
            pass
    return {
        "schema_version": 1,
        "result_kind": "a_share_intraday_crossday_archive",
        "days": [days[d] for d in sorted(days)[-MAX_ARCHIVE_DAYS:]],
    }


def read_price_histories(codes: set[str], baseline_date: str) -> tuple[dict[str, list[dict]], list[str], int]:
    """Read only the small set of prefix shards used by current frozen boards."""
    histories = {}
    errors = []
    shard_count = 0
    for prefix in sorted({code[:4] for code in codes}):
        path = HISTORY_SHARDS_DIR / f"{prefix}.json"
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            shard_count += 1
            for code, stock in (data.get("stocks") or {}).items():
                if code not in codes:
                    continue
                rows = sorted((r for r in stock.get("history") or []
                               if r.get("date") and r["date"] <= baseline_date
                               and r.get("confidence") in USABLE_CONFIDENCE
                               and isinstance(r.get("close"), (int, float)) and r["close"] > 0),
                              key=lambda r: r["date"])
                # Reject stale stock history and do not present it as yesterday's bars.
                if rows and rows[-1]["date"] == baseline_date:
                    histories[code] = rows
        except (ValueError, TypeError, AttributeError, json.JSONDecodeError) as exc:
            errors.append(f"history_shard_invalid:{prefix}:{type(exc).__name__}")
    return histories, errors, shard_count


def return_summary(codes: list[str], histories: dict[str, list[dict]], window: int) -> dict:
    returns = []
    for code in codes:
        rows = histories.get(code) or []
        if len(rows) < window + 1:
            continue
        start, end = rows[-window - 1]["close"], rows[-1]["close"]
        if start > 0:
            returns.append((end / start - 1) * 100)
    target = len(codes)
    coverage = len(returns) / target if target else 0.0
    return {
        "window_sessions": window,
        "sample_count": len(returns),
        "target_count": target,
        "coverage_ratio": round(coverage, 4),
        "status": "available" if coverage >= .8 else "partial" if returns else "unavailable",
        "median_constituent_return_pct": round(median(returns), 4) if returns else None,
        "positive_constituent_ratio": round(sum(r > 0 for r in returns) / len(returns), 4) if returns else None,
    }


def build_board_context(trends: dict, baseline_date: str, archive: dict) -> tuple[dict, dict]:
    all_codes = {code for trend in trends.values() for code in trend.get("company_codes") or []}
    histories, errors, count = read_price_histories(all_codes, baseline_date)
    previous_day = next((d for d in archive.get("days", []) if d.get("trade_date") == baseline_date), None)
    contexts = {}
    for name, trend in trends.items():
        codes = sorted(set(trend.get("company_codes") or []))
        previous = ((previous_day or {}).get("trends") or {}).get(name)
        same_universe = bool(previous and sorted(previous.get("industry_codes") or []) == sorted(trend.get("industry_codes") or []))
        contexts[name] = {
            "baseline_trade_date": baseline_date,
            "constituent_basis": "current_frozen_universe_completed_sessions",
            "seven_day": return_summary(codes, histories, 7),
            "previous_trade_day": ({
                "trade_date": baseline_date,
                "basis": "last_persisted_intraday_scan_not_official_close",
                "same_industry_codes": same_universe,
                **previous,
            } if previous else None),
        }
    return contexts, {
        "board_history_target_count": len(contexts),
        "board_history_7d_available_count": sum(v["seven_day"]["status"] == "available" for v in contexts.values()),
        "board_previous_day_available_count": sum(v["previous_trade_day"] is not None for v in contexts.values()),
        "board_history_shard_read_count": count,
        "board_history_errors": errors,
    }


def build_stock_seven_day_context(codes: set[str], baseline_date: str) -> tuple[dict, dict]:
    """Seven completed stock-to-stock return intervals, from eight valid closes.

    Independent of materialized low-risk parts so newly configured windows are
    available on the first intraday refresh, even before the next daily rebuild.
    """
    histories, errors, shard_count = read_price_histories(codes, baseline_date)
    contexts = {}
    for code in sorted(codes):
        rows = histories.get(code) or []
        enough = len(rows) >= 8
        contexts[code] = {
            "source_trade_date": baseline_date,
            "window_sessions": 7,
            "status": "available" if enough else "unavailable",
            "observation_count": 8 if enough else len(rows),
            "close_change_7d_pct": (
                round((rows[-1]["close"] / rows[-8]["close"] - 1) * 100, 4)
                if enough else None
            ),
            "basis": "eight_valid_completed_session_closes",
        }
    return contexts, {
        "stock_history_7d_target_count": len(codes),
        "stock_history_7d_available_count": sum(x["status"] == "available" for x in contexts.values()),
        "stock_history_7d_shard_read_count": shard_count,
        "stock_history_7d_errors": errors,
    }
