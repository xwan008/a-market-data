#!/usr/bin/env python3
"""Validate PRE-STATE verified hotspot identity and build the post-state buy routing.

No dynamic identity guesses or stock-breadth market-state thresholds are used.
Industry passes SW codes; theme passes confirmed concept members and Top20.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

CODE = re.compile(r"^\d{6}$")
SH_MAIN_PREFIXES = ("600", "601", "603", "605")
SZ_MAIN_PREFIXES = ("000", "001", "002", "003")


def is_main_board(code):
    return bool(CODE.fullmatch(str(code))) and str(code).startswith(
        SH_MAIN_PREFIXES + SZ_MAIN_PREFIXES
    )
GENERIC = {"工业", "自动化", "工业自动化", "设备", "产业", "概念", "板块", "行业", "材料", "制造", "相关"}


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
            catalog.get("source") not in {"EASTMONEY_AKSHARE", "THS_ADATA", "THS_FUYAO"}):
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
        if len(members) != len(set(members)):
            raise ValueError("CONCEPT_MEMBERSHIP_DUPLICATE_STOCK")
        seen.add(code)
    return rows


def build_verified_routes(handoff, industry_index, latest, structure, identities,
                          catalog=None, cap=20):
    """Post-state handoff builder: NO name guessing, NO market-state recalculation.

    Identity must be frozen before the researcher adjudicated market state.
    Industry route passes only industry CODES. Theme route uses verified
    concept membership to select up to 20 MAINBOARD technical candidates.
    """
    day = handoff.get("trade_date")
    if (not day or handoff.get("result_kind") != "a_share_trend_handoff" or
            latest.get("trade_date") != day or latest.get("market_status") != "closed" or
            structure.get("reference_trade_date") != day or
            identities.get("result_kind") != "hotspot_identity_snapshot" or
            identities.get("trade_date") != day or
            identities.get("market_scope") != "SH_SZ_MAINBOARD_ONLY" or
            identities.get("status") not in ("COMPLETE", "NEEDS_IDENTITY_REVIEW")):
        raise ValueError("IDENTITY_OR_MARKET_HANDOFF_DATE_SCOPE_INVALID")
    if not (handoff.get("source") or {}).get("identity_verified_before_state") is True:
        raise ValueError("HANDOFF_NOT_ADJUDICATED_AFTER_IDENTITY")
    if not identities.get("resolved_at") or not handoff.get("generated_at"):
        raise ValueError("IDENTITY_TO_TREND_CHRONOLOGY_MISSING")
    from datetime import datetime as _dt
    try:
        if _dt.fromisoformat(identities["resolved_at"]) > _dt.fromisoformat(handoff["generated_at"]):
            raise ValueError("IDENTITY_RESOLVED_AFTER_TREND_STATE")
        if catalog and catalog.get("source_observed_at"):
            if _dt.fromisoformat(catalog["source_observed_at"]) > _dt.fromisoformat(handoff["generated_at"]):
                raise ValueError("CONCEPT_SNAPSHOT_CAPTURED_AFTER_TREND_STATE")
    except (TypeError, KeyError) as ex:
        raise ValueError("IDENTITY_TO_TREND_CHRONOLOGY_INVALID") from ex
    if not 1 <= cap <= 20:
        raise ValueError("RESEARCH_CANDIDATE_CAP_INVALID")
    signals = handoff.get("signals") or []
    ids = identities.get("identities") or []
    by_name = {x.get("hotspot_name"): x for x in ids}
    if (len(by_name) != len(ids) or
            len({s.get("trend_name") for s in signals}) != len(signals) or
            any(name not in by_name or by_name[name].get("mapping_status") != "VERIFIED"
                for name in [s.get("trend_name") for s in signals])):
        raise ValueError("IDENTITIES_NOT_MATCHED_TO_HANDOFF")
    industry_companies = industry_index.get("companies") or {}
    quotes = latest.get("stocks") or {}
    structures = structure.get("companies") or {}
    if not industry_companies or not quotes or not structures:
        raise ValueError("MARKET_RESEARCH_UNIVERSE_EMPTY")
    matched_concepts = {}
    if any(by_name[signal["trend_name"]].get("board_type") == "THEME" for signal in signals):
        if catalog is None:
            raise ValueError("VERIFIED_CONCEPT_MEMBERSHIP_REQUIRED")
        validate_memberships(catalog, day)
        matched_concepts = {c["concept_id"]: c for c in catalog["concepts"]}
    routed = []
    for signal in signals:
        identity = by_name[signal["trend_name"]]
        kind = identity["board_type"]
        code = identity["board_code"]
        if (signal.get("board_type") != kind or
                signal.get("board_code") != code or
                signal.get("market_state") not in ("趋势确认", "候选趋势")):
            raise ValueError("POST_MAPPING_TREND_STATE_OR_IDENTITY_MISMATCH")
        industry_codes = identity.get("industry_codes") or []
        if kind == "INDUSTRY":
            if (not industry_codes or industry_codes != signal.get("industry_codes") or
                    any(not re.fullmatch(r"S\d{6}", c) for c in industry_codes)):
                raise ValueError("INDUSTRY_CODE_HANDOFF_MISMATCH")
            route = {
                "rank": signal["rank"], "trend_name": signal["trend_name"],
                "trend_state": signal["trend_state"], "market_state": signal["market_state"],
                "hotspot_type": "INDUSTRY", "board_code": code,
                "original_industry_codes": industry_codes,
                "industry_codes": industry_codes, "mapping_source": "SW2021_L3",
                "mapping_code": code, "mapping_name": signal["trend_name"],
                "candidate_stocks": [], "mapping_status": "VERIFIED",
                "classification_reason": "IDENTITY_ORIGIN_AND_DRIVER_VERIFIED",
            }
        elif kind == "THEME":
            if (identity.get("concept_code") != code or code not in matched_concepts or
                    identity.get("origin_source") != catalog["source"]):
                raise ValueError("VERIFIED_CONCEPT_CODE_OR_MEMBERSHIP_MISSING")
            members = matched_concepts[code]["member_codes"]
            scoped = {c for c in members if is_main_board(c)}
            valid = [c for c in scoped if get_return(quotes.get(c) or {}) is not None]
            coverage = len(valid)/len(scoped) if scoped else 0
            if len(valid) < 5 or coverage < .95:
                raise ValueError("CONCEPT_MAINBOARD_QUOTE_COVERAGE_INSUFFICIENT")
            from build_trend_buy_manual_research import compact_opportunity
            candidates = []
            for stock in sorted(scoped):
                info = industry_companies.get(stock) or {}
                q = quotes.get(stock) or {}
                name = str(q.get("name") or "")
                if (info.get("mapping_status") != "mapped" or
                        not info.get("industry_code") or not name or
                        "ST" in name.upper() or "退" in name):
                    continue
                opportunity, _ = compact_opportunity(structures.get(stock), day)
                if opportunity is not None:
                    candidates.append((opportunity["opportunity_score"],stock,
                                       info["industry_code"],name))
            candidates.sort(key=lambda r: (-r[0],r[1]))
            route = {
                "rank": signal["rank"], "trend_name": signal["trend_name"],
                "trend_state": signal["trend_state"], "market_state": signal["market_state"],
                "hotspot_type": "THEME", "board_code": code,
                "original_industry_codes": signal.get("industry_codes") or [],
                "mapping_source": catalog["source"], "mapping_code": code,
                "mapping_name": matched_concepts[code]["name"],
                "concept_member_count": len(members),
                "concept_mainboard_member_count": len(scoped),
                "concept_member_codes": members,
                "quote_coverage": round(coverage, 4),
                "mapping_status": "VERIFIED",
                "classification_reason": "IDENTITY_ORIGIN_AND_DRIVER_VERIFIED",
                "candidate_stocks": [
                    {"rank": n, "stock_code": c, "stock_name": name,
                     "industry_code": sector, "opportunity_score": round(score,6)}
                    for n,(score,c,sector,name) in enumerate(candidates[:cap],1)
                ],
            }
        else:
            raise ValueError("UNKNOWN_VERIFIED_BOARD_TYPE")
        routed.append(route)
    return {
        "schema_version": 1, "result_kind": "hotspot_stock_route_snapshot",
        "trade_date": day, "status": "COMPLETE",
        "market_scope": "SH_SZ_MAINBOARD_ONLY",
        "identities_verified_before_state": True,
        "concept_source": catalog["source"] if catalog else None,
        "concept_as_of_trade_date": day,
        "max_candidates_per_theme": cap, "routes": routed,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff", default="research/trend_handoff.json")
    parser.add_argument("--industry-index", default="data/research/company_industry_index.json")
    parser.add_argument("--latest", default="data/latest.json")
    parser.add_argument("--structure", default="data/research/full_market_price_structure.json")
    parser.add_argument("--concept-file", help="Verified same-day membership for identified themes")
    parser.add_argument("--identity-file", required=True,
                        help="Frozen pre-state verified identity resolution snapshot")
    parser.add_argument("--output-dir", default="data/research/theme_stock_candidates")
    args = parser.parse_args()
    handoff = read(args.handoff)
    catalog = read(args.concept_file) if args.concept_file else None
    result = build_verified_routes(
        handoff, read(args.industry_index), read(args.latest),
        read(args.structure), read(args.identity_file), catalog)
    output = Path(args.output_dir) / (result["trade_date"] + ".json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({"output": str(output), "industry": sum(x["hotspot_type"] == "INDUSTRY" for x in result["routes"]),
                      "themes": sum(x["hotspot_type"] == "THEME" for x in result["routes"]),
                      "data_insufficient": sum(x["hotspot_type"] == "DATA_INSUFFICIENT" for x in result["routes"]),
                      "candidates": sum(len(x["candidate_stocks"]) for x in result["routes"])},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
