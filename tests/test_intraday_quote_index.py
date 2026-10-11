"""Public full-market quote index: identity, privacy and expiry regressions."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import intraday_quote_index as idx


DAY = "2026-10-09"
CAPTURE = "2026-10-09T10:35:00+08:00"
CODE = "600001"


def quote(code, sina, tencent, trade_date):
    return {
        "name": "公开行情",
        "price": 21.4,
        "prev_close": 21.0,
        "change_pct": 1.9,
        "quote_time": "2026-10-09T10:34:00+08:00",
        "confidence": "high",
        "warnings": [],
        "primary_source": "sina",
    }


class QuoteIndexTests(unittest.TestCase):
    def build(self, directory, capture=CAPTURE):
        # Public full-market coverage is independent of any person's holdings.
        sina = {f"{600000 + i:06d}": {} for i in range(505)}
        manifest, payloads = idx.build_public_quote_index(
            sina, {}, DAY, capture, quote, Path(directory)
        )
        for relative, text in payloads.items():
            target = Path(directory) / Path(relative).name
            target.write_text(text, encoding="utf-8")
        snapshot = {
            "trade_date": DAY, "captured_at": capture,
            "portfolio_quote_index": manifest,
        }
        return snapshot, payloads

    def test_full_market_coverage_and_valid_quote(self):
        with tempfile.TemporaryDirectory() as folder:
            snapshot, data = self.build(folder)
            self.assertEqual(snapshot["portfolio_quote_index"]["status"], "available")
            self.assertEqual(snapshot["portfolio_quote_index"]["quote_count"], 505)
            self.assertEqual(
                idx.verify_public_quote_for_held_code(snapshot, CODE,
                    data["research/intraday_quote_shards/60.json"].encode("utf-8"))["price"], 21.4
            )
            self.assertNotIn("holding", json.dumps(snapshot).lower())
            self.assertNotIn("airtable", json.dumps(snapshot).lower())

    def test_tamper_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            snapshot, data = self.build(folder)
            raw = data["research/intraday_quote_shards/60.json"].encode("utf-8")
            with self.assertRaisesRegex(ValueError, "INDEX_MISMATCH"):
                idx.verify_public_quote_for_held_code(snapshot, CODE, raw + b" ")

    def test_quote_time_stale_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            snapshot, data = self.build(folder, "2026-10-09T11:10:00+08:00")
            raw = data["research/intraday_quote_shards/60.json"].encode("utf-8")
            with self.assertRaisesRegex(ValueError, "PORTFOLIO_QUOTE_UNAVAILABLE"):
                idx.verify_public_quote_for_held_code(snapshot, CODE, raw)

    def test_different_day_samples_not_reused(self):
        with tempfile.TemporaryDirectory() as folder:
            self.build(folder)
            snapshot, data = self.build(folder, "2026-10-09T10:45:00+08:00")
            row = json.loads(data["research/intraday_quote_shards/60.json"])["quotes"][CODE]
            self.assertEqual(len(row["samples"]), 2)
            for item in row["samples"]:
                self.assertEqual(item["trade_date"], DAY)
            self.assertNotEqual(row["samples"][0]["captured_at"], row["samples"][1]["captured_at"])

    def test_missing_code_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            snapshot, data = self.build(folder)
            raw = data["research/intraday_quote_shards/60.json"].encode("utf-8")
            with self.assertRaisesRegex(ValueError, "NOT_FOUND"):
                idx.verify_public_quote_for_held_code(snapshot, "609999", raw)


if __name__ == "__main__":
    unittest.main()
