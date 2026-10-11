"""Public, portfolio-agnostic intraday quote index.

The repository is public. NEVER persist Airtable holdings, costs, user codes or
the user's position membership here. Publish only full-market quotation shards.
The monitor selects a matching shard *after* privately reading Airtable.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

QUOTE_DIR = Path(__file__).resolve().parents[1] / "research" / "intraday_quote_shards"
CODE_RE = re.compile(r"^[0-9]{6}$")
KEEP_SAMPLES = 3


def compact_quote(quote: dict) -> dict:
    return {k: quote.get(k) for k in (
        "name", "price", "prev_close", "change_pct", "quote_time",
        "confidence", "warnings", "primary_source",
    )}


def build_public_quote_index(sina: dict, tencent: dict, trade_date: str,
                             captured_at: str, choose_quote, dest: Path = QUOTE_DIR):
    """Return a public manifest and byte-identical shard payloads. No writes yet."""
    codes = sorted(c for c in set(sina) | set(tencent) if CODE_RE.fullmatch(c))
    groups: dict[str, dict] = {}
    valid_count = 0
    for code in codes:
        row = compact_quote(choose_quote(code, sina, tencent, trade_date))
        if row["confidence"] in ("high", "medium") and row["price"] is not None:
            valid_count += 1
        prefix = code[:2]
        groups.setdefault(prefix, {})[code] = row

    # Reuse only the two preceding *same-day* public quotations, never old-day
    # positions or external holdings. This supports risk hysteresis without
    # creating a portfolio history in a public repository.
    shards: dict[str, str] = {}
    manifest: dict[str, dict] = {}
    for prefix, rows in sorted(groups.items()):
        path = dest / (prefix + ".json")
        old = {}
        try:
            prev = json.loads(path.read_text(encoding="utf-8"))
            if prev.get("trade_date") == trade_date:
                old = prev.get("quotes") if isinstance(prev.get("quotes"), dict) else {}
        except (FileNotFoundError, ValueError, OSError, TypeError):
            pass
        for code, row in rows.items():
            prev_samples = (old.get(code) or {}).get("samples") or []
            if not isinstance(prev_samples, list):
                prev_samples = []
            samples = [
                p for p in prev_samples
                if isinstance(p, dict) and p.get("captured_at") != captured_at
                and p.get("trade_date") == trade_date
            ][-(KEEP_SAMPLES - 1):]
            if row["price"] is not None and row["confidence"] in ("high", "medium"):
                samples.append({
                    "trade_date": trade_date,
                    "captured_at": captured_at,
                    "price": row["price"],
                    "change_pct": row["change_pct"],
                })
            row["samples"] = samples[-KEEP_SAMPLES:]
        document = {
            "schema_version": 1,
            "result_kind": "a_share_full_market_quote_shard",
            "trade_date": trade_date,
            "captured_at": captured_at,
            "prefix": prefix,
            "quotes": rows,
        }
        content = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        relative = "research/intraday_quote_shards/" + prefix + ".json"
        shards[relative] = content
        manifest[prefix] = {
            "path": relative,
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "quote_count": len(rows),
        }
    status = "available" if valid_count >= 500 and trade_date else "partial"
    return {
        "schema_version": 1,
        "kind": "public_full_market_quotes_not_portfolio",
        "status": status,
        "trade_date": trade_date,
        "captured_at": captured_at,
        "quote_count": len(codes),
        "usable_quote_count": valid_count,
        "shards": manifest,
    }, shards
