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


class ConfirmedSwingStopEvidenceTests(unittest.TestCase):
    def test_later_broken_pivot_cannot_be_used_as_stop(self):
        from build_full_market_price_structure import base_metrics
        day = date(2026, 10, 23)
        rows = []
        for i in range(65):
            d = (day - timedelta(days=64-i)).isoformat()
            low = 9.8
            if i == 50: low = 9.5   # Was a pivot, later broken.
            if i == 59: low = 9.2   # 5 bars old: confirmed & unbroken.
            rows.append({"date": d, "open": 10.0, "high": 10.2,
                         "low": low, "close": 10.0, "volume": 100})
        got = base_metrics("600001", "synthetic", rows,
                           {"price": 10.0}, day.isoformat(), min_points=65)
        supports = got["confirmed_swing_supports"]
        self.assertEqual(len(supports), 1)
        self.assertEqual(supports[0]["price"], 9.2)
        self.assertEqual(supports[0]["bars_ago"], 5)
        self.assertEqual(supports[0]["unbroken_through_date"], day.isoformat())

    def test_watch_stop_needs_verified_support_and_correct_price_side(self):
        import importlib.util
        path = Path(__file__).resolve().parents[1] / "scripts" / "trend_buy_engine.py"
        spec = importlib.util.spec_from_file_location("risk_stops", path)
        engine = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(engine)
        zone = [9.771, 9.937]
        ctx = {"confirmed_swing_supports":[{
            "price":9.5, "date":"2026-10-09", "bars_ago":8,
            "source":"asof_65bar_confirmed_pivot_low",
            "unbroken_through_date":"2026-10-23"}]}
        good = engine.confirmed_watch_stop(ctx, zone, "2026-10-23")
        self.assertAlmostEqual(good["stop"], 9.453, places=3)
        self.assertLess(good["stop"], zone[0])
        self.assertLess(good["risk_pct"], 8)
        ctx["confirmed_swing_supports"][0]["price"]=9.9
        self.assertIsNone(engine.confirmed_watch_stop(ctx, zone, "2026-10-23"))
        ctx["confirmed_swing_supports"][0]["price"]=9.5
        ctx["confirmed_swing_supports"][0]["unbroken_through_date"]="2026-10-22"
        self.assertIsNone(engine.confirmed_watch_stop(ctx, zone, "2026-10-23"))
        ctx["confirmed_swing_supports"][0]["unbroken_through_date"]="2026-10-23"
        ctx["confirmed_swing_supports"][0]["bars_ago"]=2
        self.assertIsNone(engine.confirmed_watch_stop(ctx, zone, "2026-10-23"))

    def test_excessively_deep_true_support_does_not_fake_low_risk(self):
        import importlib.util
        path = Path(__file__).resolve().parents[1] / "scripts" / "trend_buy_engine.py"
        spec = importlib.util.spec_from_file_location("deep_stop", path)
        engine = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(engine)
        ctx = {"confirmed_swing_supports":[{
            "price":41.8, "date":"2026-10-19", "bars_ago":4,
            "source":"asof_65bar_confirmed_pivot_low",
            "unbroken_through_date":"2026-10-23"}]}
        # 10/23 Xinjie: 41.8 survives, but its >8% downside makes the
        # conditional MA20-retreat plan ineligible for a reliable watch zone.
        self.assertIsNone(engine.confirmed_watch_stop(
            ctx, [44.991,45.758], "2026-10-23"))


if __name__ == "__main__":
    unittest.main()
