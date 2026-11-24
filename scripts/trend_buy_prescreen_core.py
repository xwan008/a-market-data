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
    # Directional volume is a price/volume proxy, not observed fund flow.
    recent_pairs=list(zip(rows[-11:-1],rows[-10:]))
    up_vol=[b["volume"] for a,b in recent_pairs if b["close"]>a["close"]]
    down_vol=[b["volume"] for a,b in recent_pairs if b["close"]<a["close"]]
    volume_balance=(max(0.,min(1.,.5+.30*math.log(
        (sum(up_vol)/len(up_vol))/(sum(down_vol)/len(down_vol)))))
        if up_vol and down_vol else None)
    close_locations=[]
    for bar in rows[-5:]:
        high,low,close=bar.get("high"),bar.get("low"),bar["close"]
        if positive(high) and positive(low) and low<=close<=high:
            close_locations.append((close-low)/(high-low) if high>low else .5)
    close_quality=(sum(close_locations)/len(close_locations)
                   if len(close_locations)==5 else None)
    higher_low=min(closes[-5:])>min(closes[-10:-5])
    return {
        "returns_pct":returns,
        "volume_balance_10d":volume_balance,
        "close_location_5d":close_quality,
        "higher_close_low":higher_low,
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
        # It may still compete for research on trend-quality evidence.
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


def rank_trend_quality(entries, slots=MAX_RESEARCH_PER_INDUSTRY):
    """One cohort, no entry-only priority and no reserved watch seats.

    Price position is a bounded 5% research proxy, never a READY gate.
    Use completed close/volume data only; fund identity is not inferred.
    """
    if slots!=5:
        raise ValueError("prescreen_fixed_five_company_model_budget")
    if not entries:
        return [], {"reason":"NO_FULLY_VERIFIED_CANDIDATES"}
    if len({x["code"] for x in entries})!=len(entries):
        raise ValueError("duplicate_company_candidate")
    horizons=("5","10","20","60")
    if len(entries)<3 or any(not all(number(x["history"]["returns_pct"].get(h))
                                    for h in horizons) for x in entries):
        return [],{"reason":"INSUFFICIENT_SAME_DAY_PEERS","peers":len(entries)}
    reference={h:median(x["history"]["returns_pct"][h] for x in entries)
               for h in horizons}
    for h in horizons:
        values=[e["history"]["returns_pct"][h]-reference[h] for e in entries]
        ranks=percentile(values)
        for e,v,rank in zip(entries,values,ranks):
            e["history"]["relative_to_sw3_median_"+h+"d_pp"]=round(v,5)
            e.setdefault("peer_percentiles",{})[h]=rank
    drawdown=percentile([e["history"]["max_close_drawdown_10_pct"] for e in entries])
    for e,dd in zip(entries,drawdown):
        f=e["history"]
        p=e["peer_percentiles"]
        if not all(number(p[h]) for h in horizons) or not number(dd):
            return [],{"reason":"PEER_PERCENTILE_INCOMPLETE"}
        relative=.20*p["5"]+.30*p["10"]+.30*p["20"]+.20*p["60"]
        persistence=.40*(f["positive_days_10"]/10)+.35*dd+.25*int(f["higher_close_low"])
        vb=f.get("volume_balance_10d")
        cl=f.get("close_location_5d")
        volume=.55*(vb if number(vb) else .5)+.45*(cl if number(cl) else .5)
        fundamental=e["fundamental_score"]
        if not number(fundamental) or not 0<=fundamental<=1:
            return [],{"reason":"FUNDAMENTAL_SCORE_OUTSIDE_UNIT_INTERVAL"}
        position=(e["entry_reference_score"] if e["entry_channel_eligible"] else .5)
        if not number(position):
            return [],{"reason":"ENTRY_REFERENCE_INVALID"}
        position=max(0.,min(1.,position))
        score=.30*relative+.25*persistence+.25*volume+.15*fundamental+.05*position
        e["trend_quality_score"]=round(score,6)
        e["trend_quality_components"]={
            "relative_strength":relative,"persistence":persistence,
            "volume_price_quality":volume,"fundamental":fundamental,
            "position_proxy":position,
            "directional_volume_observed":number(vb),
            "close_location_observed":number(cl),
        }
    ordered=sorted(entries,key=lambda e:(-e["trend_quality_score"],e["code"]))
    selected=[{**e,"selected_channel":("ENTRY_EVIDENCE_PRESENT"
                 if e["entry_channel_eligible"] else "ENTRY_EVIDENCE_ABSENT")}
              for e in ordered[:slots]]
    entry_count=sum(e["entry_channel_eligible"] for e in selected)
    return selected,{
        "selection_policy":"TREND_QUALITY_FIRST_NO_QUOTAS",
        "scored_peer_count":len(entries),
        "peer_return_medians_pct":reference,
        "entry_evidence_eligible_count":sum(e["entry_channel_eligible"] for e in entries),
        "entry_selected_count":entry_count,
        "watch_fallback_count":len(selected)-entry_count,
        "trend_quality_top5_codes":[e["code"] for e in selected],
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
            "trend_quality_score":company["trend_quality_score"],
            "trend_quality_components":company["trend_quality_components"],
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
        picked,details=rank_trend_quality(company)
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
            "selection_policy":"TREND_QUALITY_FIRST_NO_QUOTAS",
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
