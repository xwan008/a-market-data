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
            self.assertEqual(ctx["five_day"]["status"], "available")
            self.assertEqual(ctx["twenty_day"]["sample_count"], 1)
            self.assertFalse(ctx["previous_trade_day"]["same_industry_codes"])
            self.assertEqual(audit["board_previous_day_available_count"], 1)


if __name__ == "__main__":
    unittest.main()
