#!/usr/bin/env python3
"""Resolve independently discovered hotspots to an industry OR a verified concept.

This is a routing and prescreening layer, not a new trend confirmation model.
All prices and industry identities come from the frozen same-day market dataset.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

SH = ZoneInfo("Asia/Shanghai")
CODE = re.compile(r"^\d{6}$")
GENERIC = {"工业", "自动化", "设备", "产业", "概念", "板块", "行业", "材料", "制造", "相关"}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def keywords(name):
    parts = re.split(r"[/／、+\s]+", str(name or ""))
    return [p for p in parts if len(p) >= 2 and p not in GENERIC]


def name_strength(name, board_name):
    board = str(board_name).replace("概念", "")
    points = [3 if t == board else 2 if t in board else 1 if board in t else 0
              for t in keywords(name)]
    return max(points, default=0)


def safe_number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def get_return(quote):
    if quote.get("confidence") not in {"high", "medium"}:
        return None
    r = safe_number(quote.get("change_pct"))
    if r is not None:
        return r
    p, old = safe_number(quote.get("price")), safe_number(quote.get("prev_close"))
    return (p / old - 1) * 100 if p is not None and old and old > 0 else None


def validate_memberships(catalog, trade_date):
    if (catalog.get("schema_version") != 1 or
            catalog.get("as_of_trade_date") != trade_date or
            catalog.get("source") != "EASTMONEY_AKSHARE"):
        raise ValueError("CONCEPT_MEMBERSHIP_DATE_OR_SOURCE_INVALID")
    rows = catalog.get("concepts")
    if not isinstance(rows, list):
        raise ValueError("CONCEPT_MEMBERSHIP_MISSING")
    seen = set()
    for item in rows:
        code, name = item.get("concept_id"), item.get("name")
        members = item.get("member_codes")
        if not code or not name or code in seen or not isinstance(members, list):
            raise ValueError("CONCEPT_MEMBERSHIP_INVALID_ID")
        if not members or any(not CODE.fullmatch(str(x)) for x in members):
            raise ValueError("CONCEPT_MEMBERSHIP_INVALID_STOCK")
        seen.add(code)
    return rows


def fetch_current_memberships(handoff):
    """Fetch only name-matching boards; NEVER label today's membership as a past snapshot."""
    trade_date = handoff["trade_date"]
    if datetime.now(SH).date().isoformat() != trade_date:
        raise ValueError("LIVE_MEMBERSHIP_NOT_POINT_IN_TIME_FOR_TRADE_DATE")
    import akshare as ak
    listing = ak.stock_board_concept_name_em()
    if not {"板块代码", "板块名称"}.issubset(listing.columns):
        raise ValueError("EASTMONEY_BOARD_SCHEMA_CHANGED")
    relevant = {}
    for _, item in listing.iterrows():
        code, name = str(item["板块代码"]), str(item["板块名称"])
        if any(name_strength(s.get("trend_name"), name) >= 2
               for s in handoff["signals"]):
            relevant[code] = name
    # Limit remote calls while preserving complete memberships for each fetched board.
    if len(relevant) > 30:
        raise ValueError("TOO_MANY_MATCHED_CONCEPTS_REQUIRE_ALIAS_REVIEW")
    concepts = []
    for code, name in sorted(relevant.items()):
        members = ak.stock_board_concept_cons_em(symbol=code)
        if not {"代码", "名称"}.issubset(members.columns):
            raise ValueError("EASTMONEY_CONSTITUENT_SCHEMA_CHANGED:" + code)
        codes = sorted({str(v).zfill(6) for v in members["代码"]})
        if not codes or any(not CODE.fullmatch(c) for c in codes):
            raise ValueError("EMPTY_OR_INVALID_CONCEPT:" + code)
        concepts.append({"concept_id": code, "name": name, "member_codes": codes,
                         "source": "EASTMONEY_AKSHARE"})
    return {"schema_version": 1, "source": "EASTMONEY_AKSHARE",
            "as_of_trade_date": trade_date, "concepts": concepts}


