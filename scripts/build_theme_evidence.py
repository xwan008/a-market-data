#!/usr/bin/env python3
"""Compact auxiliary theme evidence from a versioned catalog and frozen daily quotes.

This module does NOT make trend/position/routing decisions.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

from build_sector_discovery import number, read_json, stock_features

TZ = ZoneInfo("Asia/Shanghai")
CODE_RE = re.compile(r"^S\d{6}$")


def _pct(n, d):
    return round(n / d, 4) if d else None


def _med(values):
    return round(median(values), 3) if values else None


def _rows(values, name):
    rows = [x for x in values if x.get(name) is not None]
    return [x[name] for x in rows]


def _industry_map(industry_index):
    groups, names = defaultdict(set), {}
    company_map = industry_index.get("companies")
    if not isinstance(company_map, dict) or not company_map:
        raise ValueError("industry_universe_missing")
    for stock, item in company_map.items():
        if item.get("mapping_status") != "mapped":
            continue
        sector, sector_name = str(item.get("industry_code") or ""), item.get("sw_level3_name")
        if not CODE_RE.fullmatch(sector) or not sector_name:
            continue
        if sector in names and names[sector] != sector_name:
            raise ValueError("industry_name_collision:" + sector)
        names[sector] = sector_name
        groups[sector].add(str(stock).zfill(6))
    return groups, names


def _validate_catalog(catalog, trade_date, index_names, retrospective):
    if catalog.get("schema_version") != 1 or catalog.get("result_kind") != "a_share_static_theme_industry_catalog":
        raise ValueError("catalog_invalid_schema")
    if catalog.get("authority") != "AUXILIARY_ONLY":
        raise ValueError("catalog_cannot_be_authoritative")
    asof = str(catalog.get("catalog_as_of_date") or "")
    try:
        date.fromisoformat(asof)
    except ValueError as exc:
        raise ValueError("catalog_invalid_asof_date") from exc
    if asof > trade_date and not retrospective:
        raise ValueError("catalog_created_after_trade_date_point_in_time_violation")
    themes = catalog.get("themes")
    if not isinstance(themes, list) or not themes:
        raise ValueError("catalog_empty")
    names_seen, ids_seen = set(), set()
    for theme in themes:
        tid, name = theme.get("theme_id"), theme.get("theme_name")
        if not tid or not name or tid in ids_seen or name in names_seen:
            raise ValueError("catalog_duplicate_or_missing_theme")
        ids_seen.add(tid)
        names_seen.add(name)
        code_seen, core_count = set(), 0
        for row in theme.get("industries") or []:
            code = row.get("code")
            if not isinstance(code, str) or not CODE_RE.fullmatch(code) or code in code_seen:
                raise ValueError("catalog_invalid_industry_code")
            if index_names.get(code) != row.get("name"):
                raise ValueError("catalog_industry_not_in_same_universe:" + code)
            if row.get("role") not in ("core", "related"):
                raise ValueError("catalog_invalid_industry_role")
            core_count += row["role"] == "core"
            code_seen.add(code)
        if not core_count:
            raise ValueError("catalog_theme_no_core:" + tid)
    return asof > trade_date


def _theme_metrics(theme, groups, stock_data, market_median):
    core = [i["code"] for i in theme["industries"] if i["role"] == "core"]
    related = [i["code"] for i in theme["industries"] if i["role"] == "related"]
    members = set().union(*(groups.get(code, set()) for code in core))
    available = [stock_data[code] for code in sorted(members) if stock_data.get(code) is not None]
    usable = len(available)
    r1 = _rows(available, "r1")
    r3 = _rows(available, "r3")
    r5 = _rows(available, "r5")
    volume = [n for n in _rows(available, "volume") if n > 0]
    core_count = len(members)
    coverage = _pct(usable, core_count)
    med1 = _med(r1)
    med3 = _med(r3) if len(r3) >= max(3, int(usable * .6 + .9999)) else None
    med5 = _med(r5) if len(r5) >= max(3, int(usable * .6 + .9999)) else None
    medvolume = _med(volume) if len(volume) >= max(3, int(usable * .6 + .9999)) else None
    breadth = _pct(sum(r > 0 for r in r1), usable)
    breadth3 = _pct(sum(r > 0 for r in r3), len(r3)) if med3 is not None else None
    breadth5 = _pct(sum(r > 0 for r in r5), len(r5)) if med5 is not None else None
    rs = round(med1 - market_median, 3) if med1 is not None else None
    accel = round(med3 - .6 * med5, 3) if med3 is not None and med5 is not None else None
    quality = ("LOW_SAMPLE" if core_count < 5 else
               "INSUFFICIENT_COVERAGE" if coverage is None or coverage < .8 else "OK")
    strong = bool(quality == "OK" and breadth >= .6 and med1 >= .5 and rs >= .8)
    emerging = bool(quality == "OK" and breadth >= .6 and med1 >= .35
                    and rs >= .3 and accel is not None and accel >= .35)
    channels = (["STRONG"] if strong else []) + (["EMERGING"] if emerging else [])
    # Core-only sector breakdown; related sectors never inflate trend evidence.
    industry_rows = []
    for code in core:
        observations = [stock_data[x]["r1"] for x in groups[code]
                        if stock_data.get(x) is not None]
        industry_rows.append({"code": code, "n": len(groups[code]),
                              "valid": len(observations),
                              "breadth_1d": _pct(sum(x > 0 for x in observations), len(observations)),
                              "median_return_1d_pct": _med(observations)})
    valid_breadths = [x["breadth_1d"] for x in industry_rows if x["valid"] >= 5
                      and x["breadth_1d"] is not None]
    divergence = round(max(valid_breadths) - min(valid_breadths), 4) if len(valid_breadths) >= 2 else None
    return {
        "theme_id": theme["theme_id"], "theme_name": theme["theme_name"],
        "core_industry_codes": core, "related_industry_codes_not_scored": related,
        "core_industries": industry_rows, "core_stock_count": core_count,
        "usable_stock_count": usable, "quote_coverage": coverage,
        "sample_quality": quality, "median_return_1d_pct": med1,
        "median_return_3d_pct": med3, "median_return_5d_pct": med5,
        "breadth_1d": breadth, "breadth_3d": breadth3, "breadth_5d": breadth5,
        "relative_strength_1d_vs_market_median_pct": rs,
        "median_volume_ratio_vs_20d": medvolume,
        "acceleration_3d_vs_5d": accel, "industry_breadth_gap": divergence,
        "channels": channels
    }


def build(latest, industry_index, structure, catalog, registry=None, sector_audit=None,
          max_research=12, max_unmapped=8, retrospective=False):
    trade_date = str(latest.get("trade_date") or "")
    if not trade_date or latest.get("market_status") != "closed":
        raise ValueError("completed_market_session_required")
    if str(structure.get("reference_trade_date") or "") != trade_date:
        raise ValueError("structure_date_mismatch")
    if max_research < 1 or max_unmapped < 0:
        raise ValueError("invalid_review_limits")
    groups, names = _industry_map(industry_index)
    is_retrospective = _validate_catalog(catalog, trade_date, names, retrospective)
    if sector_audit is not None and (
        sector_audit.get("trade_date") != trade_date or
        sector_audit.get("industry_count", 0) != len(groups)
    ):
        raise ValueError("sector_audit_date_or_coverage_mismatch")
    if registry is not None and (
        registry.get("result_kind") != "a_share_trend_registry"
        or not registry.get("trade_date") or registry["trade_date"] > trade_date
    ):
        raise ValueError("future_or_invalid_registry_baseline")

    stock_codes = set().union(*groups.values())
    features = {code: stock_features(code, latest, structure, trade_date) for code in stock_codes}
    valid = [row["r1"] for row in features.values() if row is not None]
    if not valid or len(valid) / len(stock_codes) < .9:
        raise ValueError("mapped_quote_coverage_below_90pct")
    market_median = median(valid)

    detailed = [_theme_metrics(theme, groups, features, market_median)
                for theme in catalog["themes"]]
    eligible = [x for x in detailed if x["channels"]]
    # Compact research-input order only, not trend priority or new-position rank.
    def candidate_key(t):
        return (
            "STRONG" not in t["channels"],
            -(t["relative_strength_1d_vs_market_median_pct"] or 0),
            -(t["breadth_1d"] or 0), t["theme_id"]
        )
    eligible.sort(key=candidate_key)
    candidates = eligible[:max_research]
    def brief(t):
        return {k: v for k, v in t.items() if k not in ("core_industries",)}
    research = [brief(t) for t in candidates]

    identity = {}
    for theme in catalog["themes"]:
        for n in [theme["theme_name"], *(theme.get("aliases") or [])]:
            if n in identity and identity[n] != theme["theme_id"]:
                raise ValueError("alias_collision:" + n)
            identity[n] = theme["theme_id"]
    by_id = {t["theme_id"]: t for t in detailed}
    alerts, unknown_history = [], []
    if registry:
        for row in registry.get("trends") or []:
            if row.get("lifecycle_status") == "已失效":
                continue
            name = row.get("trend_name")
            tid = identity.get(name)
            if not tid:
                unknown_history.append(name)
                continue
            theme = by_id[tid]
            reasons = []
            if theme["sample_quality"] != "OK":
                reasons.append("LOW_QUALITY")
            if (theme["breadth_1d"] is not None
                and theme["breadth_1d"] <= .35
                and theme["median_return_1d_pct"] is not None
                and theme["median_return_1d_pct"] < -.5):
                reasons.append("WEAK_BREADTH_AND_PRICE")
            if (theme["relative_strength_1d_vs_market_median_pct"] is not None
                and theme["relative_strength_1d_vs_market_median_pct"] <= -1.5):
                reasons.append("RELATIVE_UNDERPERFORMANCE")
            if (theme["industry_breadth_gap"] is not None
                and theme["industry_breadth_gap"] >= .5):
                reasons.append("CORE_INDUSTRY_DIVERGENCE")
            if reasons:
                alerts.append({
                    "theme_id": tid, "theme_name": name,
                    "reason_codes": reasons, "evidence": brief(theme),
                    "note": "Review under legacy model rules; never auto-invalidate a theme."
                })

    unmapped, total_unmapped = [], 0
    covered_sectors = {i["code"] for t in catalog["themes"] for i in t["industries"]}
    if sector_audit:
        rows = sorted(
            (r for r in (sector_audit.get("sectors") or [])
             if r.get("kind") == "industry" and r.get("channels")
             and r.get("sample_quality") == "OK"
             and str(r.get("id") or "").split(":")[-1] not in covered_sectors),
            key=lambda r: (-r.get("score", 0), r.get("id", ""))
        )
        total_unmapped = len(rows)
        unmapped = [
            {"industry_code": r["id"].split(":", 1)[1], "industry_name": r["name"],
             "channels": r["channels"], "member_count": r["member_count"],
             "median_return_1d_pct": r["median_1d_pct"],
             "advance_ratio": r["advance_ratio"],
             "relative_strength_1d_vs_market_median_pct":
                 r["relative_1d_vs_market_median_pct"],
             "note": "No validated catalog relationship; legacy model must independently research."}
            for r in rows[:max_unmapped]
        ]
    status = "RETROSPECTIVE_MAPPING_SMOKE" if is_retrospective else "COMPLETE"
    return {
        "schema_version": 1, "result_kind": "a_share_theme_evidence_snapshot",
        "trade_date": trade_date, "generated_at": datetime.now(TZ).isoformat(),
        "status": status, "no_trade_signal": True, "auxiliary_only": True,
        "decision_authority": "legacy_model_driven_trend_research",
        "catalog_version": catalog["catalog_version"],
        "catalog_as_of_date": catalog["catalog_as_of_date"],
        "mapping_semantics": "core_only_deduplicated_stocks;related_research_only",
        "point_in_time_eligible": not is_retrospective,
        "scan_summary": {
            "industry_universe_count": len(groups), "themes_evaluated": len(detailed),
            "themes_with_eligible_quant_signals": len(eligible),
            "research_candidates_returned": len(research),
            "research_candidates_deferred": len(eligible) - len(research),
            "tracked_alert_count": len(alerts),
            "unmapped_industry_alert_count": len(unmapped),
            "unmapped_eligible_industry_count": total_unmapped,
            "unknown_tracked_themes": unknown_history,
            "invalid_or_low_sample_themes": sum(t["sample_quality"] != "OK" for t in detailed),
            "sector_audit_status": "MATCHED" if sector_audit else "UNAVAILABLE",
            "registry_baseline_trade_date": registry["trade_date"] if registry else None,
            "all_theme_detail_retention": "computed_in_memory_not_persisted"
        },
        "research_candidates": research,
        "tracked_theme_alerts": alerts,
        "unmapped_industry_alerts": unmapped,
        "disclaimer": "Quantitative cross-check and gap detection only. No T0/T1/T2, trade signal, formal theme rank, or handoff."
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--latest", default="data/latest.json")
    p.add_argument("--industry-index", default="data/research/company_industry_index.json")
    p.add_argument("--structure", default="data/research/full_market_price_structure.json")
    p.add_argument("--catalog", default="research/theme_industry_catalog.json")
    p.add_argument("--registry", default="research/trend_registry.json")
    p.add_argument("--sector-audit", default="data/research/sector_discovery_audit.json")
    p.add_argument("--output", default="data/research/theme_evidence_snapshot.json")
    p.add_argument("--max-research", type=int, default=12)
    p.add_argument("--max-unmapped", type=int, default=8)
    p.add_argument("--allow-retrospective-smoke", action="store_true")
    args = p.parse_args()
    output = Path(args.output)
    if args.allow_retrospective_smoke and output.resolve() == Path(
            "data/research/theme_evidence_snapshot.json").resolve():
        p.error("retrospective smoke cannot overwrite the production evidence snapshot")
    catalog = read_json(args.catalog)
    registry = read_json(args.registry) if Path(args.registry).exists() else None
    audit = read_json(args.sector_audit) if Path(args.sector_audit).exists() else None
    snapshot = build(read_json(args.latest), read_json(args.industry_index),
                     read_json(args.structure), catalog, registry, audit,
                     args.max_research, args.max_unmapped, args.allow_retrospective_smoke)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({"trade_date": snapshot["trade_date"], "status": snapshot["status"],
                      "evaluated": snapshot["scan_summary"]["themes_evaluated"],
                      "candidates": len(snapshot["research_candidates"]),
                      "tracked_alerts": len(snapshot["tracked_theme_alerts"]),
                      "unmapped": len(snapshot["unmapped_industry_alerts"])},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
