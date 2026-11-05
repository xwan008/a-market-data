import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from shadow_backtest_theme_review import (
    group_match, captured, members, summarize_outcomes, compact_lead,
)


class ThemeShadowBacktestTests(unittest.TestCase):
    def lead(self, code, rank=1):
        return {"source_id": "SW_L2_TAXONOMY:" + code,
                "industry_codes": ["S630501", "S630502"], "rank": rank,
                "name": "PV", "review_priority_score": 70,
                "selection_track": "MULTI_L3_PERSISTENCE",
                "persistent_industry_count": 2,
                "industry_evidence": [
                    {"industry_code": "S630501"}, {"industry_code": "S630502"}]}

    def test_captured_checks_identity_and_components_not_label(self):
        pv = self.lead("pv")
        other = self.lead("other")
        self.assertTrue(group_match(pv, other))
        self.assertTrue(captured(pv, [other]))
        unrelated = {**other, "industry_codes": ["S270102", "S270103"]}
        self.assertFalse(group_match(pv, unrelated))

    def test_component_codes_never_promoted_to_trade_authority(self):
        row = compact_lead(self.lead("pv"))
        self.assertEqual(row["industry_codes"], [
            r["industry_code"] for r in row["evidence"]])
        self.assertNotIn("market_state", row)
        self.assertNotIn("in_new_position_priority", row)

    def test_member_mapping_accepts_only_asof_mapped_sw3(self):
        index = {"companies": {
            "1": {"mapping_status": "mapped", "industry_code": "S630501"},
            "2": {"mapping_status": "mapped", "industry_code": "S630502"},
            "3": {"mapping_status": "unverified", "industry_code": "S630502"},
            "4": {"mapping_status": "mapped", "industry_code": "S270103"}}}
        self.assertEqual(members(index, ["S630502"]), {"000002"})

    def test_even_observation_count_uses_statistical_median(self):
        rows = [
            {"strategy": "old3", "outcomes": {
                "1": {"status": "OBSERVED", "return_pct": -2, "relative_pct": -1,
                      "weak_continuation_proxy": True},
                "2": {"status": "NOT_YET_OBSERVABLE"}}},
            {"strategy": "old3", "outcomes": {
                "1": {"status": "OBSERVED", "return_pct": 3, "relative_pct": 2,
                      "weak_continuation_proxy": False},
                "2": {"status": "NOT_YET_OBSERVABLE"}}}]
        self.assertEqual(summarize_outcomes(rows, "old3")["horizons"]["1"]
                         ["median_forward_return_pct"], .5)

    def test_unobservable_excluded_from_weak_rate(self):
        rows = [
            {"strategy": "new10", "outcomes": {
                "1": {"status": "OBSERVED", "return_pct": -2, "relative_pct": -1,
                      "weak_continuation_proxy": True},
                "2": {"status": "NOT_YET_OBSERVABLE"}}},
            {"strategy": "new10", "outcomes": {
                "1": {"status": "OBSERVED", "return_pct": 3, "relative_pct": 1,
                      "weak_continuation_proxy": False},
                "2": {"status": "NOT_YET_OBSERVABLE"}}}]
        score = summarize_outcomes(rows, "new10")
        self.assertEqual(score["horizons"]["1"]["weak_continuation_rate"], .5)
        self.assertEqual(score["horizons"]["2"]["observed"], 0)
        self.assertIsNone(score["horizons"]["2"]["weak_continuation_rate"])


if __name__ == "__main__":
    unittest.main()
