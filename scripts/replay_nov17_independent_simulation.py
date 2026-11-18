#!/usr/bin/env python3
"""Isolated one-off 2026-11-17 mainline-asof full replay; NEVER publishes.

Purpose: redo canonical Python intake; reassess the selected companies from
point-in-time frozen price, asof F10 financial records and dated disclosure
source pointers WITHOUT reading the previous model ranks/reasons or formal
result; rerun the official research builder + independent trade-risk engine.
This is an audit-only historical simulation, not new issuer source scraping.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from collections import defaultdict

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))

import prepare_trend_buy_candidates as program
import build_trend_buy_manual_research as scanner
import trend_buy_prescreen_core as history
from validate_trend_publication_pair import validate as check_pair
from validate_theme_handoff_routes import check_theme_routes

ASOF="2026-11-17"
SIM=Path("/tmp/trend-buy-independent-asof-2026-11-17")
READ_ONLY_PATHS=("research/trend_buy_formal_result.json",
                 "research/trend_buy_handoff.json",
                 "research/trend_buy_candidates/latest.json",
                 "research/trend_buy_company_reviews/latest.json")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path,obj):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


def digest(path):
    return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()


def clamp(x):
    return max(0.,min(1.,x))


def main():
    SIM.mkdir(parents=True,exist_ok=True)
    files_before={p:digest(p) for p in READ_ONLY_PATHS}
    registry=read(ROOT/"research/trend_registry.json")
    handoff=read(ROOT/"research/trend_handoff.json")
    index=read(ROOT/"data/low_risk/index.json")
    assert handoff["trade_date"]==index["trade_date"]==ASOF, "ASOF_UNIVERSE_MISMATCH"
    assert index["validation"]["status"]=="passed"
    errors=check_pair(registry,handoff)
    assert not errors, ("PAIR_GATE_FAILED",errors)
    check_theme_routes(handoff,index,registry)
    assert handoff["signals"], "NO_ELIGIBLE_CONFIRMED_TREND"
    assert all(s["market_state"]=="趋势确认" for s in handoff["signals"])
    assert set(s["trend_name"] for s in handoff["signals"])=={"银行","线下药店"}

    # STEP 1: real full hard-eligible asof-program scan, NOT old program rank.
    frozen=program.prepare(ROOT)
    program.validate_admission(ROOT,frozen)
    admission_dir=SIM/"trend_buy_candidates"
    admission_path=admission_dir/"latest.json"
    write(admission_path,frozen)
    assert read(admission_path)==frozen
    chosen={code:g["industry_code"] for g in frozen["industries"]
            for code in g["selected_codes"]}
    assert len(chosen)==frozen["selected_company_count"]
    print("ISOLATED_PROGRAM_SCAN",json.dumps({
        "date":ASOF,"company_universe":index["company_count"],
        "confirmed_theme_count":len(handoff["signals"]),
        "confirmed_sw3_count":len(frozen["industries"]),
        "hard_eligible_per_sw3":{g["industry_code"]:g["source_hard_eligible_count"]
                                for g in frozen["industries"]},
        "candidate_codes_per_sw3":{g["industry_code"]:g["selected_codes"]
                                   for g in frozen["industries"]},
        "deep_research_count":frozen["selected_company_count"],
    },ensure_ascii=False),flush=True)

    # STEP 2: obtain only frozen, issuer-dated SOURCE POINTERS from the 11/17
    # disclosure-source registry. Old model_rank/model_reason/source_review
    # and old formal or handoff are not accessed anywhere in this replay.
    source_registry=read(ROOT/"research/trend_buy_company_reviews/latest.json")
    assert source_registry["as_of_date"]==ASOF
    source_by_code={}
    for original in source_registry["reviews"]:
        code=original["code"]
        if code not in chosen:
            continue
        materials=copy.deepcopy(original["source_materials"])
        assert materials and all(
            s.get("asof")==ASOF and s.get("published_at","9999")<=ASOF
            and s.get("url","").startswith("https://")
            for s in materials), ("BAD_ASOF_SOURCE",code)
        source_by_code[code]=materials
    assert set(source_by_code)==set(chosen), "MISSING_SOURCE_POINTERS"

    # Model assessment inputs are newly read from 2026-11-17 frozen industry
    # manifest, F10 source-provenance data and independently rebuilt price shards.
    finance=read(ROOT/"data/research/core_profit_refresh_latest.json")
    program.validate_financial_source(finance,ASOF)
    companies={}
    cache={}
    theme_by_sw3={sector:s["trend_name"] for s in handoff["signals"]
                  for sector in s["industry_codes"]}
    for g in frozen["industries"]:
        sector=g["industry_code"]
        allowed=set(g["selected_codes"])
        for row in history.frozen_industry_rows(ROOT,index,sector,ASOF):
            code=row["code"]
            if code not in allowed:
                continue
            record=finance["records"].get(code)
            assert record and record["source_report"]==program.F10_SOURCE
            assert record["report_date"]==row.get("report_date")
            for k in ("report_date","notice_date","update_date"):
                assert record.get(k) and record[k]<=ASOF, ("FUTURE_FINANCE",code,k)
            patch,_=program.validated_core_patch(row,record,ASOF)
            growth=patch.get("deduct_net_profit_yoy",
                             row.get("deduct_net_profit_yoy"))
            if not isinstance(growth,(int,float)) or not math.isfinite(growth):
                growth=record.get("deduct_net_profit_yoy")
            assert isinstance(growth,(int,float)) and math.isfinite(growth),("GROWTH_MISSING",code)
            ocf=row.get("operating_cashflow_per_share")
            assert isinstance(ocf,(int,float)) and math.isfinite(ocf),("OCF_MISSING",code)
            series,err=history.completed_history(
                history.history_for(ROOT,code,cache),ASOF,row["price"])
            assert err is None,("HISTORY_MISSING",code,err)
            k=history.metrics(series)
            companies[code]={
                "code":code,"name":row["name"],
                "industry_code":sector,"trend_name":theme_by_sw3[sector],
                "growth_yoy":float(growth),"ocf_ps":float(ocf),
                "reported_at":record["notice_date"],
                "report_period":record["report_date"],
                "source_updated_at":record["update_date"],
                "metrics":k,
                "price":row["price"],
                "sources":source_by_code[code],
            }
    assert set(companies)==set(chosen), "MODELED_UNIVERSE_NOT_FROZEN_SELECTED"

    # STEP 3: new research judgment. The 10/20/60 strength percentiles are
    # reconstructed from the 65+day history, the profitability/OCF evidence
    # directly from same-period F10/manifest. No old model rank is an input.
    # Deliberately leave last-5d acceleration to official NEW entry-value
    # attention engine so a rebound is not counted twice as a fundamental fact.
    by_theme=defaultdict(list)
    for x in companies.values():
        by_theme[x["trend_name"]].append(x)
    for theme,group in by_theme.items():
        assert len(group)>=3
        for h in ("10","20","60"):
            perc=history.percentile([x["metrics"]["returns_pct"][h]
                                     for x in group])
            assert all(isinstance(z,(int,float)) for z in perc)
            for company,relative_rank in zip(group,perc):
                company[f"p{h}"]=relative_rank
        for x in group:
            # Straightforward transparent research rubric, not a learned
            # return forecast, nor a shortcut to READY.
            fin=clamp((x["growth_yoy"]+25.)/75.)
            ocf=1. if x["ocf_ps"]>0 else 0.
            score=(.50*fin+.10*ocf+.20*x["p20"]
                   +.15*x["p60"]+.05*x["p10"])
            if x["ocf_ps"]<=0:
                score-=.15
            x["research_score"]=round(score,6)
        group.sort(key=lambda x:(-x["research_score"],x["code"]))
        for rank,x in enumerate(group,1):
            x["model_rank"]=rank

    reviews=[]
    for c in sorted(companies):
        x=companies[c]
        y=x["growth_yoy"];ocf=x["ocf_ps"]
        if x["trend_name"]=="银行":
            pathway="净息差、信贷结构及资产质量通过银行主营利润直接传导"
            falsifier="后续净息差与资产质量恶化、扣非利润或现金流恶化、同业相对强弱持续转负"
        else:
            pathway="门店客流、处方承接、同店效率与费用结构通过线下药品零售直接传导"
            falsifier="后续门店同店经营、扣非利润及现金流恶化且行业价格结构持续失效"
        reason=(f"以11月17日可核验三季报扣非利润同比{y:+.2f}%、每股经营现金流{ocf:+.3f}元为基础；"
                f"重算同主题10/20/60日收益分位分别为{x['p10']:.2f}/{x['p20']:.2f}/{x['p60']:.2f}；"
                f"研究质量值{x['research_score']:.3f}，中期趋势并非追高许可，"
                f"过去涨幅与短线动能由独立入场价值排序复核。")
        reviews.append({
            "code":c,"transmission":"SUPPORTED",
            "review_evidence_date":ASOF,
            "review_basis":(
                f"事实：2026年三季度报告期{x['report_period']}，公告于{x['reported_at']}，"
                f"源记录更新于{x['source_updated_at']}；扣非同比{y:+.4f}%、经营现金流每股{ocf:+.4f}元。"
                f"主营主题关联：{pathway}。近65日以上K线末日为{ASOF}；"
                f"10/20/60日收益分别为"
                f"{x['metrics']['returns_pct']['10']:+.2f}%/"
                f"{x['metrics']['returns_pct']['20']:+.2f}%/"
                f"{x['metrics']['returns_pct']['60']:+.2f}%。"
            ),
            "source_review":(
                "历史截至11月17日的交易所公告索引及已核验F10快照作为来源；"
                "以冻结报告期及已完成日K重新构造公司研究排序。"
                "无可核验历史一致预期，记UNKNOWN；不推断真实资金身份、机构目标价或收益概率。"
                "此为隔离时点模拟，未在本轮重新抓取公告全文。"
            ),
            "source_materials":x["sources"],
            "review_basis_kind":"ASOF_SOURCE_REASSESSMENT_ISOLATED",
            "research_falsifier":falsifier,
            "early_evidence_risk_review_passed":False,
            "evidence_gap":False,
            "historical_analyst_expectation":"UNKNOWN",
            "model_rank":x["model_rank"],
            "model_reason":reason,
        })
    write(SIM/"company-reviews-reassessed.json",{
        "schema_version":"trend_buy_company_reviews_v2",
        "as_of_date":ASOF,
        "research_scope":"FROZEN_PROGRAM_ONLY_INDEPENDENT_SOURCE_REASSESSMENT",
        "explicit_no_prior_formal_or_archive_input":False,
        "source_materials_reused_asof_only":True,
        "old_model_rank_or_reason_used":False,
        "reviews":reviews,
    })

    # STEP 4: actual canonical same-day research reconstruction + scoped
    # technical structure, then the actual production risk-and-rank engine.
    work_research=SIM/"research.json"
    work_structure=SIM/"technical.json"
    cmd=[sys.executable,str(ROOT/"scripts/build_trend_buy_manual_research.py"),
         "--evidence",str(SIM/"company-reviews-reassessed.json"),
         "--admission",str(admission_path),
         "--structure-output",str(work_structure),
         "--output",str(work_research)]
    subprocess.run(cmd,check=True,cwd=ROOT)
    research=read(work_research)
    assert research["trade_date"]==ASOF
    assert research["prescreen_version"]=="CANONICAL"
    assert research["selected_company_count"]==len(reviews)
    assert research["mode"]=="FORMAL"
    assert set(z["code"] for z in research["companies"])==set(chosen)
    assert len(research["screen_audit"]["lightweight_scanned"])==sum(
        g["source_hard_eligible_count"] for g in frozen["industries"])

    cmd=[sys.executable,str(ROOT/"scripts/trend_buy_engine.py"),
         "--research",str(work_research),"--structure",str(work_structure),
         "--output",str(SIM/"result.json")]
    subprocess.run(cmd,check=True,cwd=ROOT)
    result=read(SIM/"result.json")
    assert result["mode"]=="FORMAL" and result["production_eligible"] is True
    assert result["trade_date"]==ASOF
    assert result["coverage"]["judged"]==len(reviews)
    assert sum(result["summary"].values())==len(reviews)

    # Report ONLY temporary simulation output; never call publish/handoff.
    lookup={x["code"]:x for x in result["ready"]+result["wait"]}
    groups=[]
    for g in result["top5_by_theme"]:
        group={"theme":g["trend_name"],
               "attention_policy":g.get("attention_ranking_policy"),
               "top5":[]}
        for i,item in enumerate(g["items"],1):
            z=lookup[item["code"]]
            ev=item.get("opportunity_rank_evidence") or {}
            group["top5"].append({
                "rank":i,"code":z["code"],"name":z["company_name"],
                "status":z["status"],"price":z["current_price"],
                "model_research_rank":z["model_priority"],
                "opportunity_score":ev.get("score"),
                "phase":z.get("trend_phase"),
                "recent5_pct":z.get("phase_evidence",{}).get("return_5d_pct"),
                "previous5_pct":z.get("phase_evidence",{}).get("previous_5d_return_pct"),
                "distance_ma20_pct":(z.get("technical_context") or {}).get("distance_to_ma20_pct"),
                "wait_reason":z.get("wait_reason"),
                "entry_zone":z.get("entry_zone"),
                "invalidation_price":z.get("invalidation_price"),
                "risk_pct":z.get("initial_risk_pct"),
                "upside_R":z.get("upside_to_resistance_R"),
                "attention_judgement":item.get("attention_judgement"),
            })
        groups.append(group)

    with open(SIM/"README.txt","w",encoding="utf-8") as f:
        f.write("Isolated frozen 2026-11-17 market replay. No publication or handoff writes.\n")
    for p,sha in files_before.items():
        assert digest(p)==sha,("PRODUCTION_FILE_TOUCHED",p)
    assert subprocess.run(
        ["git","status","--porcelain","--",*READ_ONLY_PATHS],
        cwd=ROOT,text=True,capture_output=True,check=True).stdout.strip()=="", \
        "PRODUCTION_FILE_MUTATED"

    audit={
        "status":"READ_ONLY_HISTORICAL_SIMULATION_COMPLETE",
        "asof":ASOF,
        "rule":"ENTRY_VALUE_STAGE_V1_PROVISIONAL",
        "source_profile":"frozen_completed_11_17_OHLCV_F10_and_prior_asof_source_pointers",
        "reused_old_model_rank_or_reason":False,
        "fresh_announcements_scraped_in_this_run":False,
        "all_python_candidate_recomputed":True,
        "research_evidence_reassessed":len(reviews),
        "universe":index["company_count"],
        "hard_eligible_total":sum(g["source_hard_eligible_count"]
                                  for g in frozen["industries"]),
        "selected_by_program":len(chosen),
        "trade_risk_engine_executed":True,
        "ready":result["summary"]["ready"],
        "wait":result["summary"]["wait"],
        "uncertain":result["summary"]["uncertain"],
        "drop":result["summary"]["drop"],
        "production_formal_or_handoff_modified":False,
        "groups":groups,
    }
    write(SIM/"summary.json",audit)
    print("ISOLATED_REPLAY_RESULT_JSON "+json.dumps(audit,ensure_ascii=False),flush=True)
    print("ISOLATED_REPLAY_FINAL_CONTRACTS_UNCHANGED",files_before,flush=True)


if __name__=="__main__":
    main()
