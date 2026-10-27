"""Coverage hints only: no trend/routing authority and no invented external quotes."""
from collections import defaultdict
from datetime import datetime
from statistics import median
import math


def _number(x):
    try:
        n = float(x)
        return n if not isinstance(x, bool) and math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def _cutoff_ok(value, day):
    try:
        d = datetime.fromisoformat(value)
        cutoff = datetime.fromisoformat(day + "T18:30:00+08:00")
        return d.tzinfo is not None and d.utcoffset() is not None and d <= cutoff
    except (TypeError, ValueError, OverflowError):
        return False


def _feed(payload, trade_date, key):
    if payload is None:
        return "UNAVAILABLE_NO_VERIFIED_SOURCE", []
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError(key + "_schema_invalid")
    day = payload.get("as_of_trade_date")
    if not isinstance(day, str) or len(day) != 10:
        raise ValueError(key + "_date_invalid")
    if day > trade_date:
        raise ValueError(key + "_future_data")
    if day < trade_date:
        return "STALE_NOT_USED", []
    if not isinstance(payload.get("source"), str) or not payload["source"].strip() or not isinstance(payload.get(key), list):
        raise ValueError(key + "_provenance_missing")
    return "DATED_SOURCE_DECLARED_NOT_INDEPENDENTLY_VERIFIED", payload[key]


def build_coverage_review(rows, trade_date, selected_ids, sw2=None, anchors=None):
    """Supplementary hints unbounded by top three. Thresholds are NOT state gates."""
    industries = {r["id"].split(":", 1)[1]: r for r in rows
                  if r.get("kind") == "industry" and r.get("id", "").startswith("industry:S")}
    groups = defaultdict(list)
    for code, r in industries.items():
        if len(code) == 7 and code[1:].isdigit():
            groups[code[1:5]].append(r)
    index_status, index_rows = _feed(sw2, trade_date, "indices")
    price_status, price_rows = _feed(anchors, trade_date, "anchors")
    indices = {}
    for x in index_rows:
        if not isinstance(x, dict):
            raise ValueError("indices_invalid_row")
        code = x.get("sw_level2_code")
        if (not isinstance(code, str) or len(code) != 6 or not code.isdigit()
                or not code.endswith("00") or code in indices
                or _number(x.get("return_1d_pct")) is None
                or not isinstance(x.get("source"), str) or not x["source"].strip()
                or not _cutoff_ok(x.get("quote_at"), trade_date)):
            raise ValueError("indices_invalid_source_or_cutoff")
        indices[code] = x
    parents = []
    for key, members in sorted(groups.items()):
        vals = [r["median_1d_pct"] for r in members if _number(r.get("median_1d_pct")) is not None]
        if not vals:
            continue
        official = indices.get(key + "00")
        actual = _number(official["return_1d_pct"]) if official else None
        proxy = round(median(vals), 3)
        gap = round(actual - proxy, 3) if actual is not None else None
        discrepancy = (actual is not None and actual >= .5 and gap >= .8
                       and sum((r.get("advance_ratio") or 0) < .5 for r in members) > len(members) / 2)
        parents.append({
            "sw_level2_code": key + "00", "classification_only": True,
            "child_sw3_count": len(members), "sw3_codes": sorted(r["id"].split(":")[1] for r in members),
            "median_of_sw3_medians_1d_pct": proxy,
            "official_index_1d_pct": actual, "official_index_source": official.get("source") if official else None,
            "index_quote_at": official.get("quote_at") if official else None,
            "index_vs_sw3_proxy_gap_pct": gap, "flag": "INDEX_L3_DIVERGENCE" if discrepancy else None,
        })
    watch = []
    for code, r in sorted(industries.items()):
        if r.get("sample_quality") != "OK" or r.get("usable_count", 0) < 5:
            continue
        day, rel, d3, d5 = [_number(r.get(k)) for k in
                            ("median_1d_pct", "relative_1d_vs_market_median_pct",
                             "median_3d_pct", "median_5d_pct")]
        b1, b3, b5, vol = [_number(r.get(k)) for k in
                            ("advance_ratio", "breadth_3d", "breadth_5d",
                             "median_volume_ratio_vs_20d")]
        flags = []
        if all(v is not None for v in (day, rel, d3, b1)) and (
                rel >= 1.5 and day >= -.5 and b1 < .5 and d3 > 0):
            flags.append("RELATIVE_BREADTH_DIVERGENCE")
        if all(v is not None for v in (rel, d3, d5, b3, b5, vol)) and (
                rel > 0 and d3 >= 2 and d5 >= 1 and b3 >= .6 and b5 >= .5 and vol >= 1.15):
            flags.append("PERSISTENT_STRUCTURE")
        if flags:
            watch.append({"industry_code": code, "name": r["name"], "flags": flags,
                          "selected_in_top3": r["id"] in selected_ids,
                          "program_channels": r.get("channels", []),
                          "source": "data/research/sector_discovery_audit.json#sectors",
                          "sample_quality": r["sample_quality"], "market_state_authority": False})
    prices = []
    used = set()
    for r in price_rows:
        if not isinstance(r, dict):
            raise ValueError("anchors_invalid_row")
        aid, codes = r.get("anchor_id"), r.get("research_sw3_codes")
        if (not isinstance(aid, str) or not aid or aid in used
                or not isinstance(codes, list) or not codes or len(set(codes)) != len(codes)
                or any(c not in industries for c in codes)
                or not all(isinstance(r.get(k), str) and r[k].strip()
                           for k in ("instrument", "market", "price_basis", "unit", "source"))
                or _number(r.get("price")) is None or _number(r.get("price")) <= 0
                or not _cutoff_ok(r.get("quote_at"), trade_date)):
            raise ValueError("anchors_invalid_source_or_cutoff")
        used.add(aid)
        change = _number(r.get("change_5d_pct"))
        linked = [industries[c].get("median_5d_pct") for c in codes]
        eligible = [v for v in linked if _number(v) is not None]
        prices.append({
            "anchor_id": aid, "instrument": r["instrument"], "market": r["market"],
            "price_basis": r["price_basis"], "price": r["price"], "unit": r["unit"],
            "quote_at": r["quote_at"], "source": r["source"],
            "change_5d_pct": change, "research_sw3_codes": codes,
            "price_vs_equity_divergence": bool(change is not None and change >= 2
                                               and eligible and median(eligible) <= 0),
            "beneficiary_verified": False, "market_state_authority": False,
        })
    gaps = []
    if index_status != "DATED_SOURCE_DECLARED_NOT_INDEPENDENTLY_VERIFIED":
        gaps.append("sw2_index_" + index_status)
    if price_status != "DATED_SOURCE_DECLARED_NOT_INDEPENDENTLY_VERIFIED":
        gaps.append("price_anchors_" + price_status)
    return {
        "trade_date": trade_date, "role": "AUXILIARY_ONLY_NO_FORMAL_DECISIONS",
        "thresholds_not_state_gates": True, "changes_handoff": False,
        "sw2_feed_status": index_status, "price_feed_status": price_status,
        "sw2_classification_note": "SW3 taxonomy grouping is not an official SW2 index",
        "sw2_parent_reviews": parents, "sw3_watch_hints": watch, "price_anchor_hints": prices,
        "counts": {"sw2_groups": len(parents), "official_indices": len(indices),
                   "index_discrepancies": sum(x["flag"] is not None for x in parents),
                   "sw3_extra_hints": len(watch),
                   "not_in_top3": sum(not x["selected_in_top3"] for x in watch),
                   "price_anchors": len(prices)},
        "data_gaps": gaps,
    }
