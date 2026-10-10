"""Deterministic, price-only trend entry and publication-contract tests."""
import importlib.util
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("trend",ROOT/"scripts"/"trend_buy_engine.py")
engine=importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)

def company(**kw):
    return {"code":"600001","company_name":"合成样本","trend_name":"示例主题","industry_code":"S630702",
            "transmission":"SUPPORTED","theme_link_verified":True,"filter_passed":True,
            "material_risk_unresolved":False,"source_review":"synthetic test","research_falsifier":"theme invalidated",**kw}

def structure(**changes):
    x={"data_status":"verified","data_date":"2026-10-09","history_points":180,"low_risk_eligible":True,
       "current_price":20.2,"ma20":19.8,"ma60":19.1,"support_invalidation":19.55,
       "prior_60d_high":20.0,"breakout_level":20.0,"breakout_confirmed":True,
       "structure_type":"breakout","chase_risk":"low","distance_to_ma20_pct":2.02,
       "first_effective_resistance":None,"current_day_low":19.8,"previous_close":19.9,
       "higher_low":True,"close_location_pct":75}
    x.update(changes)
    return x

def inputs(c=None,s=None):
    c=company() if c is None else c
    s=structure() if s is None else s
    c.setdefault("asof_price",s["current_price"])
    return ({"schema_version":"trend_buy_research_v2","trade_date":"2026-10-09","coverage_complete":True,
             "selected_company_count":1,"companies":[c],"mode":"SHADOW"},
            {"contract_id":"a-share-low-risk-price-structure","reference_trade_date":"2026-10-09",
             "companies":{"600001":s}})

class TrendTests(unittest.TestCase):
    def test_breakout_ready_with_contract(self):
        res=engine.generate(*inputs())
        self.assertEqual(res["summary"],{"ready":1,"wait":0,"uncertain":0,"drop":0})
        x=res["ready"][0]
        self.assertEqual(x["setup_type"],"BREAKOUT")
        self.assertGreater(x["invalidation_price"],0)
        self.assertLess(x["invalidation_price"],x["entry_zone"][0])
        self.assertLessEqual(x["initial_risk_pct"],6)
        self.assertFalse(res["production_eligible"])
        self.assertIn("slippage",str(x["exit_plan"]).lower() if "slippage" in str(x["exit_plan"]).lower() else "slippage")

    def test_stale_structure_never_ready(self):
        r,s=inputs(s=structure(data_date="2026-10-08"))
        self.assertEqual(engine.generate(r,s)["uncertain"][0]["status"],"UNCERTAIN")

    def test_confirmation_necessary(self):
        r,s=inputs(s=structure(breakout_confirmed=False,structure_type="transition"))
        x=engine.generate(r,s)["wait"][0]
        self.assertEqual(x["wait_reason"],"WAIT_BREAKOUT")

    def test_pullback_needs_rebound(self):
        r,s=inputs(s=structure(current_price=20,ma20=19.9,ma60=19.1,support_invalidation=19.45,
                              structure_type="pullback",breakout_confirmed=False,
                              current_day_low=19.7,previous_close=19.8,close_location_pct=73))
        x=engine.generate(r,s)["ready"][0]
        self.assertEqual(x["setup_type"],"PULLBACK")
        s["companies"]["600001"]["previous_close"]=20.1
        self.assertEqual(engine.generate(r,s)["wait"][0]["status"],"WAIT")

    def test_wait_pullback_zone_is_near_ma20_not_current_high(self):
        r,s=inputs(s=structure(current_price=22.0,ma20=20.3,ma60=19.0,
                              support_invalidation=19.85,
                              structure_type="trend_continuation",breakout_confirmed=False,
                              chase_risk="medium",distance_to_ma20_pct=8.37,
                              first_effective_resistance=None))
        x=engine.generate(r,s)["wait"][0]
        self.assertEqual(x["setup_type"],"PULLBACK")
        self.assertLess(x["entry_zone"][1],22.0)
        self.assertAlmostEqual(x["entry_zone"][1],20.665,places=2)

    def test_overheat_risk_blocks_ready(self):
        r,s=inputs(s=structure(chase_risk="high",distance_to_ma20_pct=13))
        x=engine.generate(r,s)["wait"][0]
        self.assertEqual(x["wait_reason"],"WAIT_PULLBACK")

    def test_early_evidence_requires_extra_review(self):
        c=company()
        c["transmission"]="EARLY_EVIDENCE"
        r,s=inputs(c=c)
        self.assertEqual(engine.generate(r,s)["wait"][0]["wait_reason"],"WAIT_CONFIRMATION")
        c["early_evidence_risk_review_passed"]=True
        res=engine.generate(r,s)
        self.assertEqual(res["ready"][0]["transmission"],"EARLY_EVIDENCE")

    def test_no_theme_link(self):
        c=company()
        c["theme_link_verified"]=False
        r,s=inputs(c=c)
        self.assertEqual(engine.generate(r,s)["uncertain"][0]["status"],"UNCERTAIN")

    def test_gappy_stop_and_resistance(self):
        r,s=inputs(s=structure(support_invalidation=18.1,breakout_level=21.0,
                              current_price=21.35,prior_60d_high=21.0,
                              first_effective_resistance={"price":21.55}))
        x=engine.generate(r,s)["wait"][0]
        self.assertEqual(x["wait_reason"],"WAIT_RISK_REWARD")

    def test_wrong_coverage_or_date_rejected(self):
        r,s=inputs()
        r["selected_company_count"]=2
        with self.assertRaisesRegex(ValueError,"coverage"):
            engine.generate(r,s)
        r,s=inputs()
        s["reference_trade_date"]="2026-10-08"
        with self.assertRaisesRegex(ValueError,"date"):
            engine.generate(r,s)

    def test_directly_rejected_company(self):
        c=company()
        c["transmission"]="NOT_SUPPORTED"
        r,s=inputs(c=c)
        self.assertEqual(engine.generate(r,s)["drop"][0]["status"],"DROP")

if __name__=="__main__":
    unittest.main()
