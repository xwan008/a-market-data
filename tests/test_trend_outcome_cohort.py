import importlib.util
import pathlib
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "build_trend_outcome_cohort.py"
spec = importlib.util.spec_from_file_location("cohort", SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
SHA = "a" * 40


class TrendCohortTests(unittest.TestCase):
    def test_right_censored_cohort_does_not_invent_future_returns(self):
        j = {"trade_date": "2026-10-13", "status": "COMPLETE",
             "trends": [{"trend_name": "样本", "first_seen_trade_date": "2026-10-01",
                         "trend_state": "T2", "market_state": "观察",
                         "lifecycle_status": "有效", "industry_codes": ["S000101"]}]}
        out = m.build(j, SHA, SHA, SHA)
        self.assertEqual(out["cohort_size"], 1)
        self.assertEqual(out["themes"][0]["prospective_baseline_date"], "2026-10-13")
        self.assertEqual(out["themes"][0]["historical_first_seen_trade_date"], "2026-10-01")
        self.assertIsNone(out["themes"][0]["returns"])
        self.assertFalse(out["source_dates_verified"])
        self.assertTrue(out["source_date_verification_required_before_returns"])

    def test_reject_fabricated_sha(self):
        with self.assertRaises(ValueError):
            m.build({"status": "COMPLETE", "trade_date": "2026-10-13",
                     "trends": []}, "unknown", SHA, SHA)

    def test_reject_duplicate_theme(self):
        with self.assertRaises(ValueError):
            m.build({"status": "COMPLETE", "trade_date": "2026-10-13",
                     "trends": [{"trend_name": "样本"}, {"trend_name": "样本"}]},
                    SHA, SHA, SHA)


if __name__ == "__main__":
    unittest.main()
