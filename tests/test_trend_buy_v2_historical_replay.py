"""Point-in-time replay safeguards. No actual trade-order claims."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
spec = importlib.util.spec_from_file_location(
    "trend_buy_v2_historical_replay",
    ROOT / "experiments/trend_buy_v2_historical_replay.py")
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


class ReplayTests(unittest.TestCase):
    def test_earliest_publication_wins_and_late_backfill_excluded(self):
        # git log is newest-first, earliest in reversed view should prevail.
        raw = ("late\t2026-11-08T00:00:00+00:00\n"
               "second\t2026-11-05T12:00:00+00:00\n"
               "first\t2026-11-05T11:03:00+00:00\n")
        snapshots = {
            "first": {"trade_date": "2026-11-05", "status": "COMPLETE",
                      "production_eligible": True, "ready": [], "wait": [],
                      "top5_by_theme": []},
            "second": {"trade_date": "2026-11-05", "status": "COMPLETE",
                       "production_eligible": True, "ready": [], "wait": [],
                       "top5_by_theme": []},
            "late": {"trade_date": "2026-11-05", "status": "COMPLETE",
                     "production_eligible": True, "ready": [], "wait": [],
                     "top5_by_theme": []}
        }
        with patch.object(replay, "git", return_value=raw), patch.object(
                replay, "historical_file",
                side_effect=lambda sha, *_: snapshots[sha]):
            got, rejected = replay.published_snapshots(min_date="2026-11-05",
                                                       max_date="2026-11-05")
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["commit"], "first")
        self.assertTrue(any(x["reason"] == "publication_outside_36_hours"
                            for x in rejected))

    def test_next_open_not_asof_close_and_mae_uses_future_low(self):
        rows = {"2026-11-05": {"close": 10, "low": 9.6, "high": 10.2},
                "2026-11-06": {"open": 11, "close": 12,
                               "low": 10.5, "high": 12.5},
                "2026-11-09": {"open": 12, "close": 13,
                               "low": 11.5, "high": 13.2},
                "2026-11-10": {"open": 13, "close": 12.1,
                               "low": 12, "high": 13.5}}
        row = {"date": "2026-11-05", "code": "600001", "current_price": 10}
        got, error = replay.outcome(row, "2026-11-06", "2026-11-10",
                                    sorted(rows), {"600001": (rows, "qfq")})
        self.assertIsNone(error)
        self.assertAlmostEqual(got["return_pct"], 10)
        self.assertAlmostEqual(got["mae_pct"], -100 * .5 / 11)
        self.assertAlmostEqual(got["mfe_pct"], 100 * 2.5 / 11)

    def test_missing_session_excluded_not_interpolated(self):
        rows = {"2026-11-05": {"close": 10},
                "2026-11-06": {"open": 11, "close": 11.5},
                "2026-11-10": {"close": 12}}
        out, error = replay.outcome(
            {"date": "2026-11-05", "code": "600001", "current_price": 10},
            "2026-11-06", "2026-11-10",
            ["2026-11-05", "2026-11-06", "2026-11-09", "2026-11-10"],
            {"600001": (rows, "qfq")})
        self.assertIsNone(out)
        self.assertEqual(error, "MISSING_INTERMEDIATE_SESSION")

    def test_adjusted_basis_mismatch_rejected(self):
        rows = {"2026-11-05": {"close": 8},
                "2026-11-06": {"open": 9},
                "2026-11-10": {"close": 10}}
        out, error = replay.outcome(
            {"date": "2026-11-05", "code": "600001", "current_price": 10},
            "2026-11-06", "2026-11-10",
            sorted(rows), {"600001": (rows, "qfq")})
        self.assertIsNone(out)
        self.assertEqual(error, "ASOF_CLOSE_VS_HISTORY_BASIS_MISMATCH")

    def test_summary_does_not_claim_significance(self):
        data = [{"horizon": 3, "asof": "2026-10-09", "theme": "航空",
                 "old_top1_return_pct": 1, "v2_top1_return_pct": 2,
                 "old_top3_return_pct": 1.1, "v2_top3_return_pct": 2.2,
                 "old_top1_mae_pct": -3, "v2_top1_mae_pct": -4}]
        got = replay.summarize(data)
        self.assertEqual(got[0]["cohorts"], 1)
        self.assertEqual(got[0]["top1_mean_difference_pp"], 1)
        self.assertEqual(got[1]["cohorts"], 0)

if __name__ == "__main__":
    unittest.main()
