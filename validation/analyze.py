"""Independent, forward-only trend lifecycle and stock-selection observations.

Never changes research/, data/, or any original algorithm.  Metrics are
signal-close -> future-close *observations*, NOT executable READY trades.
Missing days and unusable quote coverage are never interpreted as failures.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "validation"
HORIZONS = (1, 3, 5, 10, 20)
MIN_BASKET_COVERAGE = .9


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def archive_days(base=BASE) -> list[tuple[str, Path]]:
    result = []
    for folder in sorted((base / "archive").glob("????-??-??")):
        if all((folder / n).is_file() for n in
               ("manifest.json", "trend_registry.json", "trend_buy_formal_result.json", "universe.json")):
            result.append((folder.name, folder))
    return result


def collect_prices(base=BASE, root=ROOT, asof=None) -> str:
    """Capture completed-day closes before 65-bar rolling history can expire."""
    latest = load(root / "data" / "latest.json")
    day = asof or datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    if latest.get("trade_date") != day or latest.get("market_status") in {
            "morning_session", "morning_closed", "afternoon_session"}:
        print("VALIDATION_PRICES_WAIT_FOR_COMPLETED_DAY", day)
        return "waiting"
    target = base / "prices" / (day + ".json")
    if target.exists():
        print("VALIDATION_PRICES_ALREADY_SAVED_IMMUTABLE", day)
        return "existing"

    track = set()
    window_start = (date.fromisoformat(day) - timedelta(days=80)).isoformat()
    for d, folder in archive_days(base):
        if window_start <= d <= day:
            universe = load(folder / "universe.json")
            for theme in universe.values():
                track.update(theme.get("constituents") or [])
            formal = load(folder / "trend_buy_formal_result.json")
            for kind in ("ready", "wait", "uncertain", "drop"):
                track.update(str(item["code"]).zfill(6) for item in formal.get(kind, []))

    prices, daily_returns, calendar_count = {}, [], Counter()
    all_count, fresh_count = 0, 0
    for file in sorted((root / "data" / "history_shards").glob("*.json")):
        source = load(file)
        for code, company in (source.get("stocks") or {}).items():
            rows = sorted((r for r in company.get("history", [])
                           if isinstance(r.get("date"), str)), key=lambda r: r["date"])
            if not rows:
                continue
            all_count += 1
            for row in rows[-35:]:
                if row["date"] <= day and isinstance(row.get("close"), (int, float)) and row["close"] > 0:
                    calendar_count[row["date"]] += 1
            current = rows[-1]
            if current["date"] != day:
                continue
            close = current.get("close")
            if not isinstance(close, (int, float)) or close <= 0:
                continue
            fresh_count += 1
            if len(rows) > 1:
                previous = rows[-2].get("close")
                if isinstance(previous, (int, float)) and previous > 0:
                    change = (close / previous - 1) * 100
                    if -25 < change < 25:
                        daily_returns.append(change)
            if code in track:
                prices[code] = {
                    "close": round(close, 5),
                    "history_basis": company.get("history_basis"),
                }

    if not all_count or fresh_count / all_count < .8 or len(daily_returns) < 500:
        print("VALIDATION_PRICES_INCOMPLETE", day, fresh_count, all_count)
        return "incomplete"
    threshold = max(100, int(max(calendar_count.values()) * .4))
    calendar = sorted(d for d, n in calendar_count.items()
                      if n >= threshold and d <= day)
    if day not in calendar:
        raise ValueError("LATEST_DAY_NOT_IN_VERIFIED_CALENDAR")
    write(target, {
        "schema_version": 1, "trade_date": day, "price_source": "rolling_history_shards",
        "price_basis": "as_stored_in_history_shards",
        "research_and_portfolio_independent": True,
        "market_proxy": "equal_weight_daily_return_of_fresh_mainboard_stocks",
        "market_daily_return_pct": round(mean(daily_returns), 6),
        "market_daily_sample": len(daily_returns),
        "fresh_stock_coverage": round(fresh_count / all_count, 5),
        "expected_market_calendar": calendar,
        "tracked_stock_count": len(track),
        "stocks": prices
    })
    print("VALIDATION_PRICES_CAPTURED", day, len(prices), len(track))
    return "created"


def future_result(code, start, horizon, prices, calendar, end_day):
    if start not in calendar:
        return {"state": "data_gap", "reason": "signal_date_not_in_calendar"}
    at = calendar.index(start) + horizon
    if at >= len(calendar) or calendar[at] > end_day:
        return {"state": "pending"}
    target = calendar[at]
    required = calendar[calendar.index(start):at + 1]
    if any(d not in prices for d in required):
        return {"state": "data_gap", "reason": "missing_daily_snapshot", "target_date": target}
    before = prices[start].get("stocks", {}).get(code)
    after = prices[target].get("stocks", {}).get(code)
    if not before or not after or before.get("history_basis") != after.get("history_basis"):
        return {"state": "data_gap", "reason": "missing_or_mixed_price_basis", "target_date": target}
    base, last = before.get("close"), after.get("close")
    if not base or not last:
        return {"state": "data_gap", "reason": "invalid_prices", "target_date": target}
    compounded = 1.0
    for d in required[1:]:
        daily = prices[d].get("market_daily_return_pct")
        if not isinstance(daily, (int, float)):
            return {"state": "data_gap", "reason": "missing_market_benchmark", "target_date": target}
        compounded *= (1 + daily / 100)
    raw = (last / base - 1) * 100
    market = (compounded - 1) * 100
    return {
        "state": "matured", "target_date": target, "return_pct": round(raw, 3),
        "market_return_pct": round(market, 3),
        "excess_vs_market_pct": round(raw - market, 3)
    }


def basket_result(codes, start, horizon, prices, calendar, end_day):
    if not codes:
        return {"state": "unavailable", "reason": "no_frozen_constituents"}
    returns = [future_result(code, start, horizon, prices, calendar, end_day)
               for code in codes]
    matured = [x for x in returns if x["state"] == "matured"]
    if any(x["state"] == "pending" for x in returns):
        # Coverage may be partial, but a future date has not yet matured.
        return {"state": "pending"}
    coverage = len(matured) / len(codes)
    if coverage < MIN_BASKET_COVERAGE:
        return {"state": "data_gap", "reason": "insufficient_constituent_coverage",
                "coverage": round(coverage, 4)}
    raw = mean(x["return_pct"] for x in matured)
    market = mean(x["market_return_pct"] for x in matured)
    return {"state": "matured", "target_date": matured[0]["target_date"],
            "constituent_count": len(codes), "covered_count": len(matured),
            "coverage": round(coverage, 4), "return_pct": round(raw, 3),
            "market_return_pct": round(market, 3),
            "excess_vs_market_pct": round(raw - market, 3)}


def compile_results(base=BASE) -> dict:
    days = archive_days(base)
    snapshots = {p.stem: load(p) for p in sorted((base / "prices").glob("????-??-??.json"))}
    if not days:
        return {"status": "COLLECTING", "archive_days": 0, "trend_episodes": 0, "stock_signals": 0}

    latest_prices = snapshots[max(snapshots)] if snapshots else {}
    calendar = latest_prices.get("expected_market_calendar") or sorted(snapshots)
    calendar = sorted(set(calendar))
    last_price_day = max(snapshots) if snapshots else None
    registry_by_day = {day: load(folder / "universe.json") for day, folder in days}
    dates = [d for d, _ in days]

    # Only adjacent verified market sessions can establish a transition;
    # if a day was not archived, its unknown state is NEVER called failure.
    episodes, active = [], {}
    for day, _ in days:
        today = registry_by_day[day]
        for name in sorted(set(active) | set(today)):
            record = today.get(name)
            is_confirmed = bool(record and record["market_state"] == "趋势确认")
            prior = active.get(name)
            if prior:
                consecutive = (prior["last_date"] in calendar and day in calendar and
                               calendar.index(day) == calendar.index(prior["last_date"]) + 1)
                if not consecutive or record is None:
                    prior["end_date"] = prior["last_date"]
                    prior["ending"] = "censored_data_gap"
                    active.pop(name)
                elif not is_confirmed:
                    prior["end_date"] = prior["last_date"]
                    prior["first_downgrade_date"] = day
                    prior["ending"] = "lost_confirmation"
                    active.pop(name)
            if is_confirmed:
                if name not in active:
                    entry = {"trend_name": name, "start_date": day, "last_date": day,
                             "confirmed_sessions": 1, "end_date": None,
                             "first_downgrade_date": None, "ending": "right_censored",
                             "constituents": record["constituents"] if record.get("constituents_usable") else [],
                             "universe_issues": record.get("universe_issues", [])}
                    episodes.append(entry)
                    active[name] = entry
                elif active[name]["start_date"] != day:
                    active[name]["last_date"] = day
                    active[name]["confirmed_sessions"] += 1

    trends = []
    for ep in episodes:
        record = {k: v for k, v in ep.items() if k != "constituents"}
        record["frozen_constituent_count"] = len(ep["constituents"])
        record["one_day_confirmation"] = (ep["confirmed_sessions"] == 1
                                          if ep["ending"] == "lost_confirmation" else None)
        record["horizons"] = {
            str(h): basket_result(ep["constituents"], ep["start_date"], h,
                                  snapshots, calendar, last_price_day)
            if last_price_day else {"state": "pending"}
            for h in HORIZONS
        }
        trends.append(record)

    stock_signals = []
    for day, folder in days:
        formal = load(folder / "trend_buy_formal_result.json")
        universe = registry_by_day[day]
        for status in ("ready", "wait", "uncertain", "drop"):
            for item in formal.get(status, []):
                code = str(item.get("code", "")).zfill(6)
                sector = item.get("trend_name")
                r = {"trade_date": day, "code": code,
                     "company_name": item.get("company_name"), "trend_name": sector,
                     "status": status.upper(), "rank": item.get("rank"),
                     "source_run_id": formal.get("run_id"),
                     "observation_only": True,
                     "ready_trigger_simulated": False, "horizons": {}}
                for horizon in HORIZONS:
                    result = (future_result(code, day, horizon, snapshots, calendar, last_price_day)
                              if last_price_day else {"state": "pending"})
                    frozen = universe.get(sector, {})
                    benchmark = (basket_result(frozen.get("constituents", [])
                                               if frozen.get("constituents_usable") else [],
                                               day, horizon, snapshots, calendar, last_price_day)
                                 if last_price_day else {"state": "pending"})
                    if result["state"] == "matured" and benchmark["state"] == "matured":
                        result["excess_vs_sector_pct"] = round(
                            result["return_pct"] - benchmark["return_pct"], 3)
                    else:
                        result["excess_vs_sector_pct"] = None
                    r["horizons"][str(horizon)] = result
                stock_signals.append(r)

    matured = lambda rows, horizon: [
        r["horizons"][str(horizon)]["excess_vs_market_pct"] for r in rows
        if r["horizons"][str(horizon)]["state"] == "matured"
    ]
    closed = [r for r in trends if r["ending"] == "lost_confirmation"]
    summary = {
        "schema_version": 1,
        "status": "AVAILABLE",
        "as_of_trade_date": last_price_day,
        "first_archived_trade_date": dates[0],
        "last_archived_trade_date": dates[-1],
        "archive_days": len(days),
        "trend_episodes": len(trends),
        "closed_confirmations": len(closed),
        "one_day_confirmations": sum(r["one_day_confirmation"] is True for r in closed),
        "one_day_confirmation_pct": (round(
            100 * sum(r["one_day_confirmation"] is True for r in closed) / len(closed), 2)
            if closed else None),
        "censored_confirmations": sum(r["ending"].startswith("censored") for r in trends),
        "stock_signals": len(stock_signals),
        "method": "forward_only_close_to_close_observations_not_tradable_signals",
        "horizon_stats": {
            str(h): {
                "trend_matured": len(matured(trends, h)),
                "trend_avg_excess_vs_market_pct":
                    round(mean(matured(trends, h)), 3) if matured(trends, h) else None,
                "stock_matured": len(matured(stock_signals, h)),
                "stock_avg_excess_vs_market_pct":
                    round(mean(matured(stock_signals, h)), 3) if matured(stock_signals, h) else None
            } for h in HORIZONS
        }
    }
    write(base / "results" / "summary.json", summary)
    write(base / "results" / "trends.json", {"schema_version": 1, "items": trends})
    write(base / "results" / "stocks.json", {"schema_version": 1, "items": stock_signals})
    print("VALIDATION_RESULTS_GENERATED", len(trends), len(stock_signals))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument("--skip-capture", action="store_true")
    args = parser.parse_args()
    if not args.skip_capture:
        collect_prices(asof=args.date)
    print(json.dumps(compile_results(), ensure_ascii=False))


if __name__ == "__main__":
    main()
