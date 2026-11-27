"""Read-only historical replay of actual locked TOP1 results, not a profitability claim.

Rebuild technical structure from the checked-out historical OHLCV store truncated
at the archived decision date. Use the archived same-date verified long-range
pivot (the rolling store may no longer contain all of its original 180 bars).
Retrospective entry assessments are separate from the immutable original results.
Only after all decisions are calculated, inspect available next-session closes.
"""
import json
from pathlib import Path
from unittest.mock import patch

from scripts import build_full_market_price_structure as technical
from scripts import trend_buy_entry_assessment as entry
from scripts import trend_buy_engine as engine
from scripts.price_inputs import SelectedStockStructures

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/top1_entry_replay_20261125_27.json"

def run():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    records = []
    observed = {}
    for case in fixture["cases"]:
        day, code = case["trade_date"], case["locked_code"]
        original = case["risk_result"]
        ctx = original["technical_context"]
        assert code in case["candidate_codes"] and original["code"] == code
        assert original["data_date"] == day
        all_rows = technical.rows_for(code)
        bars = [b for b in all_rows if b["date"] <= day]
        assert len(bars) >= 65 and bars[-1]["date"] == day, (day, code, "history_missing")
        assert all(b["date"] <= day for b in bars)
        p = original["current_price"]
        assert abs(bars[-1]["close"] - p) <= .011, (day, code, "history_price_mismatch")
        s = technical.base_metrics(code, original["company_name"], bars[-65:], {"price": p}, day, min_points=65)
        for key in ("ma20", "ma60"):
            assert abs(s[key] - ctx[key]) < .011, (day, code, key, s[key], ctx[key])
        market_return = s["raw_return_20d"] - ctx["relative_strength_20d_vs_market_pct"]/100
        s = technical.classify(s, market_return)
        # Production uses 65 bars for local structure, separately 120–180 for overhead.
        extended = SelectedStockStructures._attention_resistance(bars[-180:], p, day)
        archived_extended = ctx["attention_resistance"]
        assert (extended.get("status"), extended.get("price"), extended.get("date")) == (archived_extended.get("status"), archived_extended.get("price"), archived_extended.get("date")), (day,code,"extended_pivot_drift",extended,archived_extended)
        s["attention_resistance"] = extended
        for key in ("breakout_level", "first_effective_resistance"):
            old, new = ctx.get(key), s.get(key)
            if key == "first_effective_resistance":
                old = old.get("price") if old else None
                new = new.get("price") if new else None
            assert ((old is None and new is None) or
                    (engine.pos(old) and engine.pos(new) and abs(old-new) < .011)), (day,code,key,old,new)
        c = {**original, "asof_price": p, "theme_link_verified": True}
        # Existing engine uses only the reconstructed same-day structure.
        baseline = engine.evaluate_candidate(c, s, day)
        assert baseline["status"] == case["original_status"], (day,code,"baseline_drift",baseline["status"])
        assessment = case["retrospective_assessment"]
        # Historical compatibility remains enabled in production; this explicit
        # test-only counterfactual evaluates the proposed contract on old dates.
        with patch.object(entry, "CUTOVER_AFTER", "1900-01-01"):
            new, ref = entry.evaluate(c, s, day, assessment)
        assert new["code"] == code and new["status"] == baseline["status"]
        if new["status"] == "READY":
            for key in ("entry_zone", "invalidation_price", "initial_risk_pct", "upside_to_resistance_R"):
                assert new[key] == case["original_conditional_plan"][key], (day,code,key,new[key],case["original_conditional_plan"][key])
        if new["status"] == "WAIT":
            assert ref["reference_zone"] is None and ref["invalidation_price"] is None
            assert all(x["not_buy_order"] for x in ref["research_scenarios"])
            assert entry.validate_assessment(assessment,s,code,day)[1] == "VERIFIED"
        old_ref = case["original_watch_reference"] or {}
        record = {"trade_date":day,"code":code,"company_name":original["company_name"],
                  "source_commit":case["source_commit"],"history_bars":len(bars),
                  "old_status":baseline["status"],"new_status":new["status"],
                  "close":p,"old_watch":old_ref.get("reference_trigger_price"),
                  "new_watch":ref.get("reference_trigger_price") if ref else None,
                  "scenarios":new.get("entry_research_scenarios"),
                  "original_ready_plan_preserved":new["status"]=="READY"}
        records.append(record)
        observed[(day,code)] = all_rows
    # Outcome inspection is deliberately outside the selection/entry loop.
    for r in records:
        future = [b for b in observed[(r["trade_date"],r["code"])] if b["date"] > r["trade_date"]]
        r["forward_close_returns_pct"] = {
            str(n): round((future[n-1]["close"]/r["close"]-1)*100,2) if len(future)>=n else None
            for n in (1,3,5)}
        print("HISTORICAL_CASE " + json.dumps(r,ensure_ascii=False,sort_keys=True))
    summary = {"reference_dates":len({r["trade_date"] for r in records}),
               "selected_cases":len(records),
               "ready_preserved":sum(r["original_ready_plan_preserved"] for r in records),
               "wait_cases":sum(r["new_status"]=="WAIT" for r in records),
               "wait_with_verified_nearby_anchor":sum(r["new_status"]=="WAIT" and
                   engine.pos(r["new_watch"]) and abs(r["new_watch"]/r["close"]-1)<=.08 for r in records),
               "old_wait_with_nearby_anchor":sum(r["old_status"]=="WAIT" and
                   engine.pos(r["old_watch"]) and abs(r["old_watch"]/r["close"]-1)<=.08 for r in records),
               "status_changes":sum(r["new_status"]!=r["old_status"] for r in records),
               "mature_1d":sum(r["forward_close_returns_pct"]["1"] is not None for r in records),
               "mature_3d":sum(r["forward_close_returns_pct"]["3"] is not None for r in records),
               "mature_5d":sum(r["forward_close_returns_pct"]["5"] is not None for r in records),
               "realized_trade_returns_evaluated":False,
               "model_prospective_performance_evaluated":False}
    print("HISTORICAL_SUMMARY " + json.dumps(summary,ensure_ascii=False,sort_keys=True))
    return records,summary

if __name__ == "__main__":
    run()
