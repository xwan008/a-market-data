"""Public, portfolio-agnostic intraday quote index.

The repository is public. NEVER persist Airtable holdings, costs, user codes or
the user's position membership here. Publish only full-market quotation shards.
The monitor selects a matching shard *after* privately reading Airtable.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

QUOTE_DIR = Path(__file__).resolve().parents[1] / "research" / "intraday_quote_shards"
CODE_RE = re.compile(r"^[0-9]{6}$")
KEEP_SAMPLES = 3


def compact_quote(quote: dict) -> dict:
    return {k: quote.get(k) for k in (
        "name", "price", "prev_close", "change_pct", "quote_time",
        "confidence", "warnings", "primary_source",
    )}


def verify_public_quote_for_held_code(snapshot: dict, code: str, raw: bytes) -> dict:
    """Verify a single public quote without importing any private position data.

    The caller must establish the user's real net holding *privately* first.
    SHA verification uses the exact raw bytes returned from the stored shard.
    """
    if not isinstance(code, str) or not CODE_RE.fullmatch(code):
        raise ValueError("PORTFOLIO_CODE_INVALID")
    index = snapshot.get("portfolio_quote_index") or {}
    prefix = code[:2]
    entry = (index.get("shards") or {}).get(prefix) or {}
    if not (
        index.get("schema_version") == 1
        and index.get("kind") == "public_full_market_quotes_not_portfolio"
        and index.get("status") == "available"
        and index.get("trade_date") == snapshot.get("trade_date")
        and index.get("captured_at") == snapshot.get("captured_at")
        and entry.get("path") == f"research/intraday_quote_shards/{prefix}.json"
        and hashlib.sha256(raw).hexdigest() == entry.get("sha256")
    ):
        raise ValueError("PORTFOLIO_QUOTE_INDEX_MISMATCH")
    try:
        shard = json.loads(raw.decode("utf-8"))
        row = shard["quotes"][code]
    except (ValueError, KeyError, TypeError, UnicodeDecodeError) as exc:
        raise ValueError("PORTFOLIO_QUOTE_NOT_FOUND") from exc
    if not (
        shard.get("schema_version") == 1
        and shard.get("result_kind") == "a_share_full_market_quote_shard"
        and shard.get("prefix") == prefix
        and shard.get("trade_date") == snapshot.get("trade_date")
        and shard.get("captured_at") == snapshot.get("captured_at")
        and len(shard["quotes"]) == entry.get("quote_count")
    ):
        raise ValueError("PORTFOLIO_QUOTE_SHARD_MISMATCH")
    try:
        capture_time = datetime.fromisoformat(snapshot["captured_at"])
        quote_time = datetime.fromisoformat(row["quote_time"])
        quote_is_fresh = (
            quote_time.tzinfo is not None
            and capture_time.tzinfo is not None
            and quote_time.date().isoformat() == snapshot["trade_date"]
            and -120 <= (capture_time - quote_time).total_seconds() <= 900
        )
        valid_price = float(row["price"]) > 0
    except (ValueError, TypeError, KeyError, OverflowError):
        quote_is_fresh = valid_price = False
    if row.get("confidence") not in {"high", "medium"} or not quote_is_fresh or not valid_price:
        raise ValueError("PORTFOLIO_QUOTE_UNAVAILABLE")
    return row


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
