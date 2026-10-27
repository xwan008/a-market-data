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


def build(handoff, industry_index, latest, structure, catalog, cap=20, supplement=None):
    date = handoff.get("trade_date")
    if (not date or handoff.get("result_kind") != "a_share_trend_handoff" or
            latest.get("trade_date") != date or latest.get("market_status") != "closed" or
            structure.get("reference_trade_date") != date):
        raise ValueError("INPUTS_NOT_SAME_COMPLETED_SESSION")
    concepts = validate_memberships(catalog, date)
    company_map = industry_index.get("companies") or {}
    latest_quotes = dict(latest.get("stocks") or {})
    if supplement is not None:
        if (supplement.get("trade_date") != date or
                supplement.get("market_status") != "closed" or
                supplement.get("result_kind") != "concept_quote_supplement" or
                not isinstance(supplement.get("stocks"), dict)):
            raise ValueError("CONCEPT_QUOTE_SUPPLEMENT_ASOF_INVALID")
        for symbol, quote in supplement["stocks"].items():
            if (not CODE.fullmatch(str(symbol)) or not isinstance(quote, dict) or
                    quote.get("date") != date or
                    quote.get("confidence") not in ("high", "medium") or
                    safe_number(quote.get("price")) is None or
                    safe_number(quote.get("prev_close")) is None):
                raise ValueError("CONCEPT_SUPPLEMENT_QUOTE_NOT_DATE_VERIFIED")
        # Existing frozen market quotes always take precedence over supplemental quotes.
        latest_quotes = {**supplement["stocks"], **latest_quotes}
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
        incomplete = []
        matched_concepts = []
        for concept in concepts:
            name_match = name_strength(signal["trend_name"], concept["name"])
            if name_match < 2:
                continue
            full_members = set(concept["member_codes"])
            mainboard_members = {c for c in full_members if is_main_board(c)}
            matched_concepts.append(concept["concept_id"])
            # Main-board-only research: breadth and data coverage use the
            # concept's SH/SZ main-board members, NOT all-market constituents.
            # Full membership is kept intact for provenance and reproducibility.
            values = [(code, get_return(latest_quotes.get(code) or {}))
                      for code in mainboard_members]
            valid = [(code, r) for code, r in values if r is not None]
            actual_coverage = len(valid) / len(mainboard_members) if mainboard_members else 0
            if len(valid) < 5 or actual_coverage < .8:
                incomplete.append({
                    "concept_id": concept["concept_id"],
                    "concept_name": concept["name"],
                    "member_count": len(full_members),
                    "mainboard_member_count": len(mainboard_members),
                    "quoted_count": len(valid),
                    "quote_coverage": round(actual_coverage, 4),
                    "missing_from_frozen_quotes": sum(
                        c not in (latest.get("stocks") or {}) for c in mainboard_members),
                    "missing_from_industry_index": sum(
                        c not in company_map for c in mainboard_members),
                    "reason": "INSUFFICIENT_CONCEPT_QUOTE_COVERAGE"
                })
                continue
            # Only actual main-board SW members are eligible for Top20 research.
            codes = mainboard_members & set(company_map)
            bread = sum(r > 0 for _, r in valid) / len(valid)
            med = median(r for _, r in valid)
            extra_up = sum(code not in industry_members and r >= 1
                           for code, r in valid)
            rising = sum(r >= 1 for _, r in valid)
            industries = {company_map[code].get("industry_code")
                          for code, _ in valid if code in company_map}
            # Industry-vs-theme is a mapping decision, not an entry signal.
            # A single down session must not erase an already coherent 3d/5d
            # cross-industry theme. Require same-session verified daily history.
            windows = {}
            for days, field in ((3, "return_3d_pct"), (5, "return_5d_pct")):
                window_values = []
                for code, _ in valid:
                    item = price_structures.get(code) or {}
                    if (item.get("data_status") == "verified" and
                            item.get("data_date") == date):
                        value = safe_number((item.get("phase_evidence") or {}).get(field))
                        if value is not None:
                            window_values.append((code, value))
                coverage = len(window_values) / len(valid)
                windows[days] = {
                    "coverage": round(coverage, 4),
                    "breadth": sum(v > 0 for _, v in window_values) / len(window_values)
                               if window_values else None,
                    "median": median(v for _, v in window_values)
                              if window_values else None,
                    "outside_positive": sum(c not in industry_members and v > 0
                                            for c, v in window_values),
                    "positive_total": sum(v > 0 for _, v in window_values),
                }
            one_day_coherent = (extra_up >= 3 and
                                extra_up / max(rising, 1) >= .25 and
                                bread >= .55 and med >= 0)
            multi_day_coherent = all(
                w["coverage"] >= .8 and w["breadth"] is not None
                and w["breadth"] >= .6 and w["median"] >= 0
                and w["outside_positive"] >= 3
                and w["outside_positive"] / max(w["positive_total"], 1) >= .25
                for w in windows.values())
            is_theme = len(industries) >= 3 and (
                one_day_coherent or multi_day_coherent)
            choices.append({"concept": concept, "codes": codes, "mainboard_member_count": len(mainboard_members), "breadth": bread,
                            "median": med, "extra_up": extra_up, "rising": rising,
                            "windows": windows, "recognition_basis":
                                "CONCEPT_3D_5D_STRUCTURE" if multi_day_coherent
                                else "CONCEPT_1D_STRUCTURE" if one_day_coherent
                                else "NO_MATCHED_THEME_STRENGTH",
                            "industry_count": len(industries), "match": name_match,
                            "valid": is_theme, "quote_coverage": actual_coverage})
        eligible = [c for c in choices if c["valid"]]
        eligible.sort(key=lambda x: (-x["match"], -x["extra_up"] / max(x["rising"], 1),
                                     -x["median"], x["concept"]["concept_id"]))
        best = eligible[0] if eligible else None
        # A relevant matched concept with insufficient quotes is UNKNOWN,
        # not a negative theme finding and definitely not a positive industry classification.
        partial_catalog = catalog.get("catalog_scope") in ("PARTIAL_CONCEPT_CATALOG", "SINGLE_BOARD_ONLY")
        unresolved = bool(not best and (incomplete or partial_catalog))
        row = {"rank": signal["rank"], "trend_name": signal["trend_name"],
               "trend_state": signal["trend_state"], "market_state": signal["market_state"],
               "hotspot_type": "THEME" if best else "DATA_INSUFFICIENT" if unresolved else "INDUSTRY",
               "original_industry_codes": signal["industry_codes"],
               "mapping_source": catalog["source"] if best else "SW_LEVEL3",
               "mapping_code": best["concept"]["concept_id"] if best else None,
               "mapping_name": best["concept"]["name"] if best else None,
               "candidate_stocks": [],
               "matched_concepts": matched_concepts,
               "insufficient_concepts": incomplete,
               "classification_reason": ("CONCEPT_COVERAGE_UNVERIFIED" if incomplete else
                   "PARTIAL_CONCEPT_CATALOG") if unresolved else
                   "CONCEPT_EVIDENCE_SUPPORTED" if best else "INDUSTRY_MAPPING_RETAINED"}
        if best:
            row.update({"concept_member_count": len(best["concept"]["member_codes"]),
                        "concept_mainboard_member_count": best["mainboard_member_count"],
                        "concept_member_codes": best["concept"]["member_codes"],
                        "concept_up_ratio": round(best["breadth"], 4),
                        "concept_median_return_pct": round(best["median"], 3),
                        "outside_route_rising_count": best["extra_up"],
                        "recognition_basis": best["recognition_basis"],
                        "evidence_3d": best["windows"][3],
                        "evidence_5d": best["windows"][5],
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
            "market_scope": "SH_SZ_MAINBOARD_ONLY",
            "max_candidates_per_theme": cap, "routes": result}



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
            identities.get("status") != "COMPLETE"):
        raise ValueError("IDENTITY_OR_MARKET_HANDOFF_DATE_SCOPE_INVALID")
    if not (handoff.get("source") or {}).get("identity_verified_before_state") is True:
        raise ValueError("HANDOFF_NOT_ADJUDICATED_AFTER_IDENTITY")
    if not 1 <= cap <= 20:
        raise ValueError("RESEARCH_CANDIDATE_CAP_INVALID")
    signals = handoff.get("signals") or []
    ids = identities.get("identities") or []
    if len(ids) != len(signals) or any(
            a.get("hotspot_name") != b.get("trend_name") or
            a.get("mapping_status") != "VERIFIED" for a, b in zip(ids, signals)):
        raise ValueError("IDENTITIES_NOT_EXACTLY_MATCHED_TO_HANDOFF")
    industry_companies = industry_index.get("companies") or {}
    quotes = latest.get("stocks") or {}
    structures = structure.get("companies") or {}
    if not industry_companies or not quotes or not structures:
        raise ValueError("MARKET_RESEARCH_UNIVERSE_EMPTY")
    matched_concepts = {}
    if any(a.get("board_type") == "THEME" for a in ids):
        if catalog is None:
            raise ValueError("VERIFIED_CONCEPT_MEMBERSHIP_REQUIRED")
        validate_memberships(catalog, day)
        matched_concepts = {c["concept_id"]: c for c in catalog["concepts"]}
    routed = []
    for identity, signal in zip(ids, signals):
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
            if identity.get("concept_code") != code or code not in matched_concepts:
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
    parser.add_argument("--supplement-quotes", help="Same-day concept-only quote supplement, never overwrites frozen base")
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
