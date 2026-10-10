"""Lightweight dynamic pre-screen. No business research and no per-stock K-line reads."""
import importlib.util
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("dynamic_prescreen", ROOT/"scripts"/"build_trend_buy_manual_research.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

DAY="2026-10-09"

def technical(**changes):
    base={"data_status":"verified","data_date":DAY,"history_points":180,
          "low_risk_eligible":True,"current_price":10.0,
          "ma20":9.8,"ma60":10.1,"trend_phase":"REPAIRING",
          "phase_evidence":{"fresh_break":True,"prior_5d_high":10.35},
          "support_invalidation":9.4,
          "higher_low":False,"volume_ratio_1d_vs_20d":2.1,
          "volume_ratio_5d_vs_20d":1.7,
          "close_location_pct":90,
          "relative_strength_20d_vs_market_pct":4,
          "chase_risk":"low"}
    base.update(changes)
    return base

class PreScreenTests(unittest.TestCase):
    def test_repair_below_ma60_keeps_research_right(self):
        score, reason=mod.compact_opportunity(technical(),DAY)
        self.assertIsNone(reason)
        self.assertEqual(score["trend_phase"],"REPAIRING")
        self.assertGreater(score["opportunity_score"],.5)
        self.assertTrue(score["reference_is_not_buy_signal"])

    def test_cooling_leader_does_not_take_top5_research_slot(self):
        score, reason=mod.compact_opportunity(technical(trend_phase="COOLING"),DAY)
        self.assertIsNone(score)
        self.assertEqual(reason,"NEW_ENTRY_COOLING")

    def test_invalid_history_or_date_fails_closed(self):
        for kw in ({"data_date":"2026-10-08"},{"history_points":60},
                   {"data_status":"unavailable"}):
            score, reason=mod.compact_opportunity(technical(**kw),DAY)
            self.assertIsNone(score)
            self.assertEqual(reason,"PRICE_STRUCTURE_UNVERIFIED")

    def test_no_real_support_cannot_get_full_entry_score(self):
        a,_=mod.compact_opportunity(technical(),DAY)
        b,_=mod.compact_opportunity(technical(support_invalidation=None),DAY)
        self.assertLess(b["entry_score"],a["entry_score"])
        self.assertIsNone(b["reference_risk_pct"])

    def test_high_chase_risk_reduces_opportunity(self):
        a,_=mod.compact_opportunity(technical(),DAY)
        b,_=mod.compact_opportunity(technical(chase_risk="high"),DAY)
        self.assertLess(b["opportunity_score"],a["opportunity_score"])

if __name__=="__main__":
    unittest.main()
