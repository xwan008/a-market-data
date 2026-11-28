"""Completed-session funds and cross-day public observations for focus SHADOW.
No portfolio metadata, model calls, trades or upstream writes.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from urllib.parse import urlencode

import freeze_trend_buy_fund_flow as frozen
import on_demand_market_probe as probe

WINDOWS = (1, 5, 10, 20)
ARCHIVE_LIMIT = 30
RESEARCH_LIMIT = 10


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def blob_sha(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def session_dates(sessions, expected):
    day = dt.date.fromisoformat(expected)
    if day not in sessions:
        raise ValueError("HISTORY_BASELINE_NOT_SESSION")
    index = sessions.index(day)
    return [d.isoformat() for d in sessions[max(0, index-19):index+1]]


def checked_history(row, sym, dates, kind):
    """Require a contiguous completed-session suffix, not a fabricated 20-day window."""
    if not dates or row.get("code") != sym[2:] or row.get("trade_date") != dates[-1]:
        raise ValueError("HISTORY_IDENTITY_DATE")
    provider = row.get("provider")
    if provider not in frozen.PROVIDERS:
        raise ValueError("HISTORY_PROVIDER")
    raw = row.get("daily")
    if not isinstance(raw, list) or not 5 <= len(raw) <= len(dates):
        raise ValueError("HISTORY_COVERAGE")
    if [r.get("date") for r in raw] != dates[-len(raw):]:
        raise ValueError("HISTORY_NOT_CONTIGUOUS")
    rows = []
    for r in raw:
        net = frozen.numeric(r["main_net_cny"])
        amount = frozen.numeric(r["amount_cny"])
        if amount <= 0 or abs(net) > amount:
            raise ValueError("HISTORY_AMOUNT")
        clean = {"date": r["date"], "main_net_cny": net, "amount_cny": amount}
        if "big_net_cny" in r and "super_net_cny" in r:
            big, sup = frozen.numeric(r["big_net_cny"]), frozen.numeric(r["super_net_cny"])
            if abs(big + sup - net) > 2 or max(abs(big), abs(sup)) > amount:
                raise ValueError("HISTORY_CLASSIFICATION")
            clean.update(big_net_cny=big, super_net_cny=sup)
        rows.append(clean)
    return {"code": sym[2:], "provider": provider, "definition": frozen.DEFINITIONS[provider],
            "trade_date": dates[-1], "source_kind": kind, "queried_at": row.get("queried_at"),
            "coverage": "COMPLETE" if len(rows) == 20 else "PARTIAL",
            "daily": rows, "windows": frozen.metrics(rows),
            "sources": row.get("sources", []), "unit": "CNY"}


def frozen_histories(root, expected, symbols, dates, formal_run_id):
    """Read only the admission blob actually named by the paired formal result."""
    if not formal_run_id:
        return {}
    try:
        formal = load(root / "research/trend_buy_formal_result.json")
        raw = (root / "research/trend_buy_candidates/latest.json").read_bytes()
        provenance = formal.get("fresh_mainline_provenance") or {}
        if (formal.get("trade_date") != expected or formal.get("run_id") != formal_run_id
                or provenance.get("company_research_admission_sha") != blob_sha(raw)):
            return {}
        admission = json.loads(raw)
        flow = admission.get("fund_flow") or {}
        if admission.get("trade_date") != expected or flow.get("trade_date") != expected:
            return {}
    except (OSError, ValueError, TypeError, KeyError):
        return {}
    matches = {}
    ambiguous = set()
    targets = set(symbols)
    for group in flow.get("groups", []):
        if group.get("status") != "VERIFIED":
            continue
        for code, row in (group.get("stocks") or {}).items():
            sym = ("sh" if code.startswith("6") else "sz") + code
            if sym not in targets or row.get("provider") != group.get("provider"):
                continue
            try:
                data = checked_history(row, sym, dates, "FORMAL_FROZEN_ADMISSION")
                data["admission_blob_sha"] = blob_sha(raw)
            except (ValueError, TypeError, KeyError):
                continue
            if sym in matches and (matches[sym]["provider"] != data["provider"] or
                                   matches[sym]["daily"] != data["daily"]):
                ambiguous.add(sym)
            else:
                matches[sym] = data
    return {k: v for k, v in matches.items() if k not in ambiguous}


def fetch_completed_history(sym, dates):
    """Reuse upstream exact unadjusted quote and amount checks, without its close-only Tencent gate."""
    code = sym[2:]
    quotes = frozen.actual_quotes(code, dates)
    if dates[-1] not in quotes:
        raise ValueError("HISTORY_LAST_CLOSE_MISSING")
    params = {"secid": ("1." if sym.startswith("sh") else "0.") + code,
              "fields1": "f1,f2,f3,f7", "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63",
              "klt": 101, "lmt": 21, "end": dates[-1].replace("-", ""),
              "ut": "b2884a393a59ad64002292a3e90d46a5"}
    url = frozen.EM + "?" + urlencode(params)
    txt, received = probe.get(url, referer="https://data.eastmoney.com/")
    body = json.loads(txt)
    data = body.get("data") or {}
    if body.get("rc") != 0 or str(data.get("code")) != code or data.get("market") != int(params["secid"][0]):
        raise ValueError("HISTORY_SECURITY_MISMATCH")
    raw = [s.split(",") for s in data.get("klines", [])]
    all_dates = [r[0] for r in raw]
    if all_dates != sorted(set(all_dates)) or any(d > received.date().isoformat() for d in all_dates):
        raise ValueError("HISTORY_DATE_ORDER")
    # A provider may include today's incomplete bar. Never use it in completed history.
    mapping = {}
    for r in raw:
        day = r[0]
        if day not in dates or day not in quotes:
            continue
        if len(r) != 13:
            raise ValueError("HISTORY_COLUMNS")
        net, small, mid, big, xl, pct, sp, mp, bp, xp, close, change = map(frozen.numeric, r[1:])
        amount = quotes[day]["amount"]
        if not (amount > 0 and abs(net-big-xl) <= 1 and
                abs(net+small+mid) <= max(64, amount*1e-7) and
                abs(pct-net/amount*100) <= .0051 and abs(close-quotes[day]["close"]) < .005):
            continue
        mapping[day] = {"date": day, "main_net_cny": net, "amount_cny": amount,
                        "big_net_cny": big, "super_net_cny": xl}
    rows = []
    for day in reversed(dates):
        if day not in mapping:
            break
        rows.insert(0, mapping[day])
    return checked_history({"code": code, "provider": "eastmoney", "trade_date": dates[-1],
                            "queried_at": received.isoformat(), "daily": rows,
                            "sources": [url]}, sym, dates, "COMPLETED_SESSION_FETCH")


def previous_snapshot(root):
    try:
        row = load(root / "research/intraday_focus_snapshot.json")
        if (row.get("schema_version") != 2 or row.get("mode") != "SHADOW"
                or row.get("result_kind") != "a_share_intraday_focus_shadow"
                or not row.get("run_id") or not isinstance(row.get("stocks"), dict)):
            return {}
        day = dt.date.fromisoformat(row["trade_date"])
        slot = dt.datetime.fromisoformat(row["slot"])
        started = dt.datetime.fromisoformat(row["started_at"])
        finished = dt.datetime.fromisoformat(row["finished_at"])
        if (slot.date() != day or slot.strftime("%H:%M") not in ("09:37", "10:37", "13:17", "14:27")
                or not 0 <= (started-slot).total_seconds() <= 150
                or not 0 <= (finished-started).total_seconds() <= 240):
            return {}
        return row
    except (OSError, ValueError, TypeError, KeyError):
        return {}


def cached_history(previous, sym, dates, today):
    # Cache only an earlier published result of the same session, not yesterday's stale window.
    if previous.get("trade_date") != today or previous.get("expected_baseline_date") != dates[-1]:
        return None
    try:
        row = previous["stocks"][sym]["historical_fund_flow"]["data"]
        # A frozen admission must be rechecked against the current formal pair instead.
        if row.get("source_kind") != "COMPLETED_SESSION_FETCH":
            return None
        return checked_history(row, sym, dates, "COMPLETED_SESSION_FETCH")
    except (ValueError, TypeError, KeyError):
        return None


def resolve_history(sym, dates, today, frozen_rows, previous):
    existing = frozen_rows.get(sym)
    cached = cached_history(previous, sym, dates, today)
    candidates = [r for r in (existing, cached) if r]
    for row in candidates:
        if row["coverage"] == "COMPLETE":
            return row
    try:
        fetched = fetch_completed_history(sym, dates)
        candidates.append(fetched)
    except Exception:
        # Preserve only previously validated data; never synthesize missing days or mix sources.
        if not candidates:
            raise ValueError("HISTORY_SOURCE_UNAVAILABLE") from None
    return max(candidates, key=lambda row: len(row["daily"]))


RESEARCH_STAGES = {"STARTING", "CONTINUING", "ACCELERATING", "DIVERGING", "REPAIRING", "WEAKENING", "INVALIDATED", "UNRESOLVED"}
RESEARCH_UPDATES = {"CONFIRMED", "REVISED", "FALSIFIED", "UNRESOLVED"}
RESEARCH_FLAGS = {"STRUCTURE_INTACT", "STRUCTURE_BREAK", "BREAKOUT", "PULLBACK", "FAILED_BREAKOUT",
                  "VOLUME_SUPPORT", "VOLUME_CONFLICT", "FUND_SUPPORT", "FUND_CONFLICT",
                  "BOARD_SUPPORT", "BOARD_CONFLICT", "MARKET_SUPPORT", "MARKET_CONFLICT", "DATA_LIMITED"}


def checked_research(record, day):
    """Read only a whitelisted, non-personal market hypothesis from the existing archive."""
    if not isinstance(record, dict):
        return None
    keys = {"basis", "source_run_id", "slot", "scan_at", "trend_stage", "hypothesis_update", "flags"}
    if set(record) != keys or record.get("basis") != "AI_MARKET_HYPOTHESIS_NOT_FACT":
        return None
    try:
        slot = dt.datetime.fromisoformat(record["slot"])
        scan = dt.datetime.fromisoformat(record["scan_at"])
        if (slot.date().isoformat() != day or scan.date().isoformat() != day
                or slot.tzinfo is None or scan.tzinfo is None
                or slot.strftime("%H:%M") not in ("09:37", "10:37", "13:17", "14:27")
                or not 0 <= (scan-slot).total_seconds() <= 300):
            return None
        if not isinstance(record["source_run_id"], str) or not record["source_run_id"]:
            return None
        if record["trend_stage"] not in RESEARCH_STAGES or record["hypothesis_update"] not in RESEARCH_UPDATES:
            return None
        flags = record["flags"]
        if not isinstance(flags, list) or len(flags) != len(set(flags)) or not set(flags) <= RESEARCH_FLAGS:
            return None
    except (ValueError, TypeError, KeyError):
        return None
    return {k: record[k] for k in sorted(keys)}


def archive_context(root, previous, today, symbols):
    """Reuse the existing archive; never expose role, size, cost or private actions."""
    path = root / "research/intraday_crossday_archive.json"
    empty = {sym: [] for sym in symbols}
    try:
        archive = load(path)
        if (archive.get("schema_version") != 1 or archive.get("result_kind") != "a_share_intraday_crossday_archive"
                or not isinstance(archive.get("days"), list)):
            raise ValueError("ARCHIVE_SCHEMA")
        for d in archive["days"]:
            if not isinstance(d, dict) or not isinstance(d.get("trade_date"), str):
                raise ValueError("ARCHIVE_ROWS")
            if dt.date.fromisoformat(d["trade_date"]).isoformat() != d["trade_date"] or d["trade_date"] > today:
                raise ValueError("ARCHIVE_DATE")
            if any(not isinstance(d.get(k, {}), dict) for k in ("trends", "stocks", "focus_stocks", "focus_research")):
                raise ValueError("ARCHIVE_ROW_SCHEMA")
        days = {d["trade_date"]: d for d in archive["days"]}
        if len(days) != len(archive["days"]):
            raise ValueError("ARCHIVE_DUPLICATE_DATE")
    except (OSError, ValueError, TypeError, KeyError):
        return None, empty, "ARCHIVE_UNAVAILABLE"
    old_day = previous.get("trade_date", "")
    # Save the most recent valid scan per code per day, including earlier same-day
    # scans, so a later failed quote does not erase the last valid observation.
    if old_day and old_day <= today:
        observations = {}
        for sym, row in previous.get("stocks", {}).items():
            if not isinstance(row, dict) or row.get("core_gate") != "CORE_VALID":
                continue
            c = row.get("components") or {}
            quote = next((c.get(k, {}).get("data", {}) for k in ("tencent_quote", "sina_quote")
                          if c.get(k, {}).get("data", {}).get("quality") == "LIVE"), None)
            if not quote or quote.get("symbol") != sym or str(quote.get("quote_at", ""))[:10] != old_day:
                continue
            try:
                price, change = frozen.numeric(quote["price"]), frozen.numeric(quote["change_pct"])
                stamp = dt.datetime.fromisoformat(quote["quote_at"])
                slot = dt.datetime.fromisoformat(previous["slot"])
                if price <= 0 or not -2 <= (stamp-slot).total_seconds() <= 240:
                    continue
                ratio = row.get("metrics", {}).get("same_time_volume_ratio")
                ratio = frozen.numeric(ratio) if ratio is not None else None
                if ratio is not None and ratio <= 0:
                    ratio = None
            except (ValueError, TypeError, KeyError):
                continue
            observations[sym[2:]] = {"observed_at": quote["quote_at"], "price": price,
                                     "change_pct": change, "source_run_id": previous["run_id"],
                                     "slot": previous["slot"], "same_time_volume_ratio": ratio,
                                     "basis": "LAST_VALID_FOCUS_SCAN_NOT_OFFICIAL_CLOSE"}
        if observations:
            entry = days.setdefault(old_day, {"trade_date": old_day, "trends": {}, "stocks": {}})
            focus = entry.setdefault("focus_stocks", {})
            for code, obs in observations.items():
                existing = focus.get(code)
                if not isinstance(existing, dict) or obs["observed_at"] > str(existing.get("observed_at", "")):
                    focus[code] = obs
    ordered = [days[d] for d in sorted(days)[-ARCHIVE_LIMIT:]]
    archive = {**archive, "days": ordered}
    # Today is retained in the archive but NEVER treated as cross-day evidence.
    completed = [d for d in ordered if d["trade_date"] < today][-RESEARCH_LIMIT:]
    context = {}
    for sym in symbols:
        code = sym[2:]
        records = []
        for day in completed:
            focus = (day.get("focus_stocks") or {}).get(code)
            legacy = (day.get("stocks") or {}).get(code)
            research = checked_research((day.get("focus_research") or {}).get(code), day["trade_date"])
            if isinstance(focus, dict) and focus.get("basis") != "LAST_VALID_FOCUS_SCAN_NOT_OFFICIAL_CLOSE":
                focus = None
            # Public market observations and model hypotheses are different evidence types.
            if isinstance(focus, dict) or isinstance(legacy, dict) or research:
                records.append({"trade_date": day["trade_date"],
                                "focus_observation": focus if isinstance(focus, dict) else None,
                                "focus_research": research,
                                "legacy_research": ({k: legacy.get(k) for k in ("scan_at", "relative_strength", "price_behavior")}
                                                    if isinstance(legacy, dict) else None)})
        context[sym] = records
    return archive, context, "AVAILABLE" if any(context.values()) else "NO_MATCHING_HISTORY"
