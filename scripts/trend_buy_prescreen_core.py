#!/usr/bin/env python3
"""Program-only prescreen for canonical trend-buy research. No model or trade action."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
MAX_RESEARCH_PER_INDUSTRY = 5
VERSION = "trend_buy_program_prescreen"


def number(value):
    return (isinstance(value, (float, int)) and not isinstance(value, bool)
            and math.isfinite(value))


def positive(value):
    return number(value) and value > 0


def percentile(values):
    """Ascending peer percentiles, midpoint for ties; missing stays UNKNOWN."""
    valid=sorted((v,i) for i,v in enumerate(values) if number(v))
    out=[None]*len(values)
    if len(valid)<3:
        return out
    for i,(value,index) in enumerate(valid):
        smaller=sum(v < value for v,_ in valid)
        equal=sum(v == value for v,_ in valid)
        out[index]=round((smaller+(equal-1)/2)/(len(valid)-1),6)
    return out


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def frozen_industry_rows(root, index, code, trade_date):
    """Same-day materialized SW3 chunks, never a current unfrozen re-query."""
    meta=(index.get("industries") or {}).get(code)
    if not meta or meta.get("layout")!="chunked_manifest_v1":
        raise ValueError("missing_frozen_industry_manifest:"+code)
    manifest_file=root/meta["manifest_file"]
    manifest=read_json(manifest_file)
    if manifest.get("trade_date")!=trade_date or manifest.get("industry_code")!=code:
        raise ValueError("industry_manifest_asof_mismatch:"+code)
    rows=[]
    for part in manifest["parts"]:
        path=root/part["file"]
        raw=path.read_bytes()
        if len(raw)!=part["byte_size"]:
            raise ValueError("frozen_chunk_bytes_changed:"+str(path))
        j=json.loads(raw)
        group=j.get("companies") or []
        if (j.get("trade_date")!=trade_date or j.get("industry_code")!=code
                or [r["code"] for r in group]!=part["company_codes"]):
            raise ValueError("frozen_chunk_identity_changed:"+str(path))
        rows.extend(group)
    if ([x["code"] for x in rows]!=manifest["universe_company_codes"]
            or len(rows)!=manifest["company_count"]):
        raise ValueError("frozen_universe_incomplete:"+code)
    return rows


def history_for(root, code, cache):
    prefix=code[:4]
    if prefix not in cache:
        path=root/"data/history_shards"/(prefix+".json")
        cache[prefix]=read_json(path) if path.exists() else {}
    return (cache[prefix].get("stocks") or {}).get(code) or {}


def completed_history(stock, date, frozen_price):
    raw=(stock.get("history") or [])
    rows=sorted((x for x in raw if isinstance(x.get("date"),str)
                 and x["date"]<=date),key=lambda r:r["date"])
    if (len(rows)<65 or rows[-1]["date"]!=date
            or len({r["date"] for r in rows})!=len(rows)
            or any(not positive(r.get("close")) or not positive(r.get("volume"))
                   for r in rows)):
        return None,"ASOF_HISTORY_MISSING_OR_INVALID"
    if abs(rows[-1]["close"]/frozen_price-1)>.015:
        return None,"ASOF_HISTORY_PRICE_BASIS_MISMATCH"
    return rows,None


def metrics(rows):
    closes=[r["close"] for r in rows]
    returns={str(h):round(100*(closes[-1]/closes[-1-h]-1),6)
             for h in (5,10,20,60)}
    up10=sum(closes[i]>closes[i-1] for i in range(len(closes)-10,len(closes)))
    peak=closes[-11]
    worst=0
    for p in closes[-10:]:
        peak=max(peak,p)
        worst=min(worst,100*(p/peak-1))
    vol20=median(r["volume"] for r in rows[-21:-1])
    day_volume_ratio=rows[-1]["volume"]/vol20 if vol20>0 else None
    return {
        "returns_pct":returns,
        "positive_days_10":up10,
        "max_close_drawdown_10_pct":round(worst,4),
        "volume_1d_vs_prior20_median":round(day_volume_ratio,4) if day_volume_ratio is not None else None,
        "extreme_recent_acceleration_observation":bool(
            returns["5"]>12 and day_volume_ratio is not None and day_volume_ratio>3),
    }


def select_company_rows(rows, audit_rows, date, root, history_cache,
                        known_unsupported=None):
    """Return evidence-complete members and diagnostics, not a model result."""
    known_unsupported=set(known_unsupported or [])
    audit={r["code"]:r for r in audit_rows}
    if len(audit)!=len(audit_rows):
        raise ValueError("duplicate_frozen_lightweight_screen")
    excluded=[]
    entries=[]
    for row in rows:
        code=row["code"]
        previous=audit.get(code)
        if previous is None:
            # The original hard-screen may have rejected this company; never
            # add a company without the original hard-filter audit.
            continue
        # A missing current entry setup is not a hard evidence exclusion.
        # It can enter research only as an explicitly labeled watch fallback.
        entry_observation=previous.get("opportunity") or {}
        entry_eligible=(previous.get("excluded_reason") is None
                        and number(entry_observation.get("entry_score"))
                        and number(entry_observation.get("price_structure_score")))
        if code in known_unsupported:
            excluded.append({"code":code,"reason":"PREVIOUSLY_VERIFIED_NOT_SUPPORTED"})
            continue
        if not positive(row.get("price")):
            excluded.append({"code":code,"reason":"FROZEN_PRICE_MISSING"})
            continue
        series,error=completed_history(history_for(root,code,history_cache),
                                      date,row["price"])
        if error:
            excluded.append({"code":code,"reason":error})
            continue
        f=metrics(series)
        if previous.get("industry_code")!=row.get("industry_code"):
            raise ValueError("frozen_lightweight_industry_mismatch:"+code)
        if not number(previous.get("fundamental_score")):
            excluded.append({"code":code,"reason":"FUNDAMENTAL_NOT_VERIFIED"})
            continue
        ocf=row.get("operating_cashflow_per_share")
        core_available=number(row.get("deduct_net_profit_yoy")) or number(
            row.get("deduct_basic_eps_yoy"))
        core_notes=[]
        if not core_available:
            core_notes.append("CORE_PROFIT_GROWTH_NOT_AVAILABLE")
        if not number(row.get("deduct_basic_eps")):
            core_notes.append("CORE_EPS_NOT_AVAILABLE")
        if number(ocf) and ocf<=0:
            core_notes.append("NONPOSITIVE_OPERATING_CASHFLOW_PER_SHARE")
        entries.append({
            "code":code, "name":row.get("name"),
            "industry_code":row["industry_code"],
            "asof_date":date,
            "asof_price":row["price"],
            "fundamental_score":previous["fundamental_score"],
            "financial_report_period_end":row.get("report_date"),
            "financial_publication_date_verified":row.get("financial_publication_date_verified") is True,
            "core_profit_growth_verified":core_available,
            "financial_evidence_gaps":core_notes,
            "entry_channel_eligible":bool(entry_eligible),
            "entry_ineligibility_reason":(None if entry_eligible
                                          else previous.get("excluded_reason") or "ENTRY_EVIDENCE_MISSING"),
            "entry_reference_score":(entry_observation.get("entry_score") if entry_eligible else 0.0),
            "price_structure_score":(entry_observation.get("price_structure_score") if entry_eligible else 0.0),
            "history":f,
        })
    return entries,excluded


def rank_entry_first(entries, slots=MAX_RESEARCH_PER_INDUSTRY):
    """Entry-qualified candidates compete for ALL five seats; no channel quotas.

    Trend-only names are research fallbacks ONLY when fewer than five verified
    entry-proxy candidates exist. Qualification is NOT confirmed READY and may
    never bypass the separate completed-bar entry/stop/reward risk gate.
    """
    if slots!=5:
        raise ValueError("prescreen_fixed_five_company_model_budget")
    if not entries:
        return [], {"reason":"NO_FULLY_VERIFIED_CANDIDATES"}
    n=len(entries)
    if len({x["code"] for x in entries})!=n:
        raise ValueError("duplicate_company_candidate")
    comparable=[x for x in entries if all(number(x["history"]["returns_pct"][h])
                                           for h in ("10","20","60"))]
    if len(comparable)<3:
        return [],{"reason":"INSUFFICIENT_SAME_DAY_PEERS","peers":len(comparable)}
    reference={
        h:median(x["history"]["returns_pct"][h] for x in comparable)
        for h in ("10","20","60")}
    for row in entries:
        r=row["history"]["returns_pct"]
        for h in ("10","20","60"):
            row["history"]["relative_to_sw3_median_"+h+"d_pp"]=round(
                r[h]-reference[h],5)
    for h in ("10","20","60"):
        values=[e["history"]["relative_to_sw3_median_"+h+"d_pp"]
                for e in entries]
        ranks=percentile(values)
        for e,rank in zip(entries,ranks):
            e.setdefault("peer_percentiles",{})[h]=rank
    stay=percentile([x["history"]["positive_days_10"] for x in entries])
    for e,rank in zip(entries,stay):
        p=e["peer_percentiles"]
        if not all(number(p[h]) for h in ("10","20","60")) or not number(rank):
            return [],{"reason":"PEER_PERCENTILE_INCOMPLETE"}
        # The recorded sub-scores remain observable evidence, not two quotas.
        continued=(.40*p["20"]+.30*p["60"]+.20*p["10"]+.10*rank)
        entry=e["entry_reference_score"]
        structure=e["price_structure_score"]
        if not all(number(v) for v in (entry,structure)):
            return [],{"reason":"ENTRY_EVIDENCE_INVALID"}
        e["leader_channel_score"]=round(.80*continued+
                                        .20*e["fundamental_score"],6)
        e["entry_channel_score"]=round(.65*entry+
                                       .20*structure+
                                       .15*e["fundamental_score"],6)
    entry_order=sorted((e for e in entries if e["entry_channel_eligible"]),
                       key=lambda e:(-e["entry_channel_score"],
                                     -e["leader_channel_score"],e["code"]))
    watch_order=sorted((e for e in entries if not e["entry_channel_eligible"]),
                       key=lambda e:(-e["leader_channel_score"],e["code"]))
    selected=[{**e,"selected_channel":"ENTRY_PRIORITY"}
              for e in entry_order[:slots]]
    remaining=slots-len(selected)
    selected.extend({**e,"selected_channel":"WATCH_FALLBACK"}
                    for e in watch_order[:remaining])
    return selected,{
        "selection_policy":"ENTRY_FIRST_NO_QUOTAS",
        "scored_peer_count":len(entries),
        "peer_return_medians_pct":reference,
        "entry_evidence_eligible_count":len(entry_order),
        "entry_selected_count":min(len(entry_order),slots),
        "watch_fallback_count":min(remaining,len(watch_order)),
        "entry_top5_codes":[x["code"] for x in entry_order[:5]],
        "watch_fallback_top5_codes":[x["code"] for x in watch_order[:5]],
        "max_model_research_per_sw3":5,
        "entry_proxy_does_not_authorize_ready":True,
    }


def model_deep_review_packets(picked, trade_date):
    """At most 5 bounded review requests, NEVER requests for the whole sector."""
    if len(picked)>MAX_RESEARCH_PER_INDUSTRY:
        raise ValueError("model_review_scope_exceeds_five")
    return [{
        "code":company["code"],
        "company_name":company["name"],
        "industry_code":company["industry_code"],
        "asof_date":trade_date,
        "selected_channel":company["selected_channel"],
        "program_evidence":{
            "peer_relative_return_pp":{
                horizon:company["history"]["relative_to_sw3_median_"+horizon+"d_pp"]
                for horizon in ("10","20","60")},
            "continuity_days_10":company["history"]["positive_days_10"],
            "current_entry_reference_score":company["entry_reference_score"],
            "financial_basic_score":company["fundamental_score"],
            "core_earnings_growth_available":company["core_profit_growth_verified"],
            "financial_publication_date_verified":company["financial_publication_date_verified"],
            "financial_evidence_gaps":company["financial_evidence_gaps"],
        },
        "source_requirements":{
            "published_no_later_than":trade_date,
            "business_and_sector_transmission":"REQUIRE_VERIFIABLE_DISCLOSURE",
            "core_profit_and_cashflow":"REQUIRE_OR_MARK_UNKNOWN",
            "expected_growth_revision":"DATE_STAMPED_FACT_OR_UNKNOWN",
            "market_prior_expectation":"UNKNOWN_UNLESS_HISTORICAL_SOURCE",
            "negative_counterevidence":"REQUIRED",
            "no_imputed_price_target_or_win_probability":True,
        },
        "deep_review_status":"PENDING",
        "may_promote_ready_without_python_risk_gate":False,
    } for company in picked]


def run(root, screen, industry_index=None, selected_date=None,
        allowed_codes=None, financial_overlay=None):
    date=screen.get("trade_date")
    if not isinstance(date,str) or selected_date not in (None,date):
        raise ValueError("frozen_screen_date_mismatch")
    audit=screen.get("screen_audit") or {}
    scanned=audit.get("lightweight_scanned")
    if (not isinstance(scanned,list) or audit.get("hard_eligible")!=len(scanned)):
        raise ValueError("frozen_screen_lightweight_coverage_missing")
    index=industry_index or read_json(root/"data/low_risk/index.json")
    if index.get("trade_date")!=date:
        raise ValueError("frozen_working_set_index_date_mismatch")
    groups=defaultdict(list)
    for row in scanned:
        groups[row["industry_code"]].append(row)
    selected_industries=sorted(groups)
    if allowed_codes is not None:
        selected_industries=[c for c in selected_industries if c in allowed_codes]
    cache={}
    output=[]
    for code in selected_industries:
        rows=frozen_industry_rows(root,index,code,date)
        if financial_overlay is not None:
            rows=[{**row,**financial_overlay.get(row["code"],{})}
                  for row in rows]
        company,excluded=select_company_rows(rows,groups[code],date,root,cache)
        picked,details=rank_entry_first(company)
        output.append({
            "industry_code":code,
            "industry_name":rows[0].get("industry_name") if rows else None,
            "all_frozen_companies":len(rows),
            "hard_eligible_count":len(groups[code]),
            "eligible_with_new_technical_evidence":len(company),
            "history_exclusions":excluded,
            "research_codes":[x["code"] for x in picked],
            "model_research_slots_required":len(picked),
            "selection_evidence":details,
            "selected_candidates":picked,
            "model_deep_review_packets":model_deep_review_packets(picked,date),
            "reconstruction_fully_verified":bool(picked),
            "requires_fresh_business_review_before_formal_use":True,
        })
    return {
        "version":VERSION,
        "mode":"PROGRAM_ONLY_NO_MODEL_CALL",
        "asof_date":date,
        "industry_groups":output,
        "rules":{
            "upstream_confirmed_sw3_unchanged":True,
            "python_scans_hard_eligible_only":True,
            "max_model_reviews_per_sw3":5,
            "selection_policy":"ENTRY_FIRST_NO_QUOTAS",
            "forecast_consensus_source":"NOT_AVAILABLE_NO_IMPUTATION",
            "business_review_in_python":False,
            "ready_wait_and_handoff_untouched":True,
            "asof_history_only":True,
        },
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--screen",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    output=args.output.resolve()
    if any(s in str(output) for s in (
            "trend_buy_formal_result","trend_buy_handoff")):
        raise ValueError("prescreen_cannot_write_formal_output")
    result=run(args.root.resolve(),read_json(args.screen))
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({
        "mode":result["mode"],"date":result["asof_date"],
        "industry_groups":[{
            "industry":x["industry_code"],
            "selected":x["research_codes"],
            "eligible":x["eligible_with_new_technical_evidence"],
            "excluded":len(x["history_exclusions"])}
            for x in result["industry_groups"]]
    },ensure_ascii=False))


if __name__=="__main__":
    main()
