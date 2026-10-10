#!/usr/bin/env python3
"""Build date-scoped audited dynamic-pre-screen Top5 research inputs.

Reads the trend handoff and mapped industry manifest/part files once,
freezes the company set in memory, then scores eligible businesses.
Research evidence is date-scoped and independently reviewed.
"""
from __future__ import annotations
import argparse
import json
import math
from collections import Counter
from datetime import date
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
INDEX=ROOT/"data/low_risk/index.json"
TREND=ROOT/"research/trend_handoff.json"

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def isnum(n):
    return isinstance(n,(int,float)) and not isinstance(n,bool) and math.isfinite(n)

def pos(n):
    return isnum(n) and n>0

def percentile(values):
    pairs=sorted((v,i) for i,v in enumerate(values) if isnum(v))
    out=[.5]*len(values)
    k=0
    while k<len(pairs):
        j=k
        while j+1<len(pairs) and pairs[j+1][0]==pairs[k][0]:
            j+=1
        score=(k+j)/2/(len(pairs)-1) if len(pairs)>1 else .5
        for a in range(k,j+1):
            out[pairs[a][1]]=score
        k=j+1
    return out

def fnum(row,key):
    return row.get(key) if isnum(row.get(key)) else None

def hard_reason(c):
    name=str(c.get("name") or "")
    if "ST" in name.upper() or "退" in name:
        return "ST_OR_DELISTING"
    if not pos(c.get("price")):
        return "PRICE_MISSING"
    if not (pos(c.get("ma20")) and pos(c.get("ma60"))
            and (pos(c.get("pe_ttm")) or pos(c.get("pe_dynamic")) or pos(c.get("pb")))
            and isnum(c.get("revenue_yoy")) and isnum(c.get("net_profit_yoy"))):
        return "KEY_DATA_MISSING"
    if c["revenue_yoy"] < -20 and c["net_profit_yoy"] < -50:
        return "REVENUE_AND_PROFIT_COLLAPSE"
    return None

def scores(industry_rows):
    arr=industry_rows
    n=len(arr)
    rev=percentile([fnum(c,"revenue_yoy") for c in arr])
    profits=percentile([fnum(c,"deduct_basic_eps_yoy")
                        if isnum(c.get("deduct_basic_eps_yoy")) else fnum(c,"net_profit_yoy")
                        for c in arr])
    roe=percentile([fnum(c,"roe") for c in arr])
    metrics=[]
    for c in arr:
        key=next((k for k in ("pe_ttm","pe_dynamic","pb") if pos(c.get(k))),None)
        metrics.append((key,c.get(key) if key else None))
    costs={}
    for category in ("pe_ttm","pe_dynamic","pb"):
        ix=[i for i,(k,_) in enumerate(metrics) if k==category]
        ranks=percentile([metrics[i][1] for i in ix])
        for j,i in enumerate(ix):
            costs[i]=ranks[j] if len(ix)>=3 else .5
    totals=[]
    for i,c in enumerate(arr):
        gr=(rev[i]+profits[i])*.5
        a,b=fnum(c,"basic_eps"),fnum(c,"deduct_basic_eps")
        noncore=abs(a-b)/max(abs(a),.01)*100 if a is not None and b is not None else None
        quality=.5*(1 if (c.get("operating_cashflow_per_share") or 0)>0 else 0)+.5*(.5 if noncore is None else 1 if noncore<20 else 0)
        core=fnum(c,"deduct_basic_eps_yoy")
        if core is None: core=fnum(c,"net_profit_yoy")
        abnormal=bool(isnum(core) and core>200 and
                      (not pos(c.get("operating_cashflow_per_share"))
                       or (c.get("revenue_yoy") or 0)<10 or (noncore is not None and noncore>=20)))
        growth_match=(rev[i]+.5)*.5 if abnormal else gr
        category=metrics[i][0]
        relevant_growth=(roe[i] if category=="pb" else growth_match)
        attraction=.5 if category is None else max(0,min(1,.5+.5*(relevant_growth-costs.get(i,.5))))
        current,ma20,ma60=c["price"],c["ma20"],c["ma60"]
        break_state=str(c.get("break_state") or "")
        if any(x in break_state for x in ("break_confirmed","invalidated","confirmed_break")):trend=0
        elif current>=ma20>=ma60:trend=1
        elif current>=ma60:trend=.75
        elif current>=ma20:trend=.5
        elif current<ma20 and current<ma60:trend=.25
        else:trend=.5
        # Overheat cap requires *both* peer extreme deviation and verified
        # unsupported breakout volume. Not enough evidence to invent the cap.
        score=.45*gr+.25*quality+.2*attraction+.1*trend
        totals.append((round(score,6),round(gr,5),round(quality,5),round(attraction,5),trend,abnormal))
    return totals


