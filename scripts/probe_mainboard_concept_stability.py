#!/usr/bin/env python3
"""Verify live THS index constituents with three independent adata queries.

Only validates today's retrieved membership, not a historical-date snapshot.
No production files are changed. Market scope is explicitly SH/SZ main board.
"""
from __future__ import annotations

import hashlib
import json
import re
import signal
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

INDEX = "886069"
CONCEPT = "人形机器人"
SYMBOL = re.compile(r"^\d{6}$")
PREFIX = ("600", "601", "603", "605", "000", "001", "002", "003")
TZ = ZoneInfo("Asia/Shanghai")


def get_expected_count():
    uri = f"https://d.10jqka.com.cn/v2/blockrank/{INDEX}/8/d15.js"
    res = requests.get(uri, timeout=15, headers={
        "User-Agent": "Mozilla/5.0", "Referer": "https://q.10jqka.com.cn/"})
    res.raise_for_status()
    raw = res.text
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError("THS_COUNT_NON_JSON")
    return int(json.loads(raw[start:end + 1])["block"]["subcodeCount"])


def read_constituents():
    import adata

    def timeout_handler(*_):
        raise TimeoutError("THS_CONSTITUENTS_TIMEOUT")
    previous = signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(55)
    try:
        frame = adata.stock.info.concept_constituent_ths(index_code=INDEX)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
    if "stock_code" not in frame:
        raise ValueError("THS_STOCK_CODE_FIELD_MISSING")
    codes = [str(v).strip().zfill(6) for v in frame["stock_code"]]
    if not codes or any(not SYMBOL.fullmatch(v) for v in codes):
        raise ValueError("THS_MEMBER_CODES_INVALID")
    if len(codes) != len(set(codes)):
        raise ValueError("THS_MEMBER_CODES_DUPLICATE")
    return sorted(codes)


def main():
    now = datetime.now(TZ)
    if now.date().isoformat() != "2026-10-26":
        raise ValueError("LIVE_MEMBERSHIP_CANNOT_BACKDATE_HISTORICAL_DAY")
    trials = []
    snapshots = []
    for n in range(1, 4):
        expected = get_expected_count()
        members = read_constituents()
        if len(members) != expected:
            raise ValueError(f"THS_CONSTITUENT_PAGINATION_OR_COUNT_MISMATCH:{len(members)}/{expected}")
        main = [x for x in members if x.startswith(PREFIX)]
        digest = hashlib.sha256(",".join(members).encode()).hexdigest()
        trial = {"attempt": n, "provider_total": expected, "actual_total": len(members),
                 "mainboard_count": len(main), "membership_sha256": digest}
        trials.append(trial)
        snapshots.append(members)
        print("STABILITY_TRIAL", json.dumps(trial), flush=True)
    if len({x["membership_sha256"] for x in trials}) != 1:
        raise ValueError("CONCEPT_CONSTITUENT_CHANGED_BETWEEN_REPEAT_QUERIES")
    market = json.loads(Path("data/latest.json").read_text())
    if market.get("trade_date") != "2026-10-26" or market.get("market_status") != "closed":
        raise ValueError("MARKET_NOT_FROZEN_COMPLETED_DAY")
    quotes = market.get("stocks") or {}
    mainboard = [x for x in snapshots[0] if x.startswith(PREFIX)]
    usable = [x for x in mainboard if (quotes.get(x) or {}).get("confidence") in ("high", "medium")]
    report = {
        "status": "STABLE_WITHIN_ONE_TRADING_DAY",
        "market_scope": "SH_SZ_MAINBOARD_ONLY",
        "provider": "THS_ADATA",
        "source_captured_at": datetime.now(TZ).isoformat(),
        "concept_name": CONCEPT, "concept_index_code": INDEX,
        "trade_date": "2026-10-26",
        "membership_date_semantics": "LIVE_SNAPSHOT_NOT_HISTORICAL_QUERY",
        "trials": trials,
        "full_concept_count": len(snapshots[0]),
        "mainboard_concept_count": len(mainboard),
        "mainboard_quotes_valid": len(usable),
        "mainboard_quote_coverage": round(len(usable)/len(mainboard), 4),
        "full_member_codes": snapshots[0],
        "mainboard_member_codes": mainboard,
        "index_code_mapping": "PREVIOUSLY_RESEARCHED_INDEX_CODE_NOT_AUTOMATIC",
    }
    Path("/tmp/mainboard_ths_stability_20261026.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("STABILITY_VERDICT",json.dumps(
        {k:v for k,v in report.items() if k not in ("full_member_codes","mainboard_member_codes","trials")},
        ensure_ascii=False),flush=True)


if __name__ == "__main__":
    main()
