from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
LATEST = DATA / "latest.json"
HISTORY = DATA / "history_shards"
OUTPUT = DATA / "corporate_action_watch.json"
TZ = ZoneInfo("Asia/Shanghai")
THRESHOLD = 0.005
MIN_FACTOR = 0.2
MAX_FACTOR = 5.0


def fnum(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def scale_row(row: dict, factor: float) -> None:
    for key in ("open", "high", "low", "close", "prev_close"):
        value = fnum(row.get(key))
        if value is not None:
            row[key] = round(value * factor, 6)


def scale_summary(summary: dict, factor: float) -> None:
    for key in ("high_52w", "low_52w"):
        value = fnum(summary.get(key))
        if value is not None:
            summary[key] = round(value * factor, 6)


def main() -> int:
    if not LATEST.exists():
        raise SystemExit("data/latest.json missing")
    latest = json.loads(LATEST.read_text(encoding="utf-8"))
    quotes = latest.get("stocks") or {}
    trade_date = latest.get("trade_date")
    events = []
    changed_files = 0

    for path in sorted(HISTORY.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for code, item in (payload.get("stocks") or {}).items():
            quote = quotes.get(code) or {}
            reference = fnum(quote.get("prev_close"))
            rows = item.get("history") or []
            if reference is None or not rows:
                continue
            previous_close = fnum(rows[-1].get("close"))
            if previous_close is None or previous_close <= 0:
                continue
            factor = reference / previous_close
            if abs(factor - 1.0) < THRESHOLD:
                continue
            if not (MIN_FACTOR <= factor <= MAX_FACTOR):
                events.append({
                    "code": code,
                    "status": "blocked_extreme_reference_mismatch",
                    "previous_close": previous_close,
                    "reference_prev_close": reference,
                    "factor": factor,
                })
                continue

            for row in rows:
                scale_row(row, factor)
            scale_summary(item.get("long_term_summary") or {}, factor)
            item["last_corporate_action_adjustment"] = {
                "trade_date": trade_date,
                "factor": round(factor, 10),
                "detected_by": "provider_prev_close_vs_stored_close",
            }
            basis = str(item.get("history_basis") or "live_close_only")
            if "reference_adjusted" not in basis:
                item["history_basis"] = basis + "+reference_adjusted"
            changed = True
            events.append({
                "code": code,
                "status": "history_rebased",
                "previous_close": previous_close,
                "reference_prev_close": reference,
                "factor": round(factor, 10),
            })

        if changed:
            path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            changed_files += 1

    result = {
        "schema_version": 1,
        "generated_at": datetime.now(TZ).isoformat(),
        "trade_date": trade_date,
        "method": "compare current provider prev_close with stored prior close; rebase old OHLC when mismatch >= 0.5%",
        "adjustments": sum(1 for x in events if x["status"] == "history_rebased"),
        "blocked": sum(1 for x in events if x["status"].startswith("blocked")),
        "changed_history_shards": changed_files,
        "events": events,
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("trade_date", "adjustments", "blocked", "changed_history_shards")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
