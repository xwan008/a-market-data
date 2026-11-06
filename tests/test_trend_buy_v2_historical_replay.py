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

    def test_first_rankable_does_not_select_rankless_early_publication(self):
        # Oct 9 evening was originally complete but did not yet publish Top5.
        # Oct 10 17:00+08 is the first actually ranked Top5, before Oct 12 open.
        raw=("late\\t2026-10-11T08:00:00+00:00\\n"
             "ranked\\t2026-10-10T09:00:34+00:00\\n"
             "rankless\\t2026-10-10T05:38:48+00:00\\n").replace(chr(92)+"t",chr(9)).replace(chr(92)+"n",chr(10))
        prior={"trade_date":"2026-10-09","status":"COMPLETE",
               "production_eligible":True,"top5_by_theme":[]}
        later={**prior,"top5_by_theme":[{"trend_name":"固态电池",
            "items":[{"code":"603659"},{"code":"002812"}]}]}
        content={"rankless":prior,"ranked":later,"late":later}
        with patch.object(replay,"git",return_value=raw),patch.object(
            replay,"historical_file",side_effect=lambda sha,*_:content[sha]):
            early,_=replay.published_snapshots(
                min_date="2026-10-09",max_date="2026-10-09",
                policy="EARLIEST_COMPLETE")
            usable,rejected=replay.published_snapshots(
                min_date="2026-10-09",max_date="2026-10-09",
                policy="FIRST_RANKABLE")
        self.assertEqual(early[0]["commit"],"rankless")
        self.assertEqual(usable[0]["commit"],"ranked")
        self.assertTrue(any(x["reason"]=="rankless_complete_before_first_rankable"
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
        self.assertAlmostEqual(got["open_gap_pct"], 10)
        self.assertFalse(got["possible_price_limit_locked_open"])
        self.assertAlmostEqual(got["mae_pct"], -100 * .5 / 11)
        self.assertAlmostEqual(got["mfe_pct"], 100 * 2.5 / 11)

    def test_one_price_limit_open_is_only_an_unfillable_proxy(self):
        bars={"2026-11-05":{"close":10,"low":9.8,"high":10.2},
              "2026-11-06":{"open":11,"close":11,"low":11,"high":11},
              "2026-11-09":{"open":10.9,"close":10.5,"low":10.4,"high":11}}
        result, reason=replay.outcome(
            {"date":"2026-11-05","code":"600001","current_price":10},
            "2026-11-06","2026-11-09",sorted(bars),
            {"600001":(bars,"qfq")})
        self.assertIsNone(reason)
        self.assertTrue(result["possible_price_limit_locked_open"])
        self.assertAlmostEqual(result["open_gap_pct"],10)

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

    def test_publication_must_precede_next_open(self):
        self.assertTrue(replay.published_before_next_open(
            "2026-10-20T19:00:00+08:00", "2026-10-21"))
        self.assertFalse(replay.published_before_next_open(
            "2026-10-21T10:01:00+08:00", "2026-10-21"))
        self.assertTrue(replay.published_before_next_open(
            "2026-10-21T09:30:00+08:00", "2026-10-21"))

    def test_regime_uses_only_asof_completed_context(self):
        row={"current_price":10,"trend_phase":"REPAIRING",
             "technical_context":{"ma60":11,
                 "ma20_slope_5d_pct":-2}}
        self.assertEqual(replay.asof_regime(row),
            "REPAIR_BELOW_MA60_FALLING_MA20")
        self.assertEqual(replay.asof_regime({
             **row, "technical_context":{"ma60":9,
                 "ma20_slope_5d_pct":-2}}), "OTHER_VERIFIED_STRUCTURE")
        self.assertEqual(replay.asof_regime({
             **row, "technical_context":{"ma60":11}}),
             "UNKNOWN_STRUCTURE")

    def test_pairwise_rank_concordance_evaluates_all_stocks(self):
        moves={"A":{"return_pct":3},"B":{"return_pct":2},
               "C":{"return_pct":1}}
        self.assertAlmostEqual(
            replay.pairwise_order_accuracy(["A","B","C"],moves),1)
        self.assertAlmostEqual(
            replay.pairwise_order_accuracy(["C","B","A"],moves),0)
        ties={"A":{"return_pct":1},"B":{"return_pct":1}}
        self.assertEqual(replay.pairwise_order_accuracy(["A","B"],ties),.5)
        with self.assertRaisesRegex(ValueError,"unique_rank"):
            replay.pairwise_order_accuracy(["A","A"],moves)

    def test_summary_does_not_claim_significance(self):
        data = [{"horizon": 3, "asof": "2026-10-09", "theme": "航空",
                 "old_top1": "600001", "v2_top1": "600002",
                 "old_top1_return_pct": 1, "v2_top1_return_pct": 2,
                 "old_top3_return_pct": 1.1, "v2_top3_return_pct": 2.2,
                 "old_top1_mae_pct": -3, "v2_top1_mae_pct": -4,
                 "old_pairwise_accuracy": .5,
                 "v2_pairwise_accuracy": .7}]
        got = replay.summarize(data)
        self.assertEqual([x["horizon"] for x in got], [1,2,3,5,10])
        self.assertEqual(got[2]["cohorts"], 1)
        self.assertEqual(got[2]["top1_mean_difference_pp"], 1)
        self.assertEqual(got[0]["cohorts"], 0)
        self.assertEqual(got[1]["cohorts"], 0)

if __name__ == "__main__":
    unittest.main()
