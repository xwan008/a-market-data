#!/usr/bin/env python3
"""Fail-closed ADDITIONAL publication check for identity-first 18:30 reviews.

Does not replace the existing trend migration or registry/handoff pair gates.
Never creates status, upgrades T-stage, or touches the official registry.
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def checked_timestamp(raw, label):
    try:
        stamp = datetime.fromisoformat(str(raw))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError("missing timezone")
        return stamp
    except (ValueError, TypeError) as ex:
        raise ValueError("TIMESTAMP_INVALID:" + label) from ex


def validate(discovery, identity, market, registry, handoff):
    day = discovery.get("trade_date")
    if not day or any(obj.get("trade_date") != day
                      for obj in (identity,market,registry,handoff)):
        raise ValueError("PROPOSED_TREND_DATE_INCONSISTENT")
    if (discovery.get("result_kind") != "independent_hotspot_discovery_frozen" or
            discovery.get("discovery_stage") != "FROZEN_BEFORE_HISTORICAL_REVIEW" or
            identity.get("result_kind") != "hotspot_identity_snapshot" or
            market.get("result_kind") != "mapped_hotspot_market_evidence" or
            handoff.get("result_kind") != "a_share_trend_handoff"):
        raise ValueError("IDENTITY_EVIDENCE_PUBLICATION_CONTRACT_INVALID")
    if (registry.get("scan_audit",{}).get("independent_discovery_frozen_at") !=
            discovery.get("frozen_at") or
            identity.get("discovery_frozen_at") != discovery.get("frozen_at")):
        raise ValueError("INDEPENDENT_FREEZE_NOT_PROVEN")
    if (market.get("may_assign_trend_or_market_state") is not False or
            handoff.get("source",{}).get("identity_verified_before_state") is not True or
            identity.get("market_scope") != "SH_SZ_MAINBOARD_ONLY" or
            market.get("market_scope") != "SH_SZ_MAINBOARD_ONLY"):
        raise ValueError("IDENTITY_FIRST_STATE_ADJUDICATION_NOT_PROVEN")
    frozen = checked_timestamp(discovery["frozen_at"], "discovery")
    resolved = checked_timestamp(identity.get("resolved_at"), "identity")
    evaluated = checked_timestamp(market.get("generated_at"), "market_evidence")
    published = checked_timestamp(handoff.get("generated_at"), "handoff")
    if not frozen <= resolved <= evaluated <= published:
        raise ValueError("IDENTITY_EVIDENCE_PRODUCED_AFTER_STATE")
    by_name={x["hotspot_name"]:x for x in identity.get("identities",[])}
    evidence_by_name={x["hotspot_name"]:x for x in market.get("hotspots",[])}
    if (len(by_name)!=len(identity.get("identities",[])) or
            len(evidence_by_name)!=len(market.get("hotspots",[]))):
        raise ValueError("IDENTITY_OR_MARKET_EVIDENCE_DUPLICATE")
    baseline={x.get("trend_name"):x for x in registry.get("trends",[])}
    signals=handoff.get("signals") or []
    if len({x.get("trend_name") for x in signals}) != len(signals):
        raise ValueError("HANDOFF_DUPLICATE_TREND")
    for signal in signals:
        name=signal.get("trend_name")
        ident=by_name.get(name)
        fact=evidence_by_name.get(name)
        formal=baseline.get(name)
        if not ident or not fact or not formal:
            raise ValueError("PUBLISHED_TREND_IDENTITY_NOT_IN_PRESTATE_RESEARCH:"+str(name))
        if (ident["mapping_status"] != "VERIFIED" or
                fact.get("evaluation_status") != "READY_FOR_INDEPENDENT_STATE_REVIEW" or
                fact.get("market_state") is not None or
                fact.get("trend_state") is not None):
            raise ValueError("PUBLISHED_TREND_IDENTITY_OR_FACTS_UNVERIFIED:"+str(name))
        for pair in ((signal,formal), (signal,ident)):
            if (pair[0].get("board_type") != pair[1].get("board_type") or
                    pair[0].get("board_code") != pair[1].get("board_code")):
                raise ValueError("PUBLISHED_TREND_BOARD_IDENTITY_CHANGED:"+str(name))
        if (signal.get("trend_state") != formal.get("trend_state") or
                signal.get("market_state") != formal.get("market_state") or
                signal.get("market_state") not in ("趋势确认","候选趋势")):
            raise ValueError("PUBLISHED_TREND_STATES_NOT_MATCHED:"+str(name))
        if ident["board_type"]=="INDUSTRY":
            if signal.get("industry_codes") != ident.get("industry_codes"):
                raise ValueError("INDUSTRY_BOARD_CODES_MISMATCH:"+str(name))
        elif ident["board_type"]=="THEME":
            if signal.get("concept_code") != ident.get("concept_code"):
                raise ValueError("THEME_CODE_MISMATCH:"+str(name))
    return {"trade_date":day,"signals_verified":len(signals),
            "identity_scope":len(by_name),
            "identity_resolution_preceded_market_state":True}


def main():
    p=argparse.ArgumentParser()
    for option in ("discovery","identity","market-evidence","proposed-registry",
                   "proposed-handoff"):
        p.add_argument("--"+option,required=True)
    a=p.parse_args()
    result=validate(read(a.discovery),read(a.identity),read(a.market_evidence),
                    read(a.proposed_registry),read(a.proposed_handoff))
    print("HOTSPOT_IDENTITY_PUBLICATION_GATE_PASSED",json.dumps(result,ensure_ascii=False))


if __name__=="__main__":
    main()
