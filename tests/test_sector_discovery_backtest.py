import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from backtest_sector_discovery_asof import asof_features, future_return, load_days


class PointInTimeTests(unittest.TestCase):
    def day(self, date, price):
        return (date, "sha-" + date, {
            "trade_date": date, "market_status": "closed",
            "stocks": {"000001": {"price": price, "volume": 100, "confidence": "high"}}
        }, {"companies": {"000001": {"mapping_status": "mapped",
                                    "industry_code": "S123456", "sw_level3_name": "test"}}})

    def test_future_data_cannot_change_past_features(self):
        days = [self.day(f"2026-09-{d:02d}", 100+d) for d in range(14, 21)]
        baseline = asof_features(days, 5)["companies"]["000001"]["phase_evidence"]
        days[6][2]["stocks"]["000001"]["price"] = 99999
        after = asof_features(days, 5)["companies"]["000001"]["phase_evidence"]
        self.assertEqual(baseline, after)
        self.assertIsNone(baseline["volume_ratio_1d"])
        self.assertIsNotNone(baseline["return_3d_pct"])
        self.assertIsNotNone(baseline["return_5d_pct"])

    def test_future_return_is_ex_post_only(self):
        now = self.day("2026-10-08", 10)[2]
        later = self.day("2026-10-09", 9)[2]
        self.assertEqual(future_return(now, later, {"000001"}), None)
        # Enough participants to support a median performance.
        for i in range(2,7):
            code = f"{i:06d}"
            now["stocks"][code] = {"price": 10, "confidence": "high"}
            later["stocks"][code] = {"price": 9, "confidence": "high"}
        self.assertEqual(future_return(now, later, set(now["stocks"])), -10.0)

    def test_mismatched_snapshot_date_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            day = "2026-10-08"
            target = root / day
            target.mkdir()
            latest = self.day("2026-10-09", 11)[2]
            (target/"latest.json").write_text(json.dumps(latest))
            (target/"company_industry_index.json").write_text(json.dumps({"companies":{"000001":{"industry_code":"S1"}}}))
            with self.assertRaisesRegex(ValueError, "ASOF_DATE_MISMATCH"):
                load_days(root, {"snapshots":[{"trade_date":day, "commit":"fake"}]})


if __name__ == "__main__":
    unittest.main()
