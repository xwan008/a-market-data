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


    def test_confirmed_bullish_structure_break_does_not_mean_invalidated(self):
        def row(state):
            return {"code":state,"name":"synthetic","price":10,
                    "ma20":9.8,"ma60":11.0,"pe_ttm":15,
                    "revenue_yoy":10,"net_profit_yoy":12,
                    "roe":10,"basic_eps":0.3,
                    "operating_cashflow_per_share":.1,
                    "break_state":state}
        a=mod.scores([row("intact"),row("bullish_structure_break_confirmed")])
        # Price is above MA20, below MA60: a repair has trend health 0.5.
        self.assertEqual(a[0][4],.5)
        self.assertEqual(a[1][4],.5)
        self.assertEqual(a[0][0],a[1][0])

    def test_confirmed_bearish_or_undirected_break_is_still_rejected(self):
        def row(state):
            return {"code":state,"name":"synthetic","price":10,
                    "ma20":9.8,"ma60":9.5,"pe_ttm":15,
                    "revenue_yoy":10,"net_profit_yoy":12,"roe":10,
                    "basic_eps":.3,"operating_cashflow_per_share":.1,
                    "break_state":state}
        states=["intact","bearish_structure_break_confirmed",
                "undirected_break_confirmed","structure_invalidated"]
        out=mod.scores([row(s) for s in states])
        self.assertEqual(out[0][4],1)
        self.assertEqual([x[4] for x in out[1:]], [0,0,0])

    def test_bullish_break_below_both_mas_stays_low_quality_not_high(self):
        x={"code":"test","name":"synthetic","price":8,"ma20":10,"ma60":11,
           "pe_ttm":15,"revenue_yoy":10,"net_profit_yoy":12,"roe":10,
           "basic_eps":.3,"operating_cashflow_per_share":.1,
           "break_state":"bullish_structure_break_confirmed"}
        self.assertEqual(mod.scores([x])[0][4],.25)


if __name__=="__main__":
    unittest.main()
