#!/usr/bin/env python3
"""Real-provider experiment only. No formal trend writes or date forgery.

Probe adata THS concept listing and constituent membership, compare the full
index-code path against reported vendor total, and keep partial results clearly
separate from verified complete membership. This file is NOT a production adapter.
"""
from __future__ import annotations
import json
import os
import re
import signal
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SAMPLES = ("人形机器人", "固态电池", "商业航天")
CODE_RE = re.compile(r"^\d{6}$")


class SourceTimeout(Exception):
    pass


def within(seconds, action):
    def alarm(*_):
        raise SourceTimeout(f"call exceeded {seconds}s")
    previous = signal.signal(signal.SIGALRM, alarm)
    signal.alarm(seconds)
    try:
        return action()
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def error_name(e):
    # Deliberately do not log URL query strings, tokens or response bodies.
    return type(e).__name__


def rows(frame):
    if frame is None or not hasattr(frame, "columns"):
        raise ValueError("not a data frame")
    if "stock_code" not in frame.columns:
        raise ValueError(f"unexpected constituent fields {list(frame.columns)}")
    codes = [str(x).strip().zfill(6) for x in frame["stock_code"]]
    if not codes or any(not CODE_RE.fullmatch(x) for x in codes):
        raise ValueError("empty or invalid 6-digit stock codes")
    if len(codes) != len(set(codes)):
        raise ValueError("duplicate constituent codes")
    return sorted(codes)


def best(rows_, name, name_field):
    exact = [r for r in rows_ if r.get(name_field) == name]
    if exact:
        return exact[0]
    subset = [r for r in rows_ if name in str(r.get(name_field) or "")]
    return subset[0] if subset else None


def expected_vendor_count(index_code):
    """Read provider-reported total from same board index's pagination metadata."""
    import requests
    url = f"https://d.10jqka.com.cn/v2/blockrank/{index_code}/8/d15.js"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://q.10jqka.com.cn/"}, timeout=12)
    r.raise_for_status()
    txt = r.text
    a = txt.find("{")
    b = txt.rfind("}")
    if a < 0 or b < a:
        raise ValueError("no vendor JSON")
    result = json.loads(txt[a:b+1])
    return int(result["block"]["subcodeCount"])


