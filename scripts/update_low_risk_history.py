"""Post-publication history for low-risk signal episodes. Never feeds fresh screening."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REASONS = {"WAIT_PRICE", "WAIT_MARGIN", "WAIT_EXPECTATION", "WAIT_CATALYST"}
CATEGORIES = ("hard_filtered_out", "pre_screened_out", "early_evidence", "uncertain", "drop")


def blob_sha(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def identity(item: dict) -> str:
    return "|".join(str(item.get(k) or "") for k in ("code", "trend_name", "industry_code"))


def view(item: dict) -> dict:
    return {k: item.get(k) for k in (
        "rank", "status", "wait_reason", "current_price", "reasonable_buy_range",
        "low_risk_buy_range", "wait_or_trigger_condition", "invalidation"
    )}


def validate(formal: dict, handoff: dict, formal_sha: str) -> list[dict]:
    if formal.get("status") != "COMPLETE" or formal.get("result_kind") != "a_share_low_risk_formal_result":
        raise ValueError("FORMAL_INCOMPLETE")
    if handoff.get("status") != "COMPLETE" or handoff.get("source_run_id") != formal.get("run_id"):
        raise ValueError("HANDOFF_RUN_MISMATCH")
    if not formal.get("run_id") or formal.get("trade_date") != handoff.get("trade_date"):
        raise ValueError("HANDOFF_DATE_MISMATCH")
    if handoff.get("source_formal_blob_sha") != formal_sha:
        raise ValueError("FORMAL_SHA_MISMATCH")
    expected = sorted(formal.get("ready", []) + formal.get("wait", []), key=lambda x: x["rank"])
    actual = handoff.get("items")
    if not isinstance(actual, list) or len(actual) != len(expected):
        raise ValueError("HANDOFF_COVERAGE_MISMATCH")
    seen = set()
    for a, b in zip(actual, expected):
        if (not isinstance(a, dict) or a.get("code") in seen or a.get("status") not in ("READY", "WAIT")
                or (a.get("status") == "READY" and a.get("wait_reason") is not None)
                or (a.get("status") == "WAIT" and a.get("wait_reason") not in REASONS)):
            raise ValueError("HANDOFF_INVALID_ITEM")
        seen.add(a["code"])
        for key in ("code", "company_name", "rank", "status", "wait_reason", "trend_name", "industry_code"):
            if a.get(key) != b.get(key):
                raise ValueError("HANDOFF_IDENTITY_MISMATCH:" + key)
        for x, y in (("reasonable_buy_range", "reasonable_price_range"),
                     ("low_risk_buy_range", "low_risk_buy_range")):
            if a.get(x) != b.get(y):
                raise ValueError("HANDOFF_PRICE_MISMATCH:" + x)
        for x, y in (("current_price", "current_price"),
                     ("wait_or_trigger_condition", "reentry_trigger"),
                     ("invalidation", "invalidation"), ("industry_name", "industry_name")):
            if a.get(x) != b.get(y):
                raise ValueError("HANDOFF_FIELD_MISMATCH:" + x)
    return actual


def reason_for_absence(record: dict, formal: dict, new_items: list[dict]) -> tuple[str, str | None]:
    if any(x["code"] == record["code"] for x in new_items):
        return "ROUTE_CHANGED", None
    signals = (formal.get("trend_handoff") or {}).get("signals") or []
    if not any(s.get("trend_name") == record["trend_name"] and
               record["industry_code"] in s.get("industry_codes", []) for s in signals):
        return "OUT_OF_CURRENT_TREND_HANDOFF", None
    for category in CATEGORIES:
        for item in formal.get(category, []) or []:
            if item.get("code") == record["code"] and item.get("industry_code") == record["industry_code"]:
                if item.get("trend_name") and item["trend_name"] != record["trend_name"]:
                    continue
                return category.upper(), item.get("reason")
    return "NOT_SELECTED_THIS_RUN", None


def observation(record: dict, trade_date: str, history_dir: Path | None,
                cache: dict[str, dict]) -> dict:
    result = {"trade_date": trade_date, "status": "UNAVAILABLE", "close": None,
              "qfq_return_since_first_seen_pct": None, "history_basis": None}
    if history_dir is None:
        return result
    code = record["code"]
    prefix = code[:4]
    if prefix not in cache:
        p = history_dir / (prefix + ".json")
        cache[prefix] = load(p).get("stocks", {}) if p.exists() else {}
    stock = cache[prefix].get(code) or {}
    rows = {str(r.get("date")): r for r in stock.get("history", []) if isinstance(r, dict)}
    today, start = rows.get(trade_date), rows.get(record["first_seen_trade_date"])
    if not today or today.get("confidence") not in ("high", "medium"):
        return result
    try:
        last_close = float(today["close"])
        if last_close <= 0:
            return result
    except (TypeError, ValueError, KeyError):
        return result
    result.update(status="AVAILABLE", close=last_close, history_basis=stock.get("history_basis"))
    if str(stock.get("history_basis") or "").startswith("tencent_qfq") and start and start.get("confidence") in ("high", "medium"):
        try:
            baseline = float(start["close"])
            if baseline > 0:
                result["qfq_return_since_first_seen_pct"] = round((last_close / baseline - 1) * 100, 4)
        except (TypeError, ValueError, KeyError):
            pass
    return result


def build(formal: dict, handoff: dict, sha: str, previous: dict | None = None,
          history_dir: Path | None = None) -> tuple[dict, dict]:
    items = validate(formal, handoff, sha)
    date, run = formal["trade_date"], formal["run_id"]
    if previous and previous["as_of_trade_date"] >= date:
        raise ValueError("HISTORY_DATE_NOT_ADVANCING")
    records = copy.deepcopy((previous or {}).get("records", []))
    events, cache = [], {}
    matched = {identity(i): i for i in items}
    if len(matched) != len(items):
        raise ValueError("DUPLICATE_SIGNAL_IDENTITY")
    consumed = set()
    for record in records:
        key = identity(record)
        if record["lifecycle"] == "ACTIVE" and key in matched:
            item = matched[key]
            record["latest_snapshot"] = view(item)
            record["last_in_handoff_trade_date"] = date
            record["last_transition_reason"] = None
            record["lifecycle"] = "ACTIVE"
            consumed.add(key)
            action = "CONTINUED"
        elif record["lifecycle"] in ("ACTIVE", "PAUSED_OUT_OF_SCOPE"):
            reason, detail = reason_for_absence(record, formal, items)
            if reason == "OUT_OF_CURRENT_TREND_HANDOFF":
                record["lifecycle"] = "PAUSED_OUT_OF_SCOPE"
                record["out_of_scope_sessions"] = record.get("out_of_scope_sessions", 0) + 1
                if record["out_of_scope_sessions"] > 30:
                    record["lifecycle"] = "CLOSED"
                    reason = "OUT_OF_SCOPE_FOLLOWUP_EXPIRED"
            else:
                record["lifecycle"] = "CLOSED"
                record["post_exit_sessions"] = 0
            record["last_transition_reason"] = reason
            record["last_transition_detail"] = detail
            action = reason
        else:
            action = "ARCHIVED"
        record["last_review_trade_date"] = date
        if record["lifecycle"] == "CLOSED":
            record["post_exit_sessions"] = record.get("post_exit_sessions", 0) + (action == "ARCHIVED")
        if record["lifecycle"] != "CLOSED" or record.get("post_exit_sessions", 0) <= 30:
            record["last_market_observation"] = observation(record, date, history_dir, cache)
        events.append({"signal_id": record["signal_id"], "action": action,
                       "lifecycle": record["lifecycle"], "reason": record.get("last_transition_reason"),
                       "market_observation": record.get("last_market_observation")})
    for item in items:
        key = identity(item)
        if key in consumed:
            continue
        episode = 1 + max([r["episode"] for r in records if identity(r) == key] or [0])
        record = {"signal_id": f"{key}|{episode}", "episode": episode,
                  "code": item["code"], "company_name": item["company_name"],
                  "trend_name": item["trend_name"], "industry_code": item["industry_code"],
                  "industry_name": item.get("industry_name"), "lifecycle": "ACTIVE",
                  "first_seen_trade_date": date, "last_in_handoff_trade_date": date,
                  "last_review_trade_date": date, "initial_snapshot": view(item),
                  "latest_snapshot": view(item), "last_transition_reason": None,
                  "last_transition_detail": None, "out_of_scope_sessions": 0, "post_exit_sessions": 0}
        record["last_market_observation"] = observation(record, date, history_dir, cache)
        records.append(record)
        events.append({"signal_id": record["signal_id"], "action": "NEW",
                       "lifecycle": "ACTIVE", "reason": None,
                       "market_observation": record["last_market_observation"]})
    registry = {"schema_version": 1, "result_kind": "a_share_low_risk_signal_registry",
                "status": "BOOTSTRAP_PARTIAL" if previous is None else "COMPLETE",
                "history_start_trade_date": (previous or {}).get("history_start_trade_date", date),
                "as_of_trade_date": date, "as_of_run_id": run,
                "source_formal_blob_sha": sha, "records": records,
                "counts": {k: sum(r["lifecycle"] == k for r in records)
                           for k in ("ACTIVE", "PAUSED_OUT_OF_SCOPE", "CLOSED")}}
    snapshot = {"schema_version": 1, "result_kind": "a_share_low_risk_history_snapshot",
                "trade_date": date, "source_run_id": run, "source_formal_blob_sha": sha,
                "prior_registry": copy.deepcopy(previous), "events": events,
                "counts_after": registry["counts"]}
    return registry, snapshot


def update(root: Path) -> str:
    formal_path = root / "research/latest_formal_result.json"
    formal = load(formal_path)
    handoff = load(root / "research/low_risk_handoff.json")
    sha = blob_sha(formal_path.read_bytes())
    validate(formal, handoff, sha)  # Fail before touching history outputs.
    registry_path = root / "research/low_risk_signal_registry.json"
    previous = load(registry_path) if registry_path.exists() else None
    date = formal["trade_date"]
    snapshot_path = root / "research/low_risk_history" / (date + ".json")
    if previous and previous["as_of_trade_date"] == date:
        if not snapshot_path.exists():
            raise ValueError("SAME_DAY_SNAPSHOT_MISSING")
        prior_snapshot = load(snapshot_path)
        if (previous.get("as_of_run_id"), previous.get("source_formal_blob_sha")) == (formal["run_id"], sha):
            return "UNCHANGED"
        previous = prior_snapshot["prior_registry"]
        if previous and previous["as_of_trade_date"] >= date:
            raise ValueError("INVALID_SAME_DAY_BASELINE")
    elif snapshot_path.exists():
        raise ValueError("ORPHAN_SNAPSHOT_EXISTS")
    new, snapshot = build(formal, handoff, sha, previous, root / "data/history_shards")
    # Both files are staged in one Git commit, independently of formal/handoff.
    dump(snapshot_path, snapshot)
    dump(registry_path, new)
    return "UPDATED"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    print(update(args.root))
