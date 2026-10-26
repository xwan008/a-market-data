"""Regression tests for the minimal theme-identification / candidate snapshot layer."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import route_hotspot_themes as router


DAY = "2026-10-26"


def fixture():
    # Two original SW constituents and five unrelated-industry concept constituents.
    ownership = {
        "000001": "S640701", "000002": "S640702",
        "000003": "S650101", "000004": "S650102",
        "000005": "S650103", "000006": "S650104",
        "000007": "S650105",
    }
    index = {"companies": {k: {"mapping_status": "mapped", "industry_code": v}
                           for k, v in ownership.items()}}
    latest = {"trade_date": DAY, "market_status": "closed", "stocks": {
        code: {"name": "测试" + code, "change_pct": 2.0,
               "confidence": "high"} for code in ownership}}
    structure = {"reference_trade_date": DAY, "companies": {
        code: {"mock_score": .8 if code in {"000003", "000004"} else .6}
        for code in ownership}}
    handoff = {"result_kind": "a_share_trend_handoff", "trade_date": DAY,
               "signals": [{"rank": 1, "trend_name": "工业自动化/机器人",
                            "industry_codes": ["S640701", "S640702"],
                            "mapping_status": "resolved",
                            "trend_state": "T1", "market_state": "候选趋势"}]}
    catalog = {"schema_version": 1, "source": "EASTMONEY_AKSHARE",
               "as_of_trade_date": DAY,
               "concepts": [{"concept_id": "BKTEST", "name": "人形机器人",
                             "member_codes": list(ownership)}]}
    return handoff, index, latest, structure, catalog


def dummy_technical(row, date):
    assert date == DAY
    return ({"opportunity_score": row["mock_score"]}, None)


class ThemeRouterTests(unittest.TestCase):
    def test_robot_cross_industry_becomes_theme_and_ranks_capped_stocks(self):
        h, i, q, s, c = fixture()
        with patch("build_trend_buy_manual_research.compact_opportunity",
                   side_effect=dummy_technical):
            data = router.build(h, i, q, s, c, cap=3)
        group = data["routes"][0]
        self.assertEqual(group["hotspot_type"], "THEME")
        self.assertEqual(group["mapping_code"], "BKTEST")
        self.assertEqual(group["concept_member_count"], 7)
        self.assertEqual(group["outside_route_rising_count"], 5)
        self.assertEqual(len(group["candidate_stocks"]), 3)
        self.assertEqual(group["candidate_stocks"][0]["stock_code"], "000003")
        self.assertEqual(group["candidate_stocks"][1]["stock_code"], "000004")
        self.assertTrue(all(x["stock_code"] in c["concepts"][0]["member_codes"]
                            for x in group["candidate_stocks"]))

    def test_single_industry_trend_retains_sw_route(self):
        h, i, q, s, c = fixture()
        h["signals"][0]["trend_name"] = "煤炭"
        result = router.build(h, i, q, s, c)["routes"][0]
        self.assertEqual(result["hotspot_type"], "INDUSTRY")
        self.assertEqual(result["candidate_stocks"], [])
        self.assertEqual(result["original_industry_codes"],
                         ["S640701", "S640702"])

    def test_no_external_breadth_cannot_overwrite_industry(self):
        h, i, q, s, c = fixture()
        c["concepts"][0]["member_codes"] = ["000001", "000002",
                                            "000003", "000004", "000005"]
        for code in ("000003", "000004", "000005"):
            q["stocks"][code]["change_pct"] = -2
        result = router.build(h, i, q, s, c)["routes"][0]
        self.assertEqual(result["hotspot_type"], "INDUSTRY")

    def test_named_concept_with_missing_full_universe_is_unknown_not_industry(self):
        h, i, q, s, c = fixture()
        for stock in ("000003", "000004", "000005", "000006", "000007"):
            i["companies"].pop(stock)
            q["stocks"].pop(stock)
        result = router.build(h, i, q, s, c)["routes"][0]
        self.assertEqual(result["hotspot_type"], "DATA_INSUFFICIENT")
        self.assertEqual(result["classification_reason"], "CONCEPT_COVERAGE_UNVERIFIED")
        self.assertEqual(result["candidate_stocks"], [])
        self.assertLess(result["insufficient_concepts"][0]["quote_coverage"], .8)
        self.assertEqual(result["insufficient_concepts"][0]["member_count"], 7)

    def test_same_day_quote_supplement_does_not_change_industry_membership(self):
        h, i, q, s, c = fixture()
        # All cross-industry records are outside the frozen SW research index.
        for stock in ("000003", "000004", "000005", "000006", "000007"):
            i["companies"].pop(stock)
            q["stocks"].pop(stock)
        supplement = {
            "result_kind": "concept_quote_supplement",
            "trade_date": DAY, "market_status": "closed",
            "stocks": {code: {"confidence":"medium","change_pct":2}
                       for code in ("000003", "000004", "000005", "000006", "000007")}}
        result = router.build(h, i, q, s, c, supplement=supplement)["routes"][0]
        self.assertEqual(result["hotspot_type"], "INDUSTRY")
        # Full quote coverage is restored, but sector transmission is still unverified
        # for the unmapped stock codes; do not invent SW membership.
        self.assertFalse(result["insufficient_concepts"])

    def test_wrong_day_supplement_blocks(self):
        h, i, q, s, c = fixture()
        with self.assertRaisesRegex(ValueError, "SUPPLEMENT_ASOF_INVALID"):
            router.build(h, i, q, s, c, supplement={
                "result_kind": "concept_quote_supplement",
                "trade_date": "2026-10-27", "market_status": "closed", "stocks": {}})

    def test_membership_asof_date_is_hard_gate(self):
        h, i, q, s, c = fixture()
        c["as_of_trade_date"] = "2026-10-27"
        with self.assertRaisesRegex(ValueError, "DATE_OR_SOURCE"):
            router.build(h, i, q, s, c)

    def test_closed_session_is_required(self):
        h, i, q, s, c = fixture()
        q["market_status"] = "open"
        with self.assertRaisesRegex(ValueError, "SAME_COMPLETED_SESSION"):
            router.build(h, i, q, s, c)

    def test_invalid_or_missing_board_data_must_not_be_mislabeled(self):
        h, i, q, s, c = fixture()
        c["concepts"][0]["member_codes"] = ["junk"]
        with self.assertRaisesRegex(ValueError, "INVALID_STOCK"):
            router.build(h, i, q, s, c)

    def test_candidate_scoring_is_not_a_buy_signal(self):
        h, i, q, s, c = fixture()
        s["companies"]["000004"] = {"mock_score": .9}
        with patch("build_trend_buy_manual_research.compact_opportunity",
                   side_effect=dummy_technical):
            result = router.build(h, i, q, s, c)["routes"][0]
        self.assertNotIn("ready", result)
        self.assertNotIn("entry_zone", result["candidate_stocks"][0])


if __name__ == "__main__":
    unittest.main()