def main():
    import akshare as ak
    import adata

    out = {
        "result_kind": "concept_membership_source_probe",
        "observed_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "intended_frozen_trade_date": "2026-10-26",
        "live_provider_membership_is_historical_asof": False,
        "samples": [],
        "tushare": {"status": "TOKEN_NOT_CONFIGURED"},
        "source_disclaimer": "A live concept list may differ from 2026-10-26 close. Probe does not validate historical as-of membership."
    }
    boards = []
    try:
        raw = within(45, ak.stock_board_concept_name_ths)
        if not {"name", "code"}.issubset(raw.columns):
            raise ValueError("missing AKShare name/code fields")
        boards = [{"name": str(r["name"]).strip(), "code": str(r["code"]).strip()}
                  for _, r in raw.iterrows()]
        print("AK_THS_LIST", len(boards), flush=True)
    except Exception as e:
        out["ak_board_list_error"] = error_name(e)
        print("AK_THS_LIST_FAILED", error_name(e), flush=True)

    indexed = []
    try:
        df = within(65, adata.stock.info.all_concept_code_ths)
        if {"name", "index_code"}.issubset(df.columns):
            indexed = [
                {"name": str(r["name"]).strip(), "index_code": str(r["index_code"]).strip()}
                for _, r in df.iterrows() if str(r.get("index_code", "")).strip().startswith("8")
            ]
        else:
            raise ValueError("missing adata name/index_code fields")
        print("ADATA_INDEX_LIST", len(indexed), flush=True)
    except Exception as e:
        out["adata_index_list_error"] = error_name(e)
        print("ADATA_INDEX_LIST_FAILED", error_name(e), flush=True)

    for name in SAMPLES:
        item = {"wanted": name, "name_matched": None,
                "concept_code": None, "index_code": None,
                "web_concept_code": {"status": "NOT_ATTEMPTED"},
                "index_code_full": {"status": "NOT_ATTEMPTED"}}
        found = best(indexed, name, "name")
        board = best(boards, name, "name")
        if board:
            item["name_matched"] = board["name"]
            item["concept_code"] = board["code"]
            try:
                members = within(38, lambda: adata.stock.info.concept_constituent_ths(
                    concept_code=board["code"]))
                codes = rows(members)
                # adata's page parser hard-caps this route at five pages.
                item["web_concept_code"] = {
                    "status": "UNVERIFIED_PAGINATION_HARD_CAP",
                    "source": "ADATA_THS_CONCEPT_CODE",
                    "returned_unique": len(codes),
                    "member_codes": codes}
            except Exception as e:
                item["web_concept_code"] = {"status": "FAIL", "error": error_name(e)}
        if found:
            item["name_matched"] = found["name"]
            index_code = found["index_code"]
            item["index_code"] = index_code
            try:
                members = within(35, lambda: adata.stock.info.concept_constituent_ths(
                    index_code=index_code))
                codes = rows(members)
                item["index_code_full"] = {
                    "status": "UNVERIFIED_VENDOR_TOTAL",
                    "source": "ADATA_THS_INDEX_CODE",
                    "returned_unique": len(codes),
                    "member_codes": codes}
                try:
                    expected = within(16, lambda: expected_vendor_count(index_code))
                    item["index_code_full"]["vendor_declared_total"] = expected
                    if len(codes) == expected:
                        item["index_code_full"]["status"] = "COMPLETE_COUNT_MATCH"
                    else:
                        item["index_code_full"]["status"] = "COUNT_MISMATCH"
                except Exception as e:
                    item["index_code_full"]["count_check_error"] = error_name(e)
            except Exception as e:
                item["index_code_full"] = {"status": "FAIL", "error": error_name(e)}
        out["samples"].append(item)
        print("CONCEPT_PROBE",json.dumps({
            "wanted": name, "matched": item["name_matched"],
            "concept_code": item["concept_code"], "index_code": item["index_code"],
            "web_status": item["web_concept_code"]["status"],
            "web_size": item["web_concept_code"].get("returned_unique"),
            "index_status": item["index_code_full"]["status"],
            "index_size": item["index_code_full"].get("returned_unique"),
            "vendor_count": item["index_code_full"].get("vendor_declared_total")
        },ensure_ascii=False),flush=True)

    token = os.getenv("TUSHARE_TOKEN")
    if token:
        try:
            import tushare as ts
            pro = ts.pro_api(token)
            frame = within(30, lambda: pro.dc_member(ts_code="BK1184.DC", trade_date="20261026"))
            if not {"con_code", "name"}.issubset(frame.columns):
                raise ValueError("unexpected tushare member schema")
            con = sorted({str(v).strip().split(".")[0].zfill(6) for v in frame["con_code"]})
            if not con or any(not CODE_RE.fullmatch(c) for c in con):
                raise ValueError("invalid tushare member codes")
            out["tushare"] = {"status": "SUCCESS", "concept_code": "BK1184.DC",
                             "trade_date": "2026-10-26", "member_count": len(con),
                             "member_codes": con}
        except Exception as e:
            out["tushare"] = {"status": "FAIL", "error": error_name(e)}

    path = Path("/tmp/adata_theme_probe_20261026.json")
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print("PROBE_SUMMARY",json.dumps({
        "adata_index_boards":len(indexed),
        "ak_share_ths_boards":len(boards),
        "tushare":out["tushare"]["status"],
        "verified_index_concepts":sum(x["index_code_full"]["status"]=="COMPLETE_COUNT_MATCH"
                                      for x in out["samples"])
    },ensure_ascii=False),flush=True)


if __name__ == "__main__":
    main()
