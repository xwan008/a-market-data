"""Isolated regression for frozen A/B Top5; no production mutation."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments import top5_ab_pairwise_shadow as ab  # noqa: E402

FIXTURE = ROOT / "experiments/fixtures/top5_ab_2026-10-23.json"
ASOF = "2026-10-23"


class PairwiseShadowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frozen = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_same_frozen_top5_and_ab_output(self):
        results = ab.run(self.frozen, ASOF)
        self.assertEqual(results["kind"], "TOP5_PR54_PAIRWISE_AB_SHADOW")
        self.assertTrue(results["read_only"])
        self.assertFalse(results["modifies_formal_or_ready"])
        self.assertEqual(len(results["main"]), 2)
        named = {g["theme"]:g for g in results["main"]}
        industrial=named["工业自动化/机器人"]
        self.assertEqual(industrial["A_formal_order"],
                         ["603275","603416","002979","603025","603583"])
        for theme,group in named.items():
            self.assertEqual(len(group["A_formal_order"]),5)
            self.assertEqual(sum(map(len,group["B_evidence_tiers"])),5)
            self.assertTrue(group["membership_unchanged"])
            self.assertEqual(len(group["pairwise"]),10)
            self.assertFalse(group["non_transitive_conflict"])
            self.assertEqual(len(group["sensitivity"]),3)
            self.assertTrue(all(x["observation_stop"] is None
                                for x in group["candidate_evidence"]))
        codes={x["code"]:x for x in industrial["candidate_evidence"]}
        self.assertEqual(codes["603416"]["support_close_band"], [44.46,44.46])
        self.assertTrue(codes["603416"]["support_intraday_broken"])
        self.assertTrue(codes["603416"]["recent_support_with_volume"])
        self.assertEqual(codes["603275"]["support_close_band"], [34.81,34.83])
        self.assertTrue(codes["603275"]["recent_support_with_volume"])
        self.assertIsNone(codes["603416"]["observation_stop"])
        print("TOP5_AB_20261023_RESULT="+json.dumps(
            [{"theme":g["theme"],"A":g["A_formal_order"],
              "B_tiers":g["B_evidence_tiers"],
              "comparisons":[{"a":p["a"],"b":p["b"],"lead":p["lead"],
                              "domains":p["domains"]} for p in g["pairwise"]],
              "sensitivity":g["sensitivity"]} for g in results["main"]],
            ensure_ascii=False,separators=(",",":")))

    def test_rank_independent_of_formal_ready_rr_and_long_history(self):
        clone = copy.deepcopy(self.frozen)
        base = ab.shadow(clone,ASOF)
        for row in clone["rows"]:
            row["status"]="READY" if row["status"]=="WAIT" else "WAIT"
            row["structure_confirmed"]=True
            row["entry_zone"]=[20,22]
            row["invalidation_price"]=5
            row["upside_to_resistance_R"]=99.0
            row["trend_phase"]="REACCELERATING"
            row["technical_context"]["attention_resistance"]={"price":200}
            row["technical_context"]["prior_60d_high"]=300
        altered=ab.shadow(clone,ASOF)
        self.assertEqual([x["B_evidence_tiers"] for x in altered],
                         [x["B_evidence_tiers"] for x in base])
        self.assertEqual([x["pairwise"] for x in altered],
                         [x["pairwise"] for x in base])

    def test_frozen_row_order_and_future_data_do_not_change_result(self):
        clone=copy.deepcopy(self.frozen)
        base=ab.run(clone,ASOF)
        clone["rows"].reverse()
        after=ab.run(clone,ASOF)
        self.assertEqual(after["main"],base["main"])
        with self.assertRaisesRegex(ValueError,"snapshot_asof_mismatch"):
            ab.run(clone,"2026-10-26")
        clone["rows"][0]["data_date"]="2026-10-26"
        with self.assertRaisesRegex(ValueError,"mismatched_or_future"):
            ab.run(clone,ASOF)

    def test_support_observed_not_executable_and_no_new_stop(self):
        a={"code":"a","name":"A","five_day_break":True,
           "recent_support_with_volume":True,
           "return_5d_pct":5,"positive_days_5d":3,
           "max_close_drawdown_10d_pct":-3,
           "volume_ratio_1d_vs_20d":1.5,"volume_ratio_5d_vs_20d":1.2,
           "close_location_pct":90,"relative_strength_20d_vs_market_pct":3,
           "up_to_down_volume_ratio_5d":1.3,"abs_distance_to_ma20_pct":2}
        b=dict(a,code="b",name="B",recent_support_with_volume=False)
        one=ab.compare_domains(a,b)
        self.assertEqual(one["domains"]["structure"],1)
        self.assertEqual(one["lead"],0)  # one observed feature cannot dictate rank
        c=dict(b,code="c",abs_distance_to_ma20_pct=4.5)
        two=ab.compare_domains(a,c)
        self.assertEqual(two["lead"],1)  # structure + location, no adverse dimensions

    def test_trend_and_volume_conflicts_remain_ties(self):
        a={"code":"a","five_day_break":True,"recent_support_with_volume":False,
           "return_5d_pct":10,"positive_days_5d":4,"max_close_drawdown_10d_pct":-10,
           "volume_ratio_1d_vs_20d":2.5,"volume_ratio_5d_vs_20d":1.5,
           "close_location_pct":99,"relative_strength_20d_vs_market_pct":0,
           "up_to_down_volume_ratio_5d":1.0,"abs_distance_to_ma20_pct":5}
        b=dict(a,code="b",return_5d_pct=4,positive_days_5d=3,
               max_close_drawdown_10d_pct=-2,
               volume_ratio_1d_vs_20d=1.5,volume_ratio_5d_vs_20d=1.1,
               close_location_pct=89,relative_strength_20d_vs_market_pct=10,
               up_to_down_volume_ratio_5d=1.8,abs_distance_to_ma20_pct=2)
        c=ab.compare_domains(a,b)
        self.assertEqual(c["domains"]["trend"],1)
        self.assertEqual(c["domains"]["volume"],1)  # 3 wins despite some adverse
        self.assertEqual(c["domains"]["position"],-1)
        self.assertEqual(c["lead"],0)  # 2 dimensions win, 1 loses -> unresolved


if __name__=="__main__":
    unittest.main()
