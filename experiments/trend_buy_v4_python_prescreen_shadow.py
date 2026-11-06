#!/usr/bin/env python3
"""V4 program-first pre-screen, SHADOW ONLY.

Python scans ALL hard-eligible companies in each already-confirmed SW3 industry.
It chooses at most FIVE companies for subsequent MODEL research: three sustained
leaders and two nearer-entry candidates. There are NO model calls here.

Only previously frozen company and prior-to-asof history data enter selection;
no later prices, contemporaneous news inference, or invented analyst forecasts.
The formal pre-screen, READY/WAIT, official handoff and ranking are untouched.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
MAX_RESEARCH_PER_INDUSTRY = 5
LEADER_SLOTS = 3
ENTRY_SLOTS = 2
VERSION = "v4_python_first_prescreen_shadow_v1"


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
    v1=rows[-1]["volume"]/vol20 if vol20>0 else None
    return {
        "returns_pct":returns,
        "positive_days_10":up10,
        "max_close_drawdown_10_pct":round(worst,4),
        "volume_1d_vs_prior20_median":round(v1,4) if v1 is not None else None,
        "extreme_recent_acceleration_observation":bool(
            returns["5"]>12 and v1 is not None and v1>3),
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
        if previous.get("excluded_reason") is not None or not previous.get("opportunity"):
            excluded.append({"code":code,"reason":previous.get("excluded_reason") or "NO_VERIFIED_OPPORTUNITY"})
            continue
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
            "financial_publication_date_verified":False,
            "core_profit_growth_verified":core_available,
            "financial_evidence_gaps":core_notes,
            "entry_reference_score":previous["opportunity"].get("entry_score"),
            "price_structure_score":previous["opportunity"].get("price_structure_score"),
            "legacy_pre_screen_score":previous.get("combined_score"),
            "legacy_opportunity":previous["opportunity"],
            "history":f,
        })
    return entries,excluded


def dual_channel(entries, slots=MAX_RESEARCH_PER_INDUSTRY):
    """No over-cap ties. Leadership and entry are intentionally independent."""
    if slots!=5:
        raise ValueError("v4_fixed_five_company_model_budget")
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
        # Fixed transparent V4-Lite hypothesis; NOT tuned on hindsight returns.
        continued=(.40*p["20"]+.30*p["60"]+.20*p["10"]+.10*rank)
        entry=e["entry_reference_score"]
        structure=e["price_structure_score"]
        if not all(number(v) for v in (entry,structure)):
            return [],{"reason":"ENTRY_EVIDENCE_MISSING"}
        e["leader_channel_score"]=round(.80*continued+
                                        .20*e["fundamental_score"],6)
        e["entry_channel_score"]=round(.65*entry+
                                       .20*structure+
                                       .15*e["fundamental_score"],6)
    leader_order=sorted(entries,key=lambda e:(-e["leader_channel_score"],e["code"]))
    entry_order=sorted(entries,key=lambda e:(-e["entry_channel_score"],e["code"]))
    picked=[]
    for channel,ordered,take in (
        ("LEADERSHIP",leader_order,LEADER_SLOTS),
        ("ENTRY_LOCATION",entry_order,ENTRY_SLOTS)
    ):
        for e in ordered:
            if sum(x["selected_channel"]==channel for x in picked)>=take:
                break
            if e["code"] in {x["code"] for x in picked}:
                continue
            item=dict(e)
            item["selected_channel"]=channel
            picked.append(item)
    # With fewer than five fully eligible peers, do not fabricate members.
    if len(picked)<min(slots,len(entries)):
        for e in leader_order:
            if len(picked)>=min(slots,len(entries)):
                break
            if e["code"] not in {x["code"] for x in picked}:
                picked.append({**e,"selected_channel":"BACKFILL"})
    return picked,{
        "scored_peer_count":len(entries),
        "peer_return_medians_pct":reference,
        "leader_top5_codes":[x["code"] for x in leader_order[:5]],
        "entry_top5_codes":[x["code"] for x in entry_order[:5]],
        "max_model_research_per_sw3":5,
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
            "core_earnings_growth_verified":company["core_profit_growth_verified"],
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
        "deep_review_status":"PENDING_IN_SHADOW",
        "may_promote_ready_without_python_risk_gate":False,
    } for company in picked]


def run(root, screen, industry_index=None, selected_date=None,
        allowed_codes=None, financial_overlay=None):
    date=screen.get("trade_date")
    if not isinstance(date,str) or selected_date not in (None,date):
        raise ValueError("frozen_screen_date_mismatch")
    audit=screen.get("screen_audit") or {}
    scanned=audit.get("lightweight_scanned")
    selected=audit.get("pre_screen_selected")
    if (not isinstance(scanned,list) or not isinstance(selected,list) or
        audit.get("hard_eligible")!=len(scanned)):
        raise ValueError("frozen_screen_lightweight_coverage_missing")
    index=industry_index or read_json(root/"data/low_risk/index.json")
    if index.get("trade_date")!=date:
        raise ValueError("frozen_working_set_index_date_mismatch")
    groups=defaultdict(list)
    baseline=defaultdict(list)
    for row in scanned:
        groups[row["industry_code"]].append(row)
    for row in selected:
        baseline[row["industry_code"]].append(row["code"])
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
        picked,details=dual_channel(company)
        found={x["code"] for x in picked}
        original=baseline.get(code,[])
        output.append({
            "industry_code":code,
            "industry_name":rows[0].get("industry_name") if rows else None,
            "all_frozen_companies":len(rows),
            "original_hard_eligible":len(groups[code]),
            "eligible_with_new_technical_evidence":len(company),
            "history_exclusions":excluded,
            "original_research_codes":original,
            "v4_research_codes":[x["code"] for x in picked],
            "original_count":len(original),
            "new_research_required_codes":sorted(found-set(original)),
            "original_candidates_omitted":sorted(set(original)-found),
            "model_research_slots_required":len(picked),
            "selection_evidence":details,
            "selected_candidates":picked,
            "model_deep_review_packets":model_deep_review_packets(picked,date),
            "reconstruction_fully_verified":bool(picked) and not any(
                x["code"] in set(original) for x in excluded),
            "requires_fresh_business_review_before_formal_use":True,
        })
    return {
        "version":VERSION,
        "mode":"SHADOW_PROGRAM_ONLY_NO_MODEL_CALL",
        "asof_date":date,
        "industry_groups":output,
        "rules":{
            "upstream_confirmed_sw3_unchanged":True,
            "python_scans_hard_eligible_only":True,
            "max_model_reviews_per_sw3":5,
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
    if ("shadow" not in str(output).lower()
        or any(s in str(output) for s in (
            "trend_buy_formal_result","trend_buy_handoff"))):
        raise ValueError("shadow_only_output_required")
    result=run(args.root.resolve(),read_json(args.screen))
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({
        "mode":result["mode"],"date":result["asof_date"],
        "industry_groups":[{
            "industry":x["industry_code"],
            "original":x["original_research_codes"],
            "v4":x["v4_research_codes"],
            "new_research_required":x["new_research_required_codes"],
            "eligible":x["eligible_with_new_technical_evidence"],
            "excluded":len(x["history_exclusions"])}
            for x in result["industry_groups"]]
    },ensure_ascii=False))


if __name__=="__main__":
    main()
