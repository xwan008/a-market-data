#!/usr/bin/env python3
"""Validate the independent observation/commodity track alongside the A-share registry.

The context is descriptive research, NEVER a source of buy-handoff eligibility.
Read its previous version when validating a new close to avoid silent erasure.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
INDUSTRY = re.compile(r"^S\d{6}$")
SOURCE = re.compile(r"^https?://\S+$|^(?:data|research)/[\w./-]+$")
OBSERVE = {"观察"}
COMMODITY_STATES = {"观察", "候选趋势", "趋势确认", "高潮/衰退", "失效"}


def _date(v, day):
    return isinstance(v, str) and bool(DATE.fullmatch(v)) and v <= day


def _evidence_valid(rows, day):
    return (isinstance(rows, list) and len(rows) > 0 and
            all(isinstance(e, dict) and _date(e.get("trade_date"), day) and
                isinstance(e.get("source"), str) and bool(SOURCE.fullmatch(e["source"])) and
                isinstance(e.get("description"), str) and len(e["description"].strip()) >= 8
                for e in rows))


def _items(doc, key):
    items = doc.get(key)
    return items if isinstance(items, list) else None


def validate(registry, context, previous_context=None):
    errors = []
    if context.get("schema_version") != 1 or context.get("result_kind") != "a_share_trend_context":
        errors.append("context_schema_invalid")
    day = registry.get("trade_date")
    if (registry.get("result_kind") != "a_share_trend_registry" or
        registry.get("status") != "COMPLETE" or
        not _date(day, day) or context.get("trade_date") != day):
        errors.append("context_registry_trade_date_mismatch")
        return errors
    if context.get("status") != "COMPLETE":
        errors.append("context_not_complete")
    observations = _items(context, "observations")
    commodities = _items(context, "commodity_trends")
    if observations is None or commodities is None:
        return errors + ["context_collections_invalid"]
    active = {t.get("trend_name") for t in registry.get("trends", []) if isinstance(t, dict)}
    ids = set()
    for obs in observations:
        if not isinstance(obs, dict):
            errors.append("observation_entry_invalid")
            continue
        name, episode = obs.get("trend_name"), obs.get("episode_id")
        if (not isinstance(name, str) or not name or
            obs.get("market_state") not in OBSERVE or
            episode != f"{name}#{obs.get('first_seen_trade_date')}" or
            not _date(obs.get("first_seen_trade_date"), day) or
            not _date(obs.get("last_verified_trade_date"), day) or
            obs["last_verified_trade_date"] < obs["first_seen_trade_date"]):
            errors.append(f"{name}:observation_identity_invalid")
        if name in active:
            errors.append(f"{name}:observation_also_in_active_trends")
        if episode in ids:
            errors.append("observation_duplicate_episode")
        ids.add(episode)
        codes, labels = obs.get("industry_codes"), obs.get("industry_names")
        if (not isinstance(codes, list) or not codes or
            not all(isinstance(c, str) and INDUSTRY.fullmatch(c) for c in codes) or
            not isinstance(labels, list) or len(codes) != len(labels) or
            not all(isinstance(n, str) and n.strip() for n in labels)):
            errors.append(f"{name}:industry_identity_invalid")
        if not _evidence_valid(obs.get("evidence"), day):
            errors.append(f"{name}:observation_evidence_invalid")
        if not isinstance(obs.get("next_check"), str) or not obs["next_check"].strip():
            errors.append(f"{name}:next_check_missing")
    commodity_ids = set()
    for item in commodities:
        if not isinstance(item, dict):
            errors.append("commodity_entry_invalid")
            continue
        identity = item.get("commodity_id")
        if (not isinstance(identity, str) or not identity or identity in commodity_ids):
            errors.append("commodity_duplicate_or_missing_id")
        commodity_ids.add(identity)
        if (item.get("market_state") not in COMMODITY_STATES or
            not isinstance(item.get("commodity_name"), str) or
            not item["commodity_name"].strip() or
            not _date(item.get("last_verified_trade_date"), day) or
            not _date(item.get("first_seen_trade_date"), day) or
            item["first_seen_trade_date"] > item["last_verified_trade_date"]):
            errors.append(f"{identity}:commodity_identity_invalid")
        quote = item.get("price_anchor")
        if (not isinstance(quote, dict) or not _date(quote.get("trade_date"), day) or
            not isinstance(quote.get("value"), (int, float)) or isinstance(quote.get("value"), bool) or
            not 0 < quote["value"] < 1000000 or
            not all(isinstance(quote.get(k), str) and quote[k].strip()
                    for k in ("instrument", "contract", "unit", "price_basis")) or
            not isinstance(quote.get("source"), str) or not SOURCE.fullmatch(quote["source"])):
            errors.append(f"{identity}:price_anchor_invalid")
        if not _evidence_valid(item.get("evidence"), day):
            errors.append(f"{identity}:commodity_evidence_invalid")
        links = item.get("a_share_industries")
        if (not isinstance(links, list) or
            not all(isinstance(link, dict) and INDUSTRY.fullmatch(str(link.get("industry_code", ""))) and
                    isinstance(link.get("industry_name"), str) and link["industry_name"]
                    for link in links)):
            errors.append(f"{identity}:industry_link_invalid")
        if not isinstance(item.get("next_check"), str) or not item["next_check"].strip():
            errors.append(f"{identity}:next_check_missing")
    if previous_context is not None:
        before = previous_context.get("trade_date")
        if (previous_context.get("result_kind") != "a_share_trend_context" or
            not _date(before, day) or before >= day):
            errors.append("previous_context_invalid")
            return errors
        transitions = _items(context, "transitions")
        if transitions is None:
            errors.append("transitions_missing")
            transitions = []
        transitions_by_id = {}
        for transition in transitions:
            if not isinstance(transition, dict):
                errors.append("transition_invalid")
                continue
            key = (transition.get("kind"), transition.get("id"))
            if key in transitions_by_id:
                errors.append("duplicate_context_transition")
            transitions_by_id[key] = transition
        for key, field, id_key in (("observation", "observations", "episode_id"),
                                    ("commodity", "commodity_trends", "commodity_id")):
            old_items = {x.get(id_key): x for x in previous_context.get(field, [])
                         if isinstance(x, dict)}
            new_items = {x.get(id_key): x for x in context.get(field, [])
                         if isinstance(x, dict)}
            for identity, prev in old_items.items():
                if identity in new_items:
                    curr = new_items[identity]
                    if (curr.get("first_seen_trade_date") != prev.get("first_seen_trade_date") or
                        (key == "observation" and curr.get("trend_name") != prev.get("trend_name")) or
                        (key == "commodity" and curr.get("commodity_name") != prev.get("commodity_name"))):
                        errors.append(f"{identity}:context_identity_rewritten")
                    if curr.get("last_verified_trade_date", "") < prev.get("last_verified_trade_date", ""):
                        errors.append(f"{identity}:context_verification_regressed")
                else:
                    transition = transitions_by_id.get((key, identity))
                    if (not transition or transition.get("action") not in {"PROMOTED", "EXITED"} or
                        not isinstance(transition.get("reason"), str) or
                        len(transition["reason"].strip()) < 12 or
                        not _evidence_valid(transition.get("evidence"), day)):
                        errors.append(f"{identity}:silently_removed")
                    elif key == "observation" and transition["action"] == "PROMOTED":
                        matching = [t for t in registry.get("trends", [])
                                    if t.get("trend_name") == prev.get("trend_name")]
                        if len(matching) != 1 or matching[0].get("source_observation_episode_id") != identity:
                            errors.append(f"{identity}:promotion_link_missing")
    return errors


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--registry", required=True)
    p.add_argument("--context", required=True)
    p.add_argument("--previous-context")
    args = p.parse_args()
    try:
        read = lambda path: json.loads(Path(path).read_text(encoding="utf-8"))
        errs = validate(read(args.registry), read(args.context),
                        read(args.previous_context) if args.previous_context else None)
    except (OSError, ValueError, TypeError) as exc:
        errs = ["input_error:" + str(exc)]
    print(json.dumps({"status": "PASS" if not errs else "BLOCKED", "errors": errs},
                     ensure_ascii=False))
    return 0 if not errs else 1


if __name__ == "__main__":
    raise SystemExit(main())
