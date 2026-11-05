"""Contract tests for the V2 relative-entry SHADOW, not trade admission."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "experiments/trend_buy_v2_relative_entry_shadow.py"
spec = importlib.util.spec_from_file_location("v2_relative_entry_shadow", path)
shadow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shadow)
DAY = "2026-11-05"


def stock(code, p, ma20, rs, v1, v5, close, ret3, ret5, up5,
          phase="INITIATING", status="WAIT", weak=False, resist=None):
    return {
        "code": code, "company_name": code, "data_date": DAY,
        "status": status, "current_price": p, "trend_phase": phase,
        "technical_context": {
            "ma20": ma20, "distance_to_ma20_pct": (p / ma20 - 1) * 100,
            "relative_strength_20d_vs_market_pct": rs,
            "volume_ratio_1d_vs_20d": v1, "volume_ratio_5d_vs_20d": v5,
            "close_location_pct": close,
            "attention_resistance": (
                {"status": "VERIFIED", "price": resist,
                 "date": "2026-08-01", "history_points": 180,
                 "source": "asof_180bar_confirmed_pivot"} if resist else None),
        },
        "phase_evidence": {
            "return_3d_pct": ret3, "return_5d_pct": ret5,
            "positive_days_5d": up5, "fresh_break": True,
            "weak_close_high_volume": weak,
        },
        "entry_zone": None, "invalidation_price": None,
    }


class V2RelativeEntryTests(unittest.TestCase):
    def test_overextended_leader_can_outrank_low_deviation_weak_stock(self):
        spring = stock("601021", 45.40, 39.5635, 20.3, 3.208, 2.076, 93.59,
                       9.95, 17.43, 5, resist=46.1154)
        hainan = stock("600221", 1.23, 1.1905, 6.61, 1.486, 1.535, 0,
                       5.13, 6.96, 4, phase="REPAIRING", weak=True, resist=1.26)
        formal = {
            "trade_date": DAY, "ready": [], "wait": [spring, hainan],
            "top5_by_theme": [{
                "trend_name": "航空运输/机场",
                "items": [{"code": "600221"}, {"code": "601021"}],
            }],
        }
        result = shadow.rerank_formal(formal)
        entries = result["groups"][0]["items"]
        self.assertEqual([x["code"] for x in entries], ["601021", "600221"])
        self.assertEqual([x["status"] for x in entries], ["WAIT", "WAIT"])
        self.assertTrue(all(x["risk_reward_R"] is None for x in entries))
        self.assertTrue(all(not x["tradeable_under_formal_rules"] for x in entries))
        self.assertTrue(result["candidate_pre_screen_not_recomputed"])

    def test_rank_is_not_a_trade_gate_and_not_ready_first(self):
        strong = stock("600001", 10, 9.6, 17, 2.7, 2.0, 95, 5, 9, 5)
        weak_ready = stock("600002", 10, 9.7, -5, 1.05, 1.0, 20, 1, 1, 3,
                           status="READY", weak=True)
        a = shadow.score_company(strong, DAY)
        b = shadow.score_company(weak_ready, DAY)
        self.assertGreater(a["relative_entry_score"], b["relative_entry_score"])
        self.assertFalse(a["tradeable_under_formal_rules"])
        self.assertTrue(b["tradeable_under_formal_rules"])

    def test_dual_channel_balances_three_leaders_and_two_entries(self):
        rows = [
            {"code": str(i).zfill(6), "leader_score": 1 - i * .1,
             "entry_score": i * .1} for i in range(8)
        ]
        rows[5]["entry_score"] = .55
        # Entry leaders 7/6 can complement 0/1/2, without duplicates.
        chosen = shadow.dual_channel_select(rows, tie=0)
        self.assertEqual([x["code"] for x in chosen[:3]],
                         ["000000", "000001", "000002"])
        self.assertEqual([x["selection_channel"] for x in chosen[:3]],
                         ["TREND_LEADER"] * 3)
        self.assertEqual(len({x["code"] for x in chosen}), len(chosen))
        self.assertLessEqual(len(chosen), 6)

    def test_near_tie_sixth_only_if_close(self):
        rows = [
            {"code": str(i).zfill(6), "leader_score": 1 - i * .1,
             "entry_score": .90 - i * .01} for i in range(6)
        ]
        a = shadow.dual_channel_select(rows, tie=.03)
        b = shadow.dual_channel_select(rows, tie=0)
        self.assertEqual(len(a), 6)
        self.assertEqual(len(b), 5)
        self.assertEqual(a[5]["selection_channel"], "NEAR_TIE_SIXTH")

    def test_future_pivot_does_not_supply_space(self):
        r = stock("600001", 10, 9, 5, 2, 1.5, 90, 7, 8, 5, resist=12)
        r["technical_context"]["attention_resistance"]["date"] = "2026-11-06"
        x = shadow.score_company(r, DAY)
        self.assertIsNone(x["nearest_verified_resistance"])
        self.assertEqual(x["space_basis"], "RESISTANCE_UNVERIFIED_NEUTRAL_NO_R")
        self.assertIsNone(x["risk_reward_R"])

    def test_stale_structure_is_rejected(self):
        r = stock("600001", 10, 9, 5, 2, 1.5, 90, 7, 8, 5)
        r["data_date"] = "2026-11-04"
        with self.assertRaisesRegex(ValueError, "mismatched_technical"):
            shadow.score_company(r, DAY)

    def test_no_missing_stop_fabricated_from_old_support(self):
        r = stock("600001", 10, 9, 5, 2, 1.5, 90, 7, 8, 5, resist=11)
        r["technical_context"]["support_invalidation"] = 7
        x = shadow.score_company(r, DAY)
        self.assertIsNone(x["risk_reward_R"])
        self.assertIn("NO_R", x["space_basis"])


    def test_frozen_pre_screen_uses_unpenalized_leader_and_separate_entry(self):
        records = []
        for i in range(7):
            code = str(i).zfill(6)
            records.append({
                "code": code, "industry_code": "S421001", "fundamental_score": .5,
                "excluded_reason": None,
                "opportunity": {
                    "price_structure_score": 1 - i * .12,
                    "volume_quality_score": 1 - i * .11,
                    "relative_strength_score": 1 - i * .1,
                    "opportunity_score": i * .12,
                }
            })
        screened = {
            "trade_date": DAY,
            "screen_audit": {
                "lightweight_scanned": records,
                "pre_screen_selected": [
                    {"industry_code": "S421001", "code": str(i).zfill(6)}
                    for i in range(2, 7)],
            },
        }
        out = shadow.shadow_prescreen(screened, DAY)
        result = out["industry_comparison"][0]
        picks = result["shadow_candidates"]
        self.assertEqual([x["code"] for x in picks[:3]], ["000000", "000001", "000002"])
        self.assertEqual([x["selection_channel"] for x in picks[:3]],
                         ["TREND_LEADER"] * 3)
        self.assertEqual(len({x["code"] for x in picks}), len(picks))
        self.assertIn("000000", result["new_review_required"])
        self.assertEqual(out["fundamental_scores"]["000001"], .5)

    def test_frozen_prescreen_rejects_wrong_date(self):
        with self.assertRaisesRegex(ValueError, "trade_date_mismatch"):
            shadow.shadow_prescreen({"trade_date": "2026-11-06",
                                     "screen_audit": {"lightweight_scanned": []}},
                                    DAY)


    def test_empty_published_theme_does_not_fill_five(self):
        formal = {"trade_date": DAY, "ready": [], "wait": [],
                  "top5_by_theme": [{"trend_name": "空行业", "items": []}]}
        x = shadow.rerank_formal(formal)
        self.assertEqual(x["groups"][0]["items"], [])


if __name__ == "__main__":
    unittest.main()
