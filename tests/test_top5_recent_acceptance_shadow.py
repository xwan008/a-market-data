"""Isolation checks for recent-entry shadow only. No official output changes."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
mod_path = ROOT / "experiments/top5_recent_acceptance_shadow.py"
spec = importlib.util.spec_from_file_location("recent_shadow", mod_path)
shadow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shadow)
ASOF = "2026-10-23"
CODES = ("603416", "002979", "603275", "603583", "603025")


def fake(low, close, resistance=12):
    bars = []
    for i in range(12):
        bars.append({
            "date": "2026-10-%02d" % (10 + i),
            "open": 10.5, "low": 10.0, "high": 11.5,
            "close": 10.5, "volume": 1000
        })
    bars[-4]["low"] = 10
    bars[-3]["low"] = 10.2
    bars[-2]["low"] = 10.15
    bars[-1] = {"date": ASOF, "open": 10.2, "high": max(close, 11.3),
                "low": low, "close": close, "volume": 2000}
    row = {
        "code": "000001", "company_name": "FAKE", "current_price": close,
        "status": "WAIT",
        "technical_context": {
            "volume_ratio_1d_vs_20d": 2.0,
            "attention_resistance": {
                "status": "VERIFIED", "price": resistance,
                "date": "2026-10-09", "source": "asof_180bar_confirmed_pivot",
                "history_points": 180,
            }
        }
    }
    return bars, row


class RecentAcceptanceTests(unittest.TestCase):
    def test_shadow_hold_uses_recent_support_below_price(self):
        bars, row = fake(10.01, 11.2)
        out = shadow.evaluate_recent_acceptance(bars, row, ASOF)
        self.assertEqual(out["observed_pattern"], "LOCAL_SUPPORT_HOLD")
        self.assertEqual(out["observation_stop"], 9.95)
        self.assertFalse(out["first_acceptance_proven"])
        self.assertEqual(out["stage"], "SHADOW_OBSERVATION_NOT_EXECUTABLE")

    def test_sweep_uses_new_low_not_pierced_old_support(self):
        bars, row = fake(9.8, 11.2)
        out = shadow.evaluate_recent_acceptance(bars, row, ASOF)
        self.assertEqual(out["observed_pattern"], "SAME_DAY_SWEEP_RECLAIM")
        self.assertAlmostEqual(out["observation_stop"], 9.751)
        self.assertLess(out["observation_stop"], 9.95)

    def test_failed_reclaim_does_not_invent_a_stop_or_r(self):
        bars, row = fake(9.8, 9.9)
        out = shadow.evaluate_recent_acceptance(bars, row, ASOF)
        self.assertEqual(out["observed_pattern"], "UNCONFIRMED_LOCAL_ACCEPTANCE")
        self.assertIsNone(out["observation_stop"])
        self.assertIsNone(out["conditional_close_R"])
        self.assertIn("no_1to3d_acceptance_pattern", out["study_blocks"])

    def test_future_history_and_pivots_never_leak(self):
        bars, row = fake(9.8, 11.2)
        original = shadow.evaluate_recent_acceptance(bars, row, ASOF)
        bars.append({"date": "2026-10-26", "low": 4, "high": 20,
                     "close": 20, "volume": 100000, "open": 10})
        self.assertEqual(original, shadow.evaluate_recent_acceptance(bars, row, ASOF))
        row["technical_context"]["attention_resistance"]["date"] = "2026-10-26"
        no_future = shadow.evaluate_recent_acceptance(bars, row, ASOF)
        self.assertIsNone(no_future["conditional_close_R"])
        self.assertIn("resistance_or_stop_missing", no_future["study_blocks"])

    def test_incomplete_or_mismatched_frozen_bar_fails_closed(self):
        bars, row = fake(9.8, 11.2)
        with self.assertRaisesRegex(ValueError, "frozen_price_mismatch"):
            shadow.evaluate_recent_acceptance(bars, {**row, "current_price": 12}, ASOF)
        with self.assertRaisesRegex(ValueError, "asof_bar_missing"):
            shadow.evaluate_recent_acceptance(bars, row, "2026-10-22")

    def test_2026_oct23_real_five_all_lookback3_but_not_trade_ready(self):
        result = shadow.run(ROOT, ASOF, CODES, lookback=3)
        self.assertEqual(result["mode"], "SHADOW_ONLY_NO_FORMAL_TOP5_CHANGE")
        self.assertEqual(result["candidate_count"], 5)
        self.assertEqual(result["tradeable_candidate_count"], 0)
        self.assertEqual(result["passing_observation_count"], 0)
        self.assertTrue(result["no_forced_ranking"])
        items = {x["code"]: x for x in result["items"]}
        self.assertEqual(set(items), set(CODES))
        self.assertEqual(items["603583"]["observed_pattern"], "LOCAL_SUPPORT_HOLD")
        for c in ("603416", "002979", "603275", "603025"):
            self.assertEqual(items[c]["observed_pattern"], "SAME_DAY_SWEEP_RECLAIM")
        for x in result["items"]:
            self.assertFalse(x["first_acceptance_proven"])
            self.assertGreater(x["close_to_stop_risk_pct"], 6)
            self.assertLess(x["conditional_close_R"], 1.5)
            self.assertIn("asof_close_risk_above_6pct", x["study_blocks"])
            self.assertIn("first_resistance_below_1_5R", x["study_blocks"])
        self.assertAlmostEqual(items["603416"]["prior_support_low"], 43.15)
        self.assertAlmostEqual(items["603275"]["prior_support_low"], 33.93)
        self.assertAlmostEqual(items["603583"]["observation_anchor"], 26.8)

    def test_lookback_1_vs_3_change_is_explicit(self):
        three = shadow.run(ROOT, ASOF, CODES, lookback=3)
        one = shadow.run(ROOT, ASOF, CODES, lookback=1)
        x3 = {r["code"]: r for r in three["items"]}
        x1 = {r["code"]: r for r in one["items"]}
        self.assertNotEqual(x3["603583"]["prior_support_low"],
                            x1["603583"]["prior_support_low"])
        self.assertNotEqual(x3["603583"]["observed_pattern"],
                            x1["603583"]["observed_pattern"])

    def test_mainline_snapshot_is_not_updated(self):
        before = (ROOT / "research/trend_buy_formal_result.json").read_bytes()
        shadow.run(ROOT, ASOF, CODES)
        after = (ROOT / "research/trend_buy_formal_result.json").read_bytes()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
