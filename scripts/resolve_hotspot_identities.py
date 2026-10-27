#!/usr/bin/env python3
"""Resolve independently FROZEN hotspots to a verified industry or concept identity.

This does not discover hotspots, rank trends, or assign market/T stage. A market
state must be adjudicated later from identity-correct market and industry facts.
Name similarities and price momentum are NEVER sufficient to establish identity.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo
from pathlib import Path

SW_CODE = re.compile(r"^S\d{6}$")
CODE = re.compile(r"^\d{6}$")
MAINBOARD = ("600", "601", "603", "605", "000", "001", "002", "003")
KINDS = {"INDUSTRY_ECONOMICS", "TECHNOLOGY_CATALYST", "UNKNOWN"}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def evidence_valid(materials, trade_date):
    if not isinstance(materials, list) or not materials:
        return False
    for e in materials:
        if not isinstance(e, dict):
            return False
        source = str(e.get("source") or "")
        stamp = str(e.get("published_at") or "")
        claim = str(e.get("claim") or "").strip()
        try:
            if not stamp or date.fromisoformat(stamp) > date.fromisoformat(trade_date):
                return False
        except ValueError:
            return False
        if not claim or not (source.startswith("https://") or source.startswith("data/") or
                             source.startswith("research/")):
            return False
    return True


def validate_registry(registry):
    if (registry.get("schema_version") != 1 or
            registry.get("result_kind") != "verified_hotspot_identity_registry"):
        raise ValueError("IDENTITY_REGISTRY_SCHEMA_INVALID")
    index = {}
    aliases = {}
    for entry in registry.get("entries", []):
        name, code, kind = (entry.get("canonical_name"), entry.get("board_code"),
                            entry.get("board_type"))
        if (not name or not code or kind not in ("INDUSTRY", "THEME") or
                (not CODE.fullmatch(code) if kind == "THEME" else not SW_CODE.fullmatch(code))):
            raise ValueError("IDENTITY_REGISTRY_ENTRY_INVALID")
        identity = (kind, code)
        if identity in index:
            raise ValueError("IDENTITY_REGISTRY_DUPLICATE_CODE")
        index[identity] = entry
        for alias in [name] + (entry.get("aliases") or []):
            aliases.setdefault(alias, set()).add(identity)
    return index, aliases


def verify_concept_members(catalog, trade_date, code, source=None):
    if catalog is None:
        return "DATA_INSUFFICIENT", None, "CONCEPT_MEMBERSHIP_NOT_AVAILABLE"
    if (catalog.get("schema_version") != 1 or
            catalog.get("as_of_trade_date") != trade_date or not catalog.get("source") or
            (source is not None and catalog.get("source") != source)):
        return "DATA_INSUFFICIENT", None, "CONCEPT_MEMBERSHIP_DATE_OR_SOURCE_INVALID"
    rows = [r for r in catalog.get("concepts", []) if str(r.get("concept_id")) == code]
    if len(rows) != 1:
        return "DATA_INSUFFICIENT", None, "CONCEPT_CODE_NOT_IN_VERIFIED_SNAPSHOT"
    row = rows[0]
    codes = row.get("member_codes")
    if (not isinstance(codes, list) or not codes or
            len(codes) != len(set(codes)) or
            any(not CODE.fullmatch(str(c)) for c in codes)):
        return "DATA_INSUFFICIENT", None, "CONCEPT_MEMBER_CODES_INVALID"
    return "VERIFIED", [c for c in codes if c.startswith(MAINBOARD)], "CONCEPT_MEMBERS_VERIFIED"


def resolve(discovery, registry, catalog=None, industry_index=None, resolved_at=None):
    if (discovery.get("schema_version") != 1 or
            discovery.get("result_kind") != "independent_hotspot_discovery_frozen" or
            discovery.get("discovery_stage") != "FROZEN_BEFORE_HISTORICAL_REVIEW" or
            not discovery.get("frozen_at") or
            not isinstance(discovery.get("hotspots"), list)):
        raise ValueError("INDEPENDENT_DISCOVERY_NOT_FROZEN")
    trade_date = str(discovery.get("trade_date") or "")
    try:
        date.fromisoformat(trade_date)
        if not discovery["frozen_at"].startswith(trade_date):
            raise ValueError("DISCOVERY_FREEZE_DATE_MISMATCH")
    except ValueError:
        raise ValueError("DISCOVERY_DATE_INVALID")
    if resolved_at is None:
        resolved_at = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
    try:
        if datetime.fromisoformat(resolved_at) < datetime.fromisoformat(discovery["frozen_at"]):
            raise ValueError("IDENTITY_RESOLUTION_BEFORE_DISCOVERY_FREEZE")
    except (TypeError, ValueError) as ex:
        raise ValueError("IDENTITY_RESOLUTION_TIMESTAMP_INVALID") from ex
    index, aliases = validate_registry(registry)
    out = []
    used = set()
    for item in discovery["hotspots"]:
        key = str(item.get("hotspot_id") or "")
        name = str(item.get("hotspot_name") or "").strip()
        if not key or key in used or not name:
            raise ValueError("HOTSPOT_ID_DUPLICATE_OR_MISSING")
        used.add(key)
        origin = item.get("origin") or {}
        driver = item.get("driver") or {}
        driver_kind = driver.get("kind")
        if driver_kind not in KINDS:
            raise ValueError("HOTSPOT_DRIVER_KIND_INVALID")
        original = {
            "hotspot_id": key, "hotspot_name": name,
            "driver_kind": driver_kind,
            "driver_evidence": driver.get("sources") or [],
            "industry_seed_codes": item.get("industry_seed_codes") or [],
            "representative_codes": item.get("representative_codes") or [],
        }
        if any(not SW_CODE.fullmatch(str(c)) for c in original["industry_seed_codes"]):
            raise ValueError("HOTSPOT_SW_SEED_CODES_INVALID")
        if any(not CODE.fullmatch(str(c)) for c in original["representative_codes"]):
            raise ValueError("HOTSPOT_REPRESENTATIVES_INVALID")
        kind = origin.get("board_type")
        code = str(origin.get("board_code") or "")
        origin_source = str(origin.get("source") or "")
        if kind not in ("INDUSTRY", "THEME", "UNSPECIFIED"):
            raise ValueError("HOTSPOT_ORIGIN_TYPE_REQUIRED")
        choice = None
        issue = None
        candidates = []
        if not evidence_valid(driver.get("sources"), trade_date):
            issue = "ORIGINAL_DRIVER_EVIDENCE_MISSING"
        elif kind == "INDUSTRY":
            if (not SW_CODE.fullmatch(code) or origin_source != "SW2021_L3" or
                    driver_kind != "INDUSTRY_ECONOMICS" or
                    code not in original["industry_seed_codes"]):
                issue = "INDUSTRY_ORIGIN_OR_DRIVER_CONFLICT"
            else:
                companies = ((industry_index or {}).get("companies") or {})
                valid_industries = {
                    str(v.get("industry_code")) for c, v in companies.items()
                    if v.get("mapping_status") == "mapped" and
                       CODE.fullmatch(str(c).zfill(6))
                }
                if not valid_industries:
                    issue = "SW_MEMBERSHIP_NOT_AVAILABLE"
                elif not set(original["industry_seed_codes"]).issubset(valid_industries):
                    issue = "SW_INDUSTRY_CODES_NOT_IN_MEMBERSHIP_SOURCE"
                else:
                    choice = ("INDUSTRY", code)
        elif kind == "THEME":
            if (not CODE.fullmatch(code) or
                    driver_kind != "TECHNOLOGY_CATALYST" or
                    ("THEME", code) not in index or
                    origin_source != index[("THEME", code)]["source"] or
                    name not in [index[("THEME", code)]["canonical_name"]] + index[("THEME", code)].get("aliases", [])):
                issue = "CONCEPT_ORIGIN_OR_DRIVER_CONFLICT"
            else:
                choice = ("THEME", code)
        else:
            # Ambiguous "机器人" is NOT automatically "人形机器人".
            candidates = sorted([list(identity) for identity in aliases.get(name, set())])
            if len(candidates) == 1:
                unique = tuple(candidates[0])
                registered = index[unique]
                required = ("INDUSTRY_ECONOMICS" if unique[0] == "INDUSTRY"
                            else "TECHNOLOGY_CATALYST")
                if (driver_kind == required and
                        str(driver.get("target_board_code") or "") == unique[1]):
                    choice = unique
                else:
                    issue = "HOTSPOT_IDENTITY_DRIVE_AMBIGUOUS"
            else:
                issue = "HOTSPOT_IDENTITY_NOT_UNIQUELY_MATCHED"
        member_codes = None
        if choice and choice[0] == "THEME":
            verdict, members, reason = verify_concept_members(
                catalog, trade_date, choice[1], index[choice]["source"])
            if verdict != "VERIFIED":
                issue = reason
            else:
                member_codes = members
                if not members:
                    issue = "CONCEPT_HAS_NO_SH_SZ_MAINBOARD_STOCKS"
        if issue:
            state = ("DATA_INSUFFICIENT" if (
                (issue.startswith("CONCEPT_") and issue != "CONCEPT_ORIGIN_OR_DRIVER_CONFLICT") or
                issue.startswith("SW_MEMBERSHIP_") or
                issue.startswith("SW_INDUSTRY_CODES_NOT_IN_")
            ) else "MAPPING_UNRESOLVED")
            choice = None
        else:
            state = "VERIFIED"
        result = {
            **original,
            "mapping_status": state,
            "mapping_reason": issue or "SOURCE_AND_DRIVER_EVIDENCE_VERIFIED",
            "board_type": choice[0] if choice else None,
            "board_code": choice[1] if choice else None,
            "origin_source": origin_source,
            "identity_candidates": candidates,
            "market_scope": "SH_SZ_MAINBOARD_ONLY",
            "industry_codes": original["industry_seed_codes"] if choice and choice[0] == "INDUSTRY" else [],
            "concept_code": choice[1] if choice and choice[0] == "THEME" else None,
            "concept_mainboard_member_count": len(member_codes) if member_codes is not None else None,
        }
        out.append(result)
    return {
        "schema_version": 1,
        "result_kind": "hotspot_identity_snapshot",
        "trade_date": trade_date,
        "discovery_frozen_at": discovery["frozen_at"],
        "resolved_at": resolved_at,
        "market_scope": "SH_SZ_MAINBOARD_ONLY",
        "status": "COMPLETE" if all(x["mapping_status"] == "VERIFIED" for x in out)
                  else "NEEDS_IDENTITY_REVIEW",
        "identities": out,
        "does_not_assign_market_or_industry_trend_state": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--discovery", required=True)
    parser.add_argument("--registry", default="research/hotspot_identity_registry.json")
    parser.add_argument("--concept-file", default=None)
    parser.add_argument("--industry-index",default="data/research/company_industry_index.json")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    payload = resolve(read(args.discovery), read(args.registry),
                      read(args.concept_file) if args.concept_file else None,
                      read(args.industry_index))
    p = Path(args.output)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(p), "status": payload["status"],
        "types": [(x["hotspot_name"], x["mapping_status"], x["board_type"], x["board_code"])
                  for x in payload["identities"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