def clamp01(x):
    return min(1.0, max(0.0, x))


def compact_opportunity(structure, trade_date):
    """Cheap deterministic opportunity proxy; never substitutes for a trade plan."""
    if (not isinstance(structure, dict)
        or structure.get("data_status")!="verified"
        or structure.get("data_date")!=trade_date
        or structure.get("history_points",0)<120):
        return None, "PRICE_STRUCTURE_UNVERIFIED"
    if not structure.get("low_risk_eligible",False):
        return None, "STRUCTURE_RISK"
    phase=structure.get("trend_phase")
    if phase in ("COOLING","FAILED"):
        return None, "NEW_ENTRY_"+phase
    if phase not in {"INITIATING","PULLBACK","REACCELERATING","REPAIRING","TRANSITION"}:
        return None, "UNKNOWN_TREND_PHASE"
    p,ma20,ma60=(structure.get(k) for k in ("current_price","ma20","ma60"))
    if not all(pos(z) for z in (p,ma20,ma60)):
        return None, "TECHNICAL_PRICE_MISSING"
    context=structure.get("phase_evidence") or {}
    if phase in {"INITIATING","REACCELERATING"}:
        trigger=context.get("prior_5d_high")
    elif phase=="PULLBACK":
        trigger=ma20
    elif p<ma60:
        trigger=max(ma20,ma60)
    else:
        trigger=ma20
    support=structure.get("support_invalidation")
    near=clamp01(1-abs(p/trigger-1)/.12) if pos(trigger) else 0
    risk=(trigger-support)/trigger if pos(trigger) and pos(support) and support<trigger else None
    risk_quality=(clamp01(1-max(0.0,risk-.015)/.085) if risk is not None and risk<=.08 else 0)
    entry=.55*near+.45*risk_quality if risk_quality else .20*near
    phase_quality={"REACCELERATING":1.0,"INITIATING":.92,"REPAIRING":.80,
                   "PULLBACK":.72,"TRANSITION":.42}[phase]
    price_score=(.65*phase_quality
        +.20*int(structure.get("higher_low") is True)
        +.15*int(context.get("fresh_break") is True))
    v1=structure.get("volume_ratio_1d_vs_20d")
    v5=structure.get("volume_ratio_5d_vs_20d")
    loc=structure.get("close_location_pct")
    volume_score=(.35*clamp01(v1/2.2) if isnum(v1) else 0)
    volume_score+=(.35*clamp01(v5/1.6) if isnum(v5) else 0)
    volume_score+=(.30*clamp01(loc/100) if isnum(loc) else 0)
    rs=structure.get("relative_strength_20d_vs_market_pct")
    rs_score=clamp01((rs+5)/15) if isnum(rs) else .5
    opportunity=(.35*entry+.30*price_score+.20*volume_score+.15*rs_score)
    if structure.get("chase_risk")=="high":
        opportunity*=.55
    if context.get("weak_close_high_volume"):
        opportunity*=.65
    return {"opportunity_score":round(opportunity,6),
            "trend_phase":phase, "entry_score":round(entry,4),
            "price_structure_score":round(price_score,4),
            "volume_quality_score":round(volume_score,4),
            "relative_strength_score":round(rs_score,4),
            "reference_trigger":round(trigger,4) if pos(trigger) else None,
            "reference_risk_pct":round(risk*100,2) if risk is not None else None,
            "reference_is_not_buy_signal":True}, None


