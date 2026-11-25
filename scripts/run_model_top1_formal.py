"""Production adapter for V1.6-R1; never computes a plan for non-TOP1."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
try:
    from . import research_model_top1 as model, trend_buy_engine as engine, trend_buy_handoff as handoff
except ImportError:
    import research_model_top1 as model
    import trend_buy_engine as engine
    import trend_buy_handoff as handoff

POLICY = "MODEL_TOP1_V1_6_R1"

def generate(admission_raw, research, structure, evidence, run_id):
    day = research["trade_date"]
    model.require(evidence.get("as_of_date") == day and
                  evidence.get("explicit_no_prior_formal_or_archive_input") is True,
                  "FRESH_EVIDENCE_REQUIRED")
    reviews = evidence["reviews"]
    expected = {c["code"] for c in research["companies"]}
    model.require(len(reviews) == len(expected) and {c["code"] for c in reviews} == expected,
                  "FRESH_REVIEW_SCOPE_MISMATCH")
    for review in reviews:
        model.require(review.get("review_evidence_date") == day and
                      review.get("transmission") in engine.TRANSMISSION and
                      model.nonempty(review.get("source_review")) and
                      model.nonempty(review.get("review_basis")), "INVALID_COMPANY_REVIEW")
        for s in review.get("source_materials", []):
            model.require(s.get("asof") == day and model.nonempty(s.get("published_at")) and
                          s["published_at"][:10] <= day and str(s.get("url", "")).startswith("https://"),
                          "INVALID_REVIEW_SOURCE")
    selections = evidence["top1_selection"]
    result = model.run(admission_raw, research, structure, selections)
    admission = json.loads(admission_raw)
    roster = {c["code"]: c for c in research["companies"]}
    states = {s.lower(): [] for s in engine.STATES}
    groups, focus = [], []
    for item in result["items"]:
        industry, code, status = item["industry_code"], item["top1_code"], item["risk_status"]
        theme = roster[item["candidate_codes"][0]]["trend_name"]
        group = {"trend_name": theme, "industry_code": industry,
                 "attention_ranking_policy": POLICY, "items": []}
        if code is not None:
            row = dict(item["risk_result"])
            row.update({k: None for k in model.PLAN_FIELDS})
            if status == "READY":
                row.update(item["conditional_plan"])
            states[status.lower()].append(row)
            if status in ("READY", "WAIT"):
                ref = item["watch_reference"] if status == "WAIT" else engine.early_watch_reference(row)
                group["items"].append({"code": code, "company_name": row["company_name"],
                    "status": status, "trend_phase": row.get("trend_phase"),
                    "current_price": row["current_price"], "attention_rank": 1,
                    "attention_judgement": item["selection_reason"],
                    "reference": ref, "decision_reason": row.get("decision_reason"),
                    "entry_opportunity": "READY" if status == "READY" else "TREND_WATCH_ONLY"})
        groups.append(group)
        focus.append({"trend_name": theme, "industry_code": industry, "code": code,
                      "status": ("CURRENT_READY_FOCUS" if status == "READY" else
                                 "EARLY_FOCUS_NOT_READY" if status == "WAIT" else
                                 status or item["selection_status"]),
                      "trade_date": day, "decision_reason": item["selection_reason"],
                      "reference": item["watch_reference"], "not_buy_order": True})
    for i,row in enumerate(states["ready"]+states["wait"],1):
        row["rank"]=i
    out = {"schema_version":"trend_buy_result_v2", "result_kind":"a_share_trend_buy_result",
           "status":"COMPLETE", "mode":"FORMAL", "production_eligible":True,
           "selection_policy":POLICY, "prescreen_version":"CANONICAL",
           "run_id":run_id, "trade_date":day, "structure_trade_date":day,
           "structure_contract":structure["contract_id"],
           "publication_audit":research["publication_audit"],
           "coverage":{"selected":len(roster),"judged":result["risk_evaluated_count"],
                       "complete":True, "groups":len(groups)},
           "summary":{k:len(v) for k,v in states.items()},
           "model_thresholds":{"max_entry_risk_pct":engine.MAX_ENTRY_RISK_PCT,
                               "max_ma20_distance_pct":engine.MAX_MA20_DISTANCE_PCT,
                               "min_resistance_reward_R":engine.MIN_UPSIDE_R,
                               "status":"PROVISIONAL_LIVE_PARAMETERS_MONITOR_AND_REVISE"},
           "python_top5_by_industry":admission["industries"],
           "model_top1_selection":selections, "top1_decisions":result["items"],
           "company_reviews":reviews, "top1_by_industry":groups, "focus_watchlist":focus, **states}
    # The frozen Python roster and selected execution groups are distinct.
    projected = handoff.project(out, "prepublish-validation")
    wanted = [x["top1_code"] for x in result["items"] if x["risk_status"] in ("READY","WAIT")]
    model.require([x["code"] for x in projected["items"]] == wanted, "TOP1_HANDOFF_SCOPE_MISMATCH")
    return out

def main():
    p=argparse.ArgumentParser()
    for flag in ("admission","research","structure","evidence","output","run-id"):
        p.add_argument("--"+flag,required=True)
    a=p.parse_args()
    read=lambda x:json.loads(Path(x).read_bytes())
    out=Path(a.output).resolve()
    model.require(out.name not in ("trend_buy_formal_result.json","trend_buy_handoff.json"),
                  "COMPUTATION_MUST_NOT_PUBLISH")
    result=generate(Path(a.admission).read_bytes(),read(a.research),read(a.structure),read(a.evidence),a.run_id)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")

if __name__=="__main__":
    main()
