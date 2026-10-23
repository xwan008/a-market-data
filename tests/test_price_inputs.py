"""Regression tests: short-horizon returns, volume units, and stale shard rejection."""
import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_history import build_stock_summary
from price_inputs import load_momentum_shards


class ShardedMomentumTests(unittest.TestCase):
    def test_history_window_has_real_three_and_five_intervals(self):
        day = date(2026, 10, 9)
        rows = []
        for i in range(25):
            d = (day - timedelta(days=24-i)).isoformat()
            rows.append({"date": d, "close": 100+i, "open": 99+i,
                         "high": 101+i, "low": 98+i,
                         "volume": 10, "basis": "qfq", "source": "tencent"})
        stock = build_stock_summary({"history": rows, "last_full_refresh": "2026-10-09"},
                                    expected_trade_date=day.isoformat())
        m = stock["momentum_evidence"]
        self.assertEqual(m["data_date"], "2026-10-09")
        self.assertAlmostEqual(m["return_3d_pct"], round((124/121-1)*100, 2))
        self.assertAlmostEqual(m["return_5d_pct"], round((124/119-1)*100, 2))
        self.assertEqual(m["volume_ratio_1d"], 1.0)
        self.assertNotEqual(m["return_5d_pct"], stock["close_change_5d_pct"])

    def test_reject_stale_or_missing_momentum(self):
        day = "2026-10-09"
        stock = {"trend": {"last_date": day, "history_confidence": "high",
                           "momentum_evidence": {"data_date": day,
                               "return_3d_pct": 1.2,
                               "return_5d_pct": 2.4,
                               "return_20d_pct": 3.3,
                               "volume_ratio_1d": 1.1}}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "00001.json"
            path.write_text(json.dumps({"trade_date": day,
                                        "stocks": {"000001": stock}}))
            got = load_momentum_shards(day, tmp)
            self.assertEqual(got["companies"]["000001"]["phase_evidence"]["return_3d_pct"], 1.2)
            stock["trend"]["momentum_evidence"]["data_date"] = "2026-10-08"
            path.write_text(json.dumps({"trade_date": day, "stocks": {"000001": stock}}))
            with self.assertRaisesRegex(ValueError, "coverage_below"):
                load_momentum_shards(day, tmp)
            with self.assertRaisesRegex(ValueError, "shard_date_mismatch"):
                load_momentum_shards("2026-10-10", tmp)



class AttentionResistanceTests(unittest.TestCase):
    def test_historical_overhead_uses_confirmed_past_pivot_only(self):
        from price_inputs import SelectedStockStructures
        asof = date(2026, 10, 19)
        rows = [{"date": (asof - timedelta(days=124-i)).isoformat(),
                 "high": 10.1} for i in range(125)]
        rows[50]["high"] = 11.2
        rows[-1]["high"] = 11.8  # not a confirmed pivot: no future right bars
        got = SelectedStockStructures._attention_resistance(
            rows, 10.5, asof.isoformat())
        self.assertEqual(got["status"], "VERIFIED")
        self.assertAlmostEqual(got["price"], 11.2)
        self.assertEqual(got["date"], rows[50]["date"])
        self.assertEqual(
            SelectedStockStructures._attention_resistance(
                rows[:119], 10.5, rows[118]["date"])["status"], "UNVERIFIED")

    def test_missing_historical_pivot_is_unknown_not_infinite_upside(self):
        from price_inputs import SelectedStockStructures
        asof = "2026-10-19"
        rows = [{"date": "2026-10-18", "high": 10.1} for _ in range(124)]
        rows.append({"date": asof, "high": 10.1})
        got = SelectedStockStructures._attention_resistance(rows, 10.5, asof)
        self.assertEqual(got["status"], "UNVERIFIED")
        self.assertIsNone(got["price"])


class SetupSpecificStopInputTests(unittest.TestCase):
    def test_price_metrics_preserve_same_day_low_and_breakout_anchor(self):
        from build_full_market_price_structure import base_metrics
        day=date(2026,10,23)
        rows=[]
        for i in range(65):
            rows.append({"date":(day-timedelta(days=64-i)).isoformat(),
                         "open":10.0,"high":10.2,"low":9.8,
                         "close":10.0,"volume":100})
        rows[-1]["low"]=9.7
        got=base_metrics("600001","synthetic",rows,
                         {"price":10.0},day.isoformat(),min_points=65)
        self.assertEqual(got["current_day_low"],9.7)
        self.assertEqual(got["data_date"],day.isoformat())
        self.assertNotIn("confirmed_swing_supports",got)
        self.assertGreater(got["prior_60d_high"],0)


if __name__ == "__main__":
    unittest.main()
