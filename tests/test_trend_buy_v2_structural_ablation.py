"""V2.1 structural recovery and earnings-quality: shadow-only contracts."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"experiments"))
spec=importlib.util.spec_from_file_location(
    "structural", ROOT/"experiments/trend_buy_v2_structural_ablation.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
DAY="2026-11-05"


def candidate(code="600001",phase="REPAIRING",price=10,ma60=12,slope=-4,
              return3=17,previous5=-8,rs=-5):
    return {
        "code":code,"company_name":code,"status":"WAIT",
        "data_date":DAY,"current_price":price,"trend_phase":phase,
        "technical_context":{
          "ma20":9.7,"ma60":ma60,"ma20_slope_5d_pct":slope,
          "volume_ratio_1d_vs_20d":2.1,
          "volume_ratio_5d_vs_20d":1.5,
          "relative_strength_20d_vs_market_pct":rs,
          "close_location_pct":70,
          "attention_resistance":{
              "status":"VERIFIED","price":10.2,"date":"2026-09-15",
              "source":"asof_180bar_confirmed_pivot","history_points":180,
          },
        },
        "phase_evidence":{
          "return_3d_pct":return3,"previous_5d_return_pct":previous5,
          "return_5d_pct":7,"positive_days_5d":3,"fresh_break":True,
        },
        "entry_zone":None,"invalidation_price":None,
    }


class StructuralAblationTests(unittest.TestCase):
    def test_sharp_repair_below_ma60_gets_continuation_warning(self):
        r=candidate()
        value=mod.score_structural(r,DAY,.6)
        self.assertLess(value["v21_structural_score"],value["v20_baseline_score"])
        self.assertGreater(value["structural_penalties"]["fast_rebound_after_drawdown"],0)
        self.assertGreater(value["structural_penalties"]["falling_ma20_below_ma60"],0)
        self.assertIsNone(value["risk_reward_R"])
        self.assertFalse(value["upgrade_to_ready"])

    def test_above_ma60_rising_ma20_not_automatically_punished(self):
        r=candidate(phase="INITIATING",ma60=9.1,slope=2,
                    return3=5,previous5=3,rs=10)
        r["technical_context"]["attention_resistance"]["price"]=12.0
        out=mod.score_structural(r,DAY)
        self.assertEqual(sum(out["structural_penalties"].values()),0)
        self.assertEqual(out["v20_baseline_score"],out["v21_structural_score"])

    def test_earnings_risk_requires_past_document_and_finite_amounts(self):
        report={"published_at":"2026-10-27",
                "attributable_profit_cny":234611745.19,
                "deducted_attributable_profit_cny":115251654.93,
                "q3_profit_yoy_pct":-79.15}
        risk,basis=mod.audited_earnings_penalty(report,DAY)
        self.assertGreater(risk,.04)
        self.assertEqual(basis,"AUDITED_NONRECURRING_AND_QUARTERLY")
        self.assertEqual(mod.audited_earnings_penalty(None,DAY),
                         (0.0,"NOT_IN_CORE_SCORING"))
        with self.assertRaisesRegex(ValueError,"future"):
            mod.audited_earnings_penalty({**report,"published_at":"2026-11-06"},DAY)

    def test_shadow_can_rank_even_if_all_wait(self):
        a=candidate(code="600001")
        b=candidate(code="600002",phase="INITIATING",ma60=9.1,
                    slope=2,return3=3,previous5=3,rs=11)
        formal={"trade_date":DAY,"ready":[],"wait":[a,b],
                "top5_by_theme":[{"trend_name":"测试行业",
                    "items":[{"code":"600001"},{"code":"600002"}]}]}
        result=mod.rerank_structural(formal,{"600001":.9,"600002":.45})
        self.assertEqual({x["code"] for x in result["groups"][0]["items"]},
                         {"600001","600002"})
        self.assertTrue(all(x["status"]=="WAIT" and not x["upgrade_to_ready"]
                            for x in result["groups"][0]["items"]))

    def test_missing_structural_evidence_does_not_become_fabricated(self):
        r=candidate()
        r["technical_context"].pop("ma20_slope_5d_pct")
        value=mod.score_structural(r,DAY)
        self.assertIn("ma20_slope_5d_pct",value["incomplete_structural_fields"])
        self.assertEqual(value["structural_penalties"]["falling_ma20_below_ma60"],0)


if __name__=="__main__":
    unittest.main()
