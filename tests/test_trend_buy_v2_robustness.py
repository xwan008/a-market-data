"""Independent regressions for point-in-time replay robustness diagnostics."""
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
spec = importlib.util.spec_from_file_location(
    "v2robust", ROOT / "experiments/trend_buy_v2_robustness.py")
robust = importlib.util.module_from_spec(spec)
spec.loader.exec_module(robust)

def sample(day, theme, old, new, delta, horizon=5, end="2026-10-31",
           regime="REPAIR_BELOW_MA60_FALLING_MA20"):
    return {"asof": day, "theme": theme, "horizon": horizon,
            "old_top1": old, "v2_top1": new,
            "v2_top1_regime": regime,
            "old_top1_return_pct": 1.0,
            "v2_top1_return_pct": 1.0 + delta,
            "future_first_session": "2026-10-20",
            "future_target_session": end}

def report(name, samples):
    return {"mode": "HISTORICAL_SHADOW_INDICATIVE_NOT_TRADING_BACKTEST",
            "ranking": name, "asof_dates": ["2026-10-16"],
            "samples": samples, "skipped": {}}


class RobustnessTests(unittest.TestCase):
    def test_repeat_stock_pair_not_counted_as_independent_event(self):
        rows = [
            sample("2026-10-16", "黄金", "A", "B", -4),
            sample("2026-10-20", "黄金", "A", "B", -5),
            sample("2026-10-21", "黄金", "A", "C", 2),
        ]
        result=robust.robust_summary(rows)
        self.assertEqual(result["cohorts"],3)
        self.assertEqual(result["unique_theme_old_new_tuple_cohorts"],2)
        self.assertEqual(result["nonoverlap_by_theme_cohorts"],1)
        self.assertEqual(result["distinct_dates"],3)
        self.assertAlmostEqual(result["equal_cohort_mean_diff_pp"],-2.3333,places=3)

    def test_day_clusters_do_not_overweight_dates_with_more_themes(self):
        a = sample("2026-10-16", "A", "a","b",10)
        b = sample("2026-10-16", "B", "a","b",10)
        c = sample("2026-10-20", "A", "a","c",-10)
        m=robust.robust_summary([a,b,c])
        self.assertAlmostEqual(m["equal_cohort_mean_diff_pp"],3.3333,places=3)
        self.assertEqual(m["equal_date_mean_diff_pp"],0)

    def test_changed_only_excludes_ties_due_unchanged_first_choice(self):
        rows=[
            sample("2026-10-16","A","a","a",0),
            sample("2026-10-20","A","a","b",-6),
        ]
        m=robust.robust_summary(rows)
        self.assertEqual(m["changed_top1_cohorts"],1)
        self.assertEqual(m["changed_top1_only_mean_diff_pp"],-6)
        self.assertEqual(m["changed_top1_wins_losses_ties"]["losses"],1)

    def test_conservative_sparse_signflip(self):
        self.assertIsNone(robust.exact_sign_flip_p([-1,-1,2]))
        self.assertEqual(robust.exact_sign_flip_p([1,1,1,1,1]), .0625)

    def test_reject_unpaired_and_duplicate_cohorts(self):
        a=sample("2026-10-16","A","a","b",-2)
        good=report("V2",[a])
        same=report("V21_STRUCTURAL",[a])
        result=robust.run({"V2":good,"V21_STRUCTURAL":same})
        self.assertTrue(result["comparability"]["identical_cohort_keys"])
        self.assertFalse(result["promotion_eligible"])
        with self.assertRaisesRegex(ValueError,"duplicate_date_theme_horizon"):
            robust.run({"V2":report("V2",[a,a]),"V21_STRUCTURAL":same})
        off=sample("2026-10-17","A","a","b",1)
        diff=robust.run({"V2":good,
                         "V21_STRUCTURAL":report("V21_STRUCTURAL",[off])})
        self.assertFalse(diff["comparability"]["identical_cohort_keys"])

    def test_outcome_date_must_be_strictly_after_asof(self):
        a=sample("2026-10-20","A","a","b",1)
        with self.assertRaisesRegex(ValueError,"invalid_outcome_dates"):
            robust.run({"V2":report("V2",[a]),
                        "V21_STRUCTURAL":report("V21_STRUCTURAL",[a])})


if __name__ == "__main__":
    unittest.main()
