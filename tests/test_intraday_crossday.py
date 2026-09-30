import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import intraday_crossday_context as cd


class CrossDayTest(unittest.TestCase):
    def test_last_persisted_scan_is_independent_of_same_day(self):
        with tempfile.TemporaryDirectory() as temp:
            state_path = Path(temp) / "state.json"
            state = {
                "result_kind": "a_share_intraday_monitor_state",
                "trade_date": "2026-09-29", "monitor_date": "2026-09-29",
                "last_scan_at": "2026-09-29T14:31:00+08:00",
                "frozen_trends": [{"trend_name": "风电设备", "industry_codes": ["S630602"]}],
                "industry_history": {"风电设备": [{
                    "scan_at": "2026-09-29T14:31:00+08:00", "data_quality": "READY",
                    "current_state": "分歧", "up_ratio": 0.8889
                }]},
                "stock_history": {}
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")
            archive = {"schema_version": 1, "result_kind": "a_share_intraday_crossday_archive", "days": []}
            rolled = cd.merge_archive(archive, state_path, "2026-09-30")
            self.assertEqual(rolled["days"][0]["trends"]["风电设备"]["last_intraday_state"], "分歧")
            same_day = cd.merge_archive(archive, state_path, "2026-09-29")
            self.assertFalse(same_day["days"])

    def test_stale_bars_cannot_be_called_yesterday(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "0024.json"
            path.write_text(json.dumps({"stocks": {"002487": {"history": [
                {"date": "2026-09-28", "close": 10, "confidence": "high"},
                {"date": "2026-09-29", "close": 11, "confidence": "invalid"}
            ]}}}), encoding="utf-8")
            with patch.object(cd, "HISTORY_SHARDS_DIR", Path(temp)):
                history, errors, reads = cd.read_price_histories({"002487"}, "2026-09-29")
            self.assertFalse(history)
            self.assertFalse(errors)
            self.assertEqual(reads, 1)

    def test_rolling_return_and_membership_gate(self):
        dates = [f"2026-09-{n:02d}" for n in range(1, 22)]
        rows = [{"date": d, "close": 100+i, "confidence": "high"} for i,d in enumerate(dates)]
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "0024.json").write_text(json.dumps({"stocks": {"002487": {"history": rows}}}), encoding="utf-8")
            archive = {"days": [{"trade_date": dates[-1], "trends": {
                "风电设备": {"industry_codes": ["S1"], "last_intraday_state": "分歧"}
            }}]}
            with patch.object(cd, "HISTORY_SHARDS_DIR", Path(temp)):
                result, audit = cd.build_board_context(
                    {"风电设备": {"industry_codes": ["S2"], "company_codes": ["002487"]}}, dates[-1], archive)
            ctx = result["风电设备"]
            self.assertEqual(ctx["seven_day"]["status"], "available")
            self.assertEqual(ctx["seven_day"]["window_sessions"], 7)
            self.assertEqual(ctx["seven_day"]["sample_count"], 1)
            self.assertAlmostEqual(ctx["seven_day"]["median_constituent_return_pct"], (120 / 113 - 1) * 100, places=4)
            self.assertNotIn("five_day", ctx)
            self.assertEqual(audit["board_history_7d_available_count"], 1)
            self.assertNotIn("board_history_5d_available_count", audit)
            self.assertFalse(ctx["previous_trade_day"]["same_industry_codes"])
            self.assertEqual(audit["board_previous_day_available_count"], 1)

    def test_stock_7d_requires_eight_valid_closes_and_is_stale_safe(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Path(temp) / "0024.json"
            rows = [
                {"date": f"2026-09-{d:02d}", "close": 100 + d, "confidence": "high"}
                for d in range(15, 23)
            ]
            store.write_text(json.dumps({"stocks": {"002487": {"history": rows}}}), encoding="utf-8")
            with patch.object(cd, "HISTORY_SHARDS_DIR", Path(temp)):
                ready, audit = cd.build_stock_seven_day_context({"002487"}, "2026-09-22")
                stale, _ = cd.build_stock_seven_day_context({"002487"}, "2026-09-23")
            self.assertEqual(ready["002487"]["window_sessions"], 7)
            self.assertEqual(ready["002487"]["observation_count"], 8)
            self.assertAlmostEqual(ready["002487"]["close_change_7d_pct"], (122 / 115 - 1) * 100, places=4)
            self.assertEqual(audit["stock_history_7d_available_count"], 1)
            self.assertEqual(stale["002487"]["status"], "unavailable")
            rows[0]["confidence"] = "invalid"
            store.write_text(json.dumps({"stocks": {"002487": {"history": rows}}}), encoding="utf-8")
            with patch.object(cd, "HISTORY_SHARDS_DIR", Path(temp)):
                short, _ = cd.build_stock_seven_day_context({"002487"}, "2026-09-22")
            self.assertEqual(short["002487"]["status"], "unavailable")
            self.assertIsNone(short["002487"]["close_change_7d_pct"])

    def test_upstream_stock_summary_adds_7d_without_breaking_research(self):
        from build_history import build_stock_summary
        rows = [{"date": f"2026-09-{d:02d}", "close": 100 + d,
                 "high": 101 + d, "low": 99 + d, "confidence": "high"}
                for d in range(15, 23)]
        data = build_stock_summary({"history": rows}, expected_trade_date="2026-09-22")
        self.assertAlmostEqual(data["close_change_7d_pct"], (122 / 115 - 1) * 100, places=4)
        self.assertIn("close_change_5d_pct", data)  # Other formal research remains untouched.
        self.assertEqual(build_stock_summary({"history": rows[:-1]},
                         expected_trade_date="2026-09-21")["close_change_7d_pct"], None)


if __name__ == "__main__":
    unittest.main()
