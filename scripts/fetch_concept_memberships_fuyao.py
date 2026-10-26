#!/usr/bin/env python3
"""Optional authenticated concept membership provider with code-first mapping.

FuyAO/同花顺 financial data API is a third-party authenticated provider. Its
documented catalog is full (no pagination), and its constituency endpoint is
current-only. This adapter refuses to backdate current membership.
No production job depends on this adapter until credentials and quotas work.
"""
import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from route_hotspot_themes import name_strength

BASE = "https://fuyao.aicubes.cn"
INDEX_RE = re.compile(r"^\d{6}\.TI$")
CODE_RE = re.compile(r"^\d{6}$")
SH = ZoneInfo("Asia/Shanghai")


def request_json(session, path, params, key):
    r = session.get(
        BASE + path, params=params,
        headers={"X-api-key": key, "Accept":"application/json"}, timeout=18)
    r.raise_for_status()
    parsed = r.json()
    if parsed.get("code") != 0 or not isinstance(parsed.get("data"), dict):
        raise ValueError("AUTHENTICATED_PROVIDER_RESPONSE_NOT_SUCCESS")
    return parsed["data"]


def extract_members(payload):
    items = payload.get("item")
    if not isinstance(items, list) or not items:
        raise ValueError("EMPTY_OR_MALFORMED_CONSTITUENTS")
    codes = []
    for row in items:
        if not isinstance(row,dict):
            raise ValueError("INVALID_MEMBER_ROW")
        c = str(row.get("ticker") or str(row.get("thscode") or "").split(".")[0])
        if not CODE_RE.fullmatch(c):
            raise ValueError("INVALID_MEMBER_CODE")
        codes.append(c)
    if len(codes) != len(set(codes)):
        raise ValueError("DUPLICATE_MEMBERS_IN_PROVIDER")
    return sorted(codes)


def date_from_timestamp(payload):
    millis=payload.get("timestamp")
    if not isinstance(millis, (int,float)):
        raise ValueError("PROVIDER_TIMESTAMP_MISSING")
    return datetime.fromtimestamp(millis/1000, SH).date().isoformat()


def build(handoff, key, session=None):
    session = session or requests.Session()
    asof = handoff.get("trade_date")
    if datetime.now(SH).date().isoformat() != asof:
        raise ValueError("CURRENT_PROVIDER_CANNOT_REPLAY_HISTORICAL_MEMBERSHIP")
    listing = request_json(session, "/api/a-share-index/catalog/ths-index-list",
                           {"tag":"cn_concept"}, key)
    if date_from_timestamp(listing) != asof:
        raise ValueError("PROVIDER_CATALOG_NOT_CURRENT_SESSION")
    items = listing.get("item")
    if not isinstance(items,list) or len(items)<100:
        raise ValueError("INCOMPLETE_CONCEPT_CATALOG")
    all_codes = set()
    picked = []
    for item in items:
        code = str(item.get("thscode") or "")
        name = str(item.get("name") or "").strip()
        if not INDEX_RE.fullmatch(code) or not name or code in all_codes:
            raise ValueError("INVALID_CATALOG_INDEX")
        all_codes.add(code)
        if any(name_strength(sig.get("trend_name"),name)>=2
               for sig in handoff.get("signals") or []):
            picked.append((code,name))
    if not picked or len(picked)>30:
        raise ValueError("NO_CONCEPT_MATCH_OR_TOO_MANY_MATCHES")
    out=[]
    for code,name in sorted(picked):
        result = request_json(session,"/api/a-share-index/constituents/ths-stock-list",
                              {"thscode":code},key)
        if date_from_timestamp(result)!=asof:
            raise ValueError("PROVIDER_MEMBERSHIP_NOT_CURRENT_SESSION")
        out.append({"concept_id":code,"name":name,
                    "member_codes":extract_members(result),"source":"THS_FUYAO"})
    return {"schema_version":1,"source":"THS_FUYAO","as_of_trade_date":asof,
            "catalog_scope":"MATCHED_HOTSPOT_CONCEPTS_COMPLETE",
            "concepts":out,
            "source_note":"Current members captured on as-of trade day; not historical query."}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--handoff",default="research/trend_handoff.json")
    p.add_argument("--out",required=True)
    args=p.parse_args()
    key=os.environ.get("FUYAO_API_KEY")
    if not key:
        raise SystemExit("FUYAO_API_KEY_NOT_CONFIGURED: no request issued")
    result=build(json.loads(Path(args.handoff).read_text()),key)
    path=Path(args.out)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print("FULL_CONCEPT_CATALOG_MATCHED",[(x["concept_id"],x["name"],len(x["member_codes"]))
                                          for x in result["concepts"]])


if __name__=="__main__":
    main()
