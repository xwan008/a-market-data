#!/usr/bin/env python3
"""Shadow-only supplemental quotes for a provider-verified full concept.

Do not edit the official main-board quote pipeline. Fetch raw Sina / Tencent
snapshots, count newly observed GEM/STAR/BSE code coverage and only accept
source quotes carrying the requested completed-session date.
"""
import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import easyquotation
from fetch_market_resilient import normalize_easyquotation_timestamp
from fetch_market import normalize_code, normalize_quote_date

SIX = re.compile(r"^\d{6}$")
SH = ZoneInfo("Asia/Shanghai")
TARGET_PREFIXES = ("sh", "sz", "bj")


def segment(c):
    if c.startswith(("300", "301", "302")): return "GEM"
    if c.startswith(("688", "689")): return "STAR"
    if c.startswith(("8", "9", "4")): return "BSE_OR_OTHER"
    if c.startswith(("600", "601", "603", "605", "000", "001", "002", "003")): return "MAIN"
    return "OTHER"


def valid_row(symbol, raw, trade_date):
    original = str(symbol).strip().lower()
    if not original.startswith(TARGET_PREFIXES):
        return None
    code = normalize_code(original)
    if not SIX.fullmatch(code):
        return None
    quote_date, time = normalize_easyquotation_timestamp(raw)
    if normalize_quote_date(quote_date) != trade_date:
        return None
    try:
        price, previous = float(raw.get("now")), float(raw.get("close"))
    except (ValueError, TypeError):
        return None
    if price <= 0 or previous <= 0:
        return None
    return (code, {
        "name": str(raw.get("name") or ""),
        "price": price, "prev_close": previous,
        "change_pct": round((price / previous - 1) * 100, 5),
        "date": trade_date,
        "time": str(time or ""),
        "confidence": "medium"
    })


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--concept-file", required=True)
    p.add_argument("--frozen-latest", default="data/latest.json")
    p.add_argument("--output", required=True)
    a = p.parse_args()
    concept = json.loads(Path(a.concept_file).read_text())
    latest = json.loads(Path(a.frozen_latest).read_text())
    day = latest["trade_date"]
    if (latest.get("market_status") != "closed"
        or day != concept.get("as_of_trade_date")
        or datetime.now(SH).date().isoformat() != day):
        raise ValueError("SUPPLEMENT_NOT_SAME_COMPLETED_SESSION")
    members = {str(c).zfill(6) for r in concept["concepts"] for c in r["member_codes"]}
    old = set(latest["stocks"])
    missing = members - old
    print("MISSING_BEFORE",len(missing), dict(Counter(segment(c) for c in missing)),flush=True)
    candidates = {}
    sources = {}
    for provider in ("tencent","sina"):
        try:
            raw = easyquotation.use(provider).market_snapshot(prefix=True)
            normalized = {}
            by_segments = Counter()
            for symbol, quote in raw.items():
                resolved = valid_row(symbol, quote, day)
                if not resolved:
                    continue
                code, row = resolved
                by_segments[segment(code)] += 1
                if code in missing:
                    normalized[code] = row
            sources[provider] = {
                "status":"OK", "raw_count":len(raw),
                "same_day_verified_count":sum(by_segments.values()),
                "same_day_by_segment":dict(by_segments),
                "matched_missing":len(normalized)}
            for code, row in normalized.items():
                if code not in candidates:
                    candidates[code] = {**row, "provider":provider}
                else:
                    oldrow = candidates[code]
                    deviation = abs(row["price"]-oldrow["price"])/oldrow["price"]
                    if deviation > .015:
                        oldrow["confidence"] = "invalid"
                        oldrow["disagreement_pct"] = round(deviation*100,4)
                    else:
                        oldrow["confidence"] = "high"
                        oldrow["other_provider"] = provider
        except Exception as e:
            sources[provider] = {"status":"FAIL","error":type(e).__name__}
        print("SUPPLEMENT_SOURCE",provider,json.dumps(sources[provider],ensure_ascii=False),flush=True)
    stocks = {code: row for code,row in candidates.items()
              if row["confidence"] in ("medium","high")}
    output = {
        "schema_version":1,
        "result_kind":"concept_quote_supplement",
        "trade_date":day, "market_status":"closed",
        "as_of_data_role":"SHADOW_CONCEPT_ONLY_NOT_FORMAL_HISTORY",
        "sources":sources,
        "member_count":len(members), "frozen_member_count":len(members&old),
        "missing_in_frozen_market":len(missing),
        "missing_by_segment":dict(Counter(segment(c) for c in missing)),
        "supplement_count":len(stocks),
        "remaining_missing_count":len(missing-set(stocks)),
        "remaining_by_segment":dict(Counter(segment(c) for c in (missing-set(stocks)))),
        "stocks":stocks
    }
    dest=Path(a.output)
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n")
    print("SUPPLEMENT_VERDICT",json.dumps({
        "members":len(members),"missing_base":len(missing),
        "recovered":len(stocks),"still_missing":len(missing-set(stocks)),
        "overall_coverage":round((len(members&old)+len(stocks))/len(members),4)
    },ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