def build(handoff, industry_index, latest, structure, catalog, cap=20):
    date = handoff.get("trade_date")
    if (not date or handoff.get("result_kind") != "a_share_trend_handoff" or
            latest.get("trade_date") != date or latest.get("market_status") != "closed" or
            structure.get("reference_trade_date") != date):
        raise ValueError("INPUTS_NOT_SAME_COMPLETED_SESSION")
    concepts = validate_memberships(catalog, date)
    company_map = industry_index.get("companies") or {}
    latest_quotes = latest.get("stocks") or {}
    price_structures = structure.get("companies") or {}
    if not company_map or not latest_quotes or not price_structures:
        raise ValueError("INPUT_UNIVERSE_INCOMPLETE")
    if cap < 1 or cap > 20:
        raise ValueError("THEME_RESEARCH_CAP_MUST_BE_1_TO_20")
    for signal in handoff.get("signals") or []:
        if (not signal.get("industry_codes") or
                signal.get("mapping_status") != "resolved"):
            raise ValueError("UNRESOLVED_UPSTREAM_SIGNAL")
    result = []
    for signal in handoff.get("signals") or []:
        mapped = set(signal["industry_codes"])
        industry_members = {str(code).zfill(6) for code, info in company_map.items()
                            if info.get("mapping_status") == "mapped"
                            and info.get("industry_code") in mapped}
        if not industry_members:
            raise ValueError("NO_INDUSTRY_SEED:" + signal["trend_name"])
        choices = []
        for concept in concepts:
            name_match = name_strength(signal["trend_name"], concept["name"])
            if name_match < 2:
                continue
            codes = set(concept["member_codes"]) & set(company_map)
            values = [(code, get_return(latest_quotes.get(code) or {}))
                      for code in codes]
            valid = [(code, r) for code, r in values if r is not None]
            if len(valid) < 5 or len(valid) / max(len(codes), 1) < .8:
                continue
            bread = sum(r > 0 for _, r in valid) / len(valid)
            med = median(r for _, r in valid)
            extra_up = sum(code not in industry_members and r >= 1
                           for code, r in valid)
            rising = sum(r >= 1 for _, r in valid)
            industries = {company_map[code].get("industry_code")
                          for code, _ in valid}
            # A concept must materially explain strength OUTSIDE the original SW route.
            is_theme = (len(industries) >= 3 and extra_up >= 3 and
                        extra_up / max(rising, 1) >= .25 and
                        bread >= .55 and med >= 0)
            choices.append({"concept": concept, "codes": codes, "breadth": bread,
                            "median": med, "extra_up": extra_up, "rising": rising,
                            "industry_count": len(industries), "match": name_match,
                            "valid": is_theme, "quote_coverage": len(valid) / len(codes)})
        eligible = [c for c in choices if c["valid"]]
        eligible.sort(key=lambda x: (-x["match"], -x["extra_up"] / max(x["rising"], 1),
                                     -x["median"], x["concept"]["concept_id"]))
        best = eligible[0] if eligible else None
        row = {"rank": signal["rank"], "trend_name": signal["trend_name"],
               "trend_state": signal["trend_state"], "market_state": signal["market_state"],
               "hotspot_type": "THEME" if best else "INDUSTRY",
               "original_industry_codes": signal["industry_codes"],
               "mapping_source": "EASTMONEY_AKSHARE" if best else "SW_LEVEL3",
               "mapping_code": best["concept"]["concept_id"] if best else None,
               "mapping_name": best["concept"]["name"] if best else None,
               "candidate_stocks": []}
        if best:
            row.update({"concept_member_count": len(best["concept"]["member_codes"]),
                        "concept_member_codes": best["concept"]["member_codes"],
                        "concept_up_ratio": round(best["breadth"], 4),
                        "concept_median_return_pct": round(best["median"], 3),
                        "outside_route_rising_count": best["extra_up"],
                        "quote_coverage": round(best["quote_coverage"], 4)})
            # Reuse the existing cheap technical opportunity screen; no new buy score.
            from build_trend_buy_manual_research import compact_opportunity
            ranked = []
            for code in best["codes"]:
                info = company_map.get(code) or {}
                quote = latest_quotes.get(code) or {}
                name = str(quote.get("name") or "")
                if not CODE.fullmatch(code) or "ST" in name.upper() or "退" in name:
                    continue
                opportunity, reason = compact_opportunity(price_structures.get(code), date)
                if opportunity is None:
                    continue
                ranked.append((opportunity["opportunity_score"], code, info, name))
            ranked.sort(key=lambda x: (-x[0], x[1]))
            row["candidate_stocks"] = [
                {"rank": i, "stock_code": code, "stock_name": name,
                 "industry_code": str(info.get("industry_code") or ""),
                 "opportunity_score": round(score, 6)}
                for i, (score, code, info, name) in enumerate(ranked[:cap], 1)]
        result.append(row)
    return {"schema_version": 1, "result_kind": "hotspot_stock_route_snapshot",
            "trade_date": date, "status": "COMPLETE",
            "concept_source": catalog["source"],
            "concept_as_of_trade_date": catalog["as_of_trade_date"],
            "max_candidates_per_theme": cap, "routes": result}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff", default="research/trend_handoff.json")
    parser.add_argument("--industry-index", default="data/research/company_industry_index.json")
    parser.add_argument("--latest", default="data/latest.json")
    parser.add_argument("--structure", default="data/research/full_market_price_structure.json")
    parser.add_argument("--concept-file", help="Verified same-day membership snapshot (historical replay)")
    parser.add_argument("--output-dir", default="data/research/theme_stock_candidates")
    args = parser.parse_args()
    handoff = read(args.handoff)
    catalog = read(args.concept_file) if args.concept_file else fetch_current_memberships(handoff)
    result = build(handoff, read(args.industry_index), read(args.latest),
                   read(args.structure), catalog)
    output = Path(args.output_dir) / (result["trade_date"] + ".json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({"output": str(output), "industry": sum(x["hotspot_type"] == "INDUSTRY" for x in result["routes"]),
                      "themes": sum(x["hotspot_type"] == "THEME" for x in result["routes"]),
                      "candidates": sum(len(x["candidate_stocks"]) for x in result["routes"])},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