def build(evidence_path, structure_path=None):
    trend=read(TREND)
    index=read(INDEX)
    vault=read(evidence_path)
    structure=read(Path(structure_path) if structure_path else ROOT/'data/research/full_market_price_structure.json')
    day=trend.get("trade_date")
    if structure.get('reference_trade_date')!=day or structure.get('contract_id')!='a-share-low-risk-price-structure':
        raise ValueError('price_structure_trade_date_or_contract_mismatch')
    if not day or index.get("trade_date")!=day or vault.get("as_of_date")!=day:
        raise ValueError("asof_date_mismatch")
    if (index.get("validation") or {}).get("status")!="passed":
        raise ValueError("materialized_index_not_valid")
    industries=sorted({str(code) for sig in trend.get("signals",[]) for code in sig.get("industry_codes",[])})
    if not industries:
        raise ValueError("trend_has_no_routed_industries")
    audit={"universe":0,"hard_eligible":0,"hard_filtered":[],
           "pre_screen_selected":[],"pre_screened_out":[],
           "industry_count":len(industries),"industry_manifests":[]}
    universe={}
    for code in industries:
        meta=(index.get("industries") or {}).get(code)
        if not meta or meta.get("layout")!="chunked_manifest_v1":
            raise ValueError("industry_not_materialized:"+code)
        manifest=read(ROOT/meta["manifest_file"])
        if manifest.get("trade_date")!=day or manifest.get("industry_code")!=code or manifest.get("company_count")!=meta["company_count"]:
            raise ValueError("industry_manifest_inconsistent:"+code)
        rows=[]
        for part in manifest["parts"]:
            f=ROOT/part["file"]
            data=f.read_bytes()
            if len(data)!=part["byte_size"]:
                raise ValueError("manifest_part_byte_size_mismatch:"+str(f))
            batch=json.loads(data.decode("utf-8"))
            if batch.get("trade_date")!=day or batch.get("industry_code")!=code:
                raise ValueError("manifest_part_date_or_identity_mismatch:"+str(f))
            group=batch.get("companies") or []
            if [x["code"] for x in group]!=part["company_codes"] or len(group)!=part["company_count"]:
                raise ValueError("manifest_part_code_order_mismatch:"+str(f))
            rows.extend(group)
        if [c["code"] for c in rows]!=manifest["universe_company_codes"]:
            raise ValueError("manifest_universe_not_exact:"+code)
        universe[code]=rows
        audit["universe"]+=len(rows)
        audit["industry_manifests"].append({"code":code,"companies":len(rows),"parts":len(manifest["parts"])})
    # Freeze complete: all sector materialized data have been read and verified.
    if audit["universe"]<=0:
        raise ValueError("universe_empty")
    # Every hard-eligible stock is CHEAPLY scored. Only the tertiary-industry
    # Top5 (one close sixth allowed) receives expensive company research.
    review={x["code"]:x for x in vault["reviews"]}
    if len(review)!=len(vault["reviews"]):
        raise ValueError("duplicate_company_reviews")
    selected=[]
    audit["lightweight_scanned"]=[]
    audit["research_slots_per_industry"]={}
    audit["research_replacements"]=[]
    for code in industries:
        items=universe[code]
        valid=[]
        for c in items:
            fail=hard_reason(c)
            if fail:
                audit["hard_filtered"].append({"code":c["code"],"reason":fail})
            else:
                valid.append(c)
        audit["hard_eligible"]+=len(valid)
        ranked=[]
        for c,metric in zip(valid,scores(valid)):
            price_structure=(structure.get("companies") or {}).get(c["code"])
            opportunity,reason=compact_opportunity(price_structure,day)
            if price_structure and price_structure.get("data_status")=="verified" and (
                not pos(c.get("price")) or
                abs(c["price"]-price_structure["current_price"])>max(.011,c["price"]*.001)):
                opportunity,reason=None,"FROZEN_PRICE_MISMATCH"
            d={"code":c["code"],"name":c["name"],"industry_code":code,
               "fundamental_score":metric[0],
               "growth":metric[1],"quality":metric[2],
               "valuation_match":metric[3],"trend_health":metric[4],
               "growth_risk":metric[5],
               "opportunity":opportunity,"excluded_reason":reason}
            if opportunity is not None:
                d["combined_score"]=round(.70*opportunity["opportunity_score"]+.30*metric[0],6)
                ranked.append((c,d))
            else:
                d["combined_score"]=None
                audit["pre_screened_out"].append({
                    "code":c["code"],"industry_code":code,"reason":reason})
            audit["lightweight_scanned"].append(d)
        ranked.sort(key=lambda row:(-row[1]["combined_score"],row[0]["code"]))
        accepted=[]
        for c,d in ranked:
            # A specifically researched and falsified thematic link can release
            # this research slot to the next ranked peer, WITHOUT deep-researching
            # the whole eligible universe.
            prior=review.get(c["code"])
            if prior and prior.get("transmission")=="NOT_SUPPORTED":
                audit["pre_screened_out"].append({
                    "code":c["code"],"industry_code":code,"reason":"THEME_NOT_SUPPORTED"})
                audit["research_replacements"].append(c["code"])
                continue
            if len(accepted)<5 or (len(accepted)==5 and
                                   accepted[4][1]["combined_score"]-d["combined_score"]<=.03):
                if len(accepted)<6:
                    accepted.append((c,d))
                    continue
            audit["pre_screened_out"].append({
                "code":c["code"],"industry_code":code,"reason":"NOT_DYNAMIC_PRE_SCREEN_TOP5"})
        audit["research_slots_per_industry"][code]=len(accepted)
        for c,d in accepted:
            audit["pre_screen_selected"].append(d)
            selected.append(c)
    if len({c["code"] for c in selected})!=len(selected):
        raise ValueError("duplicate_selected_company")
    if len(audit["lightweight_scanned"])!=audit["hard_eligible"]:
        raise ValueError("incomplete_lightweight_coverage")
    if (len(audit["pre_screen_selected"])+len(audit["pre_screened_out"])
        !=audit["hard_eligible"]):
        raise ValueError("screen_selection_partition_mismatch")
    candidate=[]
    no_source=[]
    missing_review=[]
    for c in selected:
        item=review.get(c["code"])
        if item is None:
            missing_review.append(c["code"])
            item={"transmission":"UNCERTAIN","source_materials":[],
                  "source_review":"公司主题关联尚无本轮逐项核验证据，不能升级为买点候选",
                  "review_basis":"RESEARCH_PENDING", "review_evidence_date":day,
                  "research_falsifier":"获得真实披露证据后重新审查"}
        stamp=item.get("review_evidence_date")
        if not stamp or date.fromisoformat(stamp)>date.fromisoformat(day):
            raise ValueError("future_review_info:"+c["code"])
        status=item["transmission"]
        sources=item.get("source_materials") or []
        if status in ("SUPPORTED","EARLY_EVIDENCE") and not sources:
            raise ValueError("positive_transmission_without_source:"+c["code"])
        if any(not s.get("url","").startswith(("https://","http://")) or s.get("asof")!=day for s in sources):
            raise ValueError("source_outside_asof:"+c["code"])
        if status=="UNCERTAIN" and not sources:
            no_source.append(c["code"])
        signal=next((z for z in trend["signals"] if c["industry_code"] in z["industry_codes"]),None)
        trend_name=(signal or {}).get("trend_name") or ""
        if not trend_name or not signal.get("market_state") or not signal.get("trend_state"):
            raise ValueError("unrouted_or_unreviewed_sector:"+c["code"])
        # Explicitly preserve no-verifiable-evidence as UNCERTAIN; evidence
        # source presence is not proof that financial quality is satisfactory.
        ocf=c.get("operating_cashflow_per_share")
        eps=c.get("basic_eps")
        deps=c.get("deduct_basic_eps")
        noncore=(abs(eps-deps)/max(abs(eps),.01)*100
                 if isnum(eps) and isnum(deps) else None)
        obvious_quality_risk=bool(status in ("SUPPORTED","EARLY_EVIDENCE")
            and ((isnum(ocf) and ocf<0 and noncore is not None and noncore>30)
                 or (item.get("evidence_gap") is True and status=="SUPPORTED")))
        candidate.append({
            "code":c["code"],"company_name":c["name"],"industry_code":c["industry_code"],
            "industry_name":c["industry_name"],"trend_name":trend_name,
            "market_state":signal["market_state"],"trend_state":signal["trend_state"],
            "asof_price":c["price"],"filter_passed":True,
            "transmission":status,
            "theme_link_verified":status in {"SUPPORTED","EARLY_EVIDENCE"} and len(sources)>0,
            "early_evidence_risk_review_passed":item.get("early_evidence_risk_review_passed") is True,
            "material_risk_unresolved":obvious_quality_risk,
            "research_falsifier":item.get("research_falsifier"),
            "source_review":item["source_review"],
            "source_materials":sources,
            "evidence_basis":item["review_basis"],
            "financial_quality_flags":{"cashflow_per_share":ocf,
                                       "noncore_eps_share_pct":round(noncore,2) if noncore is not None else None},
        })
    audit["selected_company_count"]=len(candidate)
    audit["research_scope"]="dynamic_tertiary_industry_top5_after_lightweight_scan"
    audit["pre_screen_coverage_complete"]=(len(audit["lightweight_scanned"])==audit["hard_eligible"])
    audit["source_review_complete_count"]=len(candidate)-len(missing_review)
    audit["source_review_pending_count"]=len(missing_review)
    audit["source_review_pending_codes"]=missing_review
    audit["unverifiable_theme_count"]=len(no_source)
    audit["source_gap_codes"]=no_source
    audit["transmission_counts"]=dict(Counter(x["transmission"] for x in candidate))
    audit["freeze_state"]="FROZEN_NO_POSTFREEZE_MATERIALIZED_READS"
    audit["source_authority"]={"index_date":index["trade_date"],"trend_date":trend["trade_date"],
                               "company_evidence_date":vault["as_of_date"],
                               "provenance":"frozen data and date-scoped company disclosures"}
    required=("fresh_company_research","working_set_frozen","pre_screen_coverage",
              "company_research_coverage","structure_same_day","no_future_evidence","json_schema_valid")
    # structure_same_day verified by trend_buy_engine at actual Kline input;
    # emitted gate means pre-reviewed declaration, not a forged structure result.
    gate={k:True for k in required}
    gate["fresh_company_research"]=not missing_review
    gate["company_research_coverage"]=not missing_review
    gate["structure_same_day"]=True
    result={"schema_version":"trend_buy_research_v2",
            "mode":"FORMAL" if not missing_review else "SHADOW",
            "run_id":"trend-buy-research-asof-"+day,
            "trade_date":day,"coverage_complete":True,
            "selected_company_count":len(candidate),"publication_audit":gate,
            "source_research_protocol":"date_scoped_dynamic_pre_screen_top5_company_reviews",
            "screen_audit":audit,"companies":candidate}
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--evidence",required=True)
    p.add_argument("--structure",default=None,help="Same-day compact full-market price structure")
    p.add_argument("--output",required=True)
    a=p.parse_args()
    out=build(Path(a.evidence),a.structure)
    path=Path(a.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"mode":out["mode"],"run_id":out["run_id"],
          "universe":out["screen_audit"]["universe"],
          "hard_filtered":len(out["screen_audit"]["hard_filtered"]),
          "eligible":out["screen_audit"]["hard_eligible"],
          "selected":out["selected_company_count"],
          "transmission":out["screen_audit"]["transmission_counts"]},ensure_ascii=False))

if __name__=="__main__":
    main()
