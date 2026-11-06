"""Isolation tests: change only overheat ranking priority, never trade gates."""
from pathlib import Path
import importlib.util
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location(
    "v3_soft",ROOT/"experiments/trend_buy_v3_minimal_overheat_shadow.py")
v3=importlib.util.module_from_spec(spec)
spec.loader.exec_module(v3)
DAY="2026-11-05"


def row(code,status="WAIT",gap=11,ratio=3.2,rs=14,loc=90):
    ma20=10
    price=ma20*(1+gap/100)
    return {"code":code,"company_name":code,"data_date":DAY,
            "status":status,"trend_phase":"INITIATING",
            "current_price":price,
            "technical_context":{
              "ma20":ma20,"ma60":9.2,
              "distance_to_ma20_pct":gap,
              "volume_ratio_1d_vs_20d":ratio,
              "volume_ratio_5d_vs_20d":2.2,
              "relative_strength_20d_vs_market_pct":rs,
              "close_location_pct":loc,
              "chase_risk":"high" if gap>8 else "normal"},
            "phase_evidence":{
              "return_5d_pct":9,"positive_days_5d":4,
              "fresh_break":True}}


class MinimalOverheatTests(unittest.TestCase):
    def test_stronger_overextended_fresh_break_can_beat_weak_safe(self):
        leader=row("001111",gap=11,ratio=3.2,rs=14,loc=92)
        follower=row("002222",gap=3,ratio=1.32,rs=2,loc=65)
        old0=v3.engine.top5_rank_key(leader)
        old1=v3.engine.top5_rank_key(follower)
        self.assertGreater(old0,old1)
        new0=v3.eligibility_and_key(leader,DAY)
        new1=v3.eligibility_and_key(follower,DAY)
        self.assertLess(new0["ranking_key"],new1["ranking_key"])
        self.assertGreater(new0["continuous_overheat_cost"],0)
        self.assertEqual(new1["continuous_overheat_cost"],0)
        self.assertEqual(new0["status"],"WAIT")

    def test_overextension_is_not_automatically_a_buy(self):
        ready=row("000001",status="READY",gap=3,ratio=1.4)
        wait=row("000002",status="WAIT",gap=9,ratio=3.6,rs=18,loc=95)
        formal={"trade_date":DAY,"ready":[ready],"wait":[wait],
                "top5_by_theme":[{"trend_name":"测试",
                    "items":[{"code":"000002"},{"code":"000001"}]}]}
        result=v3.rerank_formal(formal)
        self.assertEqual(result["groups"][0]["shadow_codes"],["000001","000002"])
        self.assertEqual(ready["status"],"READY")
        self.assertEqual(wait["status"],"WAIT")
        self.assertFalse(result["risk_gate_changed"])
        self.assertFalse(result["pre_screen_membership_changed"])

    def test_negative_gap_not_high_price_overextension(self):
        below=v3.eligibility_and_key(row("000003",gap=-12),DAY)
        self.assertEqual(below["continuous_overheat_cost"],0)
        self.assertLess(below["ma20_distance_pct"],0)

    def test_missing_ma20_is_not_assumed_safe(self):
        r=row("000004",gap=2)
        r["technical_context"].pop("distance_to_ma20_pct")
        r["technical_context"].pop("ma20")
        result=v3.eligibility_and_key(r,DAY)
        self.assertEqual(result["continuous_overheat_cost"],.15)

    def test_asof_date_and_scope_fail_closed(self):
        a=row("000005")
        with self.assertRaisesRegex(ValueError,"stale_or_future"):
            v3.eligibility_and_key(a,"2026-11-04")
        with self.assertRaisesRegex(ValueError,"unresearchable_status"):
            v3.eligibility_and_key({**a,"status":"UNCERTAIN"},DAY)
        formal={"trade_date":DAY,"ready":[],"wait":[a],
                "top5_by_theme":[{"trend_name":"测试",
                    "items":[{"code":"999999"}]}]}
        with self.assertRaisesRegex(ValueError,"published_top5_without_researched"):
            v3.rerank_formal(formal)


if __name__=="__main__":
    unittest.main()
