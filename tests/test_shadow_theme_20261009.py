import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_theme_handoff_routes import check_theme_routes


class IndependentThemeShadowReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shadow = json.loads((ROOT / "research/backtests/trend_theme_shadow_replay_20261009.json").read_text())
        cls.index = json.loads((ROOT / "data/low_risk/index.json").read_text())

    def test_strict_source_and_full_candidate_accounting(self):
        s = self.shadow
        self.assertEqual(s["asof_cutoff_local"], "2026-10-09T18:40:00+08:00")
        self.assertTrue(s["shadow_only"])
        c = s["candidate_audit"]
        self.assertEqual(len(c), 78)
        self.assertEqual(len({x["code"] for x in c}), 78)
        self.assertEqual(sum(x["initial_status"] == "MODEL_REVIEW" for x in c), 20)
        self.assertEqual(sum(x["initial_status"] == "CAPACITY_DEFERRED" for x in c), 58)
        self.assertEqual(
            {x["code"] for x in c},
            {code for codes in s["investigation_basket_codes"].values() for code in codes})
        self.assertTrue(s["summaries"]["basket_count_is_not_verified_theme_count"])
        self.assertFalse(s["summaries"]["exhaustive_deep_research_of_all_78_completed"])

    def test_original_handoff_identity_works_without_schema_change(self):
        s = self.shadow
        self.assertEqual(self.index["trade_date"], "2026-10-09")
        signals = []
        registry_rows = []
        for x in s["priority_shadows"]:
            codes=x["industry_codes"]
            names=[self.index["industries"][code]["industry_name"] for code in codes]
            row={
                "rank": x["rank"], "trend_name": x["trend_name"],
                "trend_state": x["trend_state"], "market_state": x["market_state"],
                "industry_codes": codes, "industry_names": names,
                "mapping_status": "resolved"
            }
            signals.append(row)
            registry_rows.append({
                "trend_name": x["trend_name"], "trend_state": x["trend_state"],
                "market_state": x["market_state"],
                "priority_rank": x["rank"],
                "in_new_position_priority": True,
                "industry_codes": codes, "industry_names": names
            })
        handoff={"schema_version":1,"result_kind":"a_share_trend_handoff",
                 "trade_date":"2026-10-09","signals":signals}
        registry={"result_kind":"a_share_trend_registry","status":"COMPLETE",
                  "trade_date":"2026-10-09","trends":registry_rows}
        result=check_theme_routes(handoff, self.index, registry)
        self.assertEqual(result["theme_count"], 3)
        self.assertEqual(result["unique_industry_count"], 7)
        self.assertTrue(result["identity_only"])
        self.assertEqual(len(signals), 3)
        self.assertNotIn("煤炭", [row["trend_name"] for row in signals])

    def test_no_unvalidated_observation_leaks_into_handoff(self):
        ranked={c for x in self.shadow["priority_shadows"] for c in x["industry_codes"]}
        obs={c for x in self.shadow["other_theme_decisions"]
             for c in (x["observe"]+x["codes_core"])}
        self.assertFalse(ranked & obs)
        self.assertEqual(self.shadow["priority_reserve"]["trend_name"], "煤炭")


if __name__ == "__main__":
    unittest.main()
