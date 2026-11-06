"""V4 program-first, bounded research budget and point-in-time safety."""
import copy
from datetime import date,timedelta
import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location(
    "v4",ROOT/"experiments/trend_buy_v4_python_prescreen_shadow.py")
v4=importlib.util.module_from_spec(spec)
spec.loader.exec_module(v4)
DAY="2026-11-05"

def make_history(code="000001",base=10,growth=.003):
    start=date(2026,8,1)
    bars=[]
    for i in range(100):
        dt=start+timedelta(days=i)
        if dt>date.fromisoformat(DAY):
            break
        p=round(base*((1+growth)**i),5)
        bars.append({"date":dt.isoformat(),"open":p,"close":p,
                     "high":p*1.01,"low":p*.99,"volume":100+i})
    return {"history":bars,"history_basis":"reference_adjusted"}

def item(n,trend=10,entry=.5,finance=.6):
    return {"code":f"{n:06d}","name":f"company{n}",
        "industry_code":"S123456","asof_date":DAY,
        "fundamental_score":finance,"entry_reference_score":entry,
        "price_structure_score":.6,
        "core_profit_growth_verified":False,"financial_evidence_gaps":["CORE_PROFIT_GROWTH_NOT_AVAILABLE"],
        "history":{"returns_pct":{
            "5":trend*.2,"10":trend*.5,"20":trend,"60":trend*2},
            "positive_days_10":max(1,min(10,n%10+1)),
            "volume_1d_vs_prior20_median":1.1}}

class V4PrescreenTests(unittest.TestCase):
    def test_history_future_bar_ignored(self):
        stock=make_history()
        cut=[x for x in stock["history"] if x["date"]<=DAY]
        # The generator ends at the date, make explicit future monster candle.
        base=copy.deepcopy(stock)
        after={"date":"2026-11-06","close":999,
               "open":999,"high":1000,"low":998,"volume":100000}
        base["history"].append(after)
        known=cut[-1]["close"]
        left,error=v4.completed_history(stock,DAY,known)
        right,error2=v4.completed_history(base,DAY,known)
        self.assertIsNone(error)
        self.assertIsNone(error2)
        self.assertEqual(v4.metrics(left),v4.metrics(right))

    def test_history_missing_and_basis_mismatch(self):
        stock=make_history()
        p=stock["history"][-1]["close"]
        self.assertIsNotNone(v4.completed_history(stock,DAY,p*1.05)[1])
        small={"history":stock["history"][-10:]}
        self.assertIsNotNone(v4.completed_history(small,DAY,p)[1])

    def test_one_industry_exactly_five_with_three_leaders_two_entries(self):
        rows=[item(n,trend=n*.9,entry=(10-n)/10) for n in range(1,10)]
        chosen,meta=v4.dual_channel(rows)
        self.assertEqual(len(chosen),5)
        self.assertEqual(len({x["code"] for x in chosen}),5)
        self.assertEqual(sum(x["selected_channel"]=="LEADERSHIP" for x in chosen),3)
        self.assertEqual(sum(x["selected_channel"]=="ENTRY_LOCATION" for x in chosen),2)
        self.assertEqual(meta["max_model_research_per_sw3"],5)

    def test_financial_unknown_is_not_called_verified(self):
        records=[item(n) for n in range(1,6)]
        with self.assertRaisesRegex(ValueError,"v4_fixed_five"):
            v4.dual_channel(records,slots=6)
        self.assertEqual(v4.percentile([None,None,.3]),[None,None,None])

    def test_original_model_budget_not_increased_when_fewer_companies(self):
        records=[item(n,trend=n) for n in range(1,4)]
        chosen,_=v4.dual_channel(records)
        self.assertEqual(len(chosen),3)
        self.assertEqual(len({r["code"] for r in chosen}),3)

    def test_run_requires_same_day_frozen_lightweight_coverage(self):
        wrong={"trade_date":DAY,
               "screen_audit":{"hard_eligible":3,"lightweight_scanned":[],
                               "pre_screen_selected":[]}}
        with self.assertRaisesRegex(ValueError,"lightweight_coverage"):
            v4.run(ROOT,wrong,{"trade_date":DAY})

    def test_hard_research_scope_and_no_formal_upgrade(self):
        fake=[item(n,trend=n) for n in range(1,6)]
        scanned=[{"code":x["code"],"industry_code":"S123456"}
                 for x in fake]
        screen={"trade_date":DAY,"screen_audit":{
            "hard_eligible":len(scanned),"lightweight_scanned":scanned,
            "pre_screen_selected":scanned[:4]}}
        index={"trade_date":DAY}
        with patch.object(v4,"frozen_industry_rows",return_value=[
                {"code":x["code"],"industry_name":"test"} for x in fake]):
            with patch.object(v4,"select_company_rows",
                              return_value=(fake,[])):
                out=v4.run(ROOT,screen,index)
        g=out["industry_groups"][0]
        self.assertLessEqual(g["model_research_slots_required"],5)
        self.assertEqual({x["code"] for x in g["model_deep_review_packets"]},
                         set(g["v4_research_codes"]))
        self.assertEqual(len(g["model_deep_review_packets"]),len(g["v4_research_codes"]))
        self.assertTrue(all(x["deep_review_status"]=="PENDING_IN_SHADOW"
                            for x in g["model_deep_review_packets"]))
        self.assertTrue(all(x["source_requirements"]["expected_growth_revision"]
                            =="DATE_STAMPED_FACT_OR_UNKNOWN"
                            for x in g["model_deep_review_packets"]))
        self.assertEqual(out["mode"],"SHADOW_PROGRAM_ONLY_NO_MODEL_CALL")
        self.assertFalse(out["rules"]["business_review_in_python"])
        self.assertTrue(out["rules"]["ready_wait_and_handoff_untouched"])

if __name__=="__main__":
    unittest.main()
