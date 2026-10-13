import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_holding_chart_data as charts


def bar(day, close, **extra):
    return {"date": day, "open": close, "high": close + 1, "low": close - 1,
            "close": close, "basis": "qfq", **extra}


def snapshot(day="2026-10-13", at="2026-10-13T09:38:00+08:00", price=5.8):
    return {"result_kind": "a_share_intraday_market_snapshot",
            "trade_date": day, "captured_at": at,
            "validation": {"status": "passed"},
            "holding_stocks": {"601212": {
                "code": "601212", "source_scope": "holding_watchlist",
                "confidence": "high", "price": price,
                "quote_time": at}}}


class HoldingChartsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.directory.joinpath("6012.json").write_text(json.dumps({"stocks": {
            "601212": {"history": [
                bar("2026-10-08", 5.3), bar("2026-10-09", 5.5),
                bar("2026-10-12", 5.6), bar("2026-10-13", 5.7),
                bar("2026-10-14", 5.8)]
            }}}), encoding="utf-8")
        self.watchlist = [{"code": "601212", "company_name": "白银有色"}]

    def build(self, snap=None, old=None):
        return charts.build_chart_data(
            snap or snapshot(), self.watchlist, old or {}, self.directory)

    def test_daily_only_completed_and_does_not_fill_weekend(self):
        result = self.build()
        data = result["stocks"]["601212"]
        self.assertEqual([x["date"] for x in data["daily_bars"]],
                         ["2026-10-08", "2026-10-09", "2026-10-12"])
        self.assertEqual(data["daily_basis"], "qfq")
        self.assertEqual(len(data["intraday_points"]), 1)

    def test_four_slots_accumulate_replace_same_slot_but_not_other_days(self):
        result = self.build()
        for at, p in [
            ("2026-10-13T10:40:00+08:00", 5.85),
            ("2026-10-13T13:19:00+08:00", 5.72),
            ("2026-10-13T14:29:00+08:00", 5.94)]:
            result = self.build(snapshot(at=at, price=p), result)
        points = result["stocks"]["601212"]["intraday_points"]
        self.assertEqual([x["slot"] for x in points], [1, 2, 3, 4])
        result = self.build(snapshot(at="2026-10-13T10:50:00+08:00", price=5.9), result)
        self.assertEqual(len(result["stocks"]["601212"]["intraday_points"]), 4)
        self.assertEqual(result["stocks"]["601212"]["intraday_points"][1]["price"], 5.9)
        result = self.build(snapshot(at="2026-10-13T09:32:00+08:00", price=6.0), result)
        self.assertEqual(result["stocks"]["601212"]["intraday_points"][0]["price"], 5.8)

    def test_next_day_resets_intraday_and_preserves_no_future(self):
        result = self.build()
        tomorrow = self.build(snapshot(day="2026-10-14", at="2026-10-14T09:38:00+08:00"), result)
        self.assertEqual(len(tomorrow["stocks"]["601212"]["intraday_points"]), 1)
        self.assertEqual(tomorrow["stocks"]["601212"]["daily_last_date"], "2026-10-13")

    def test_missing_or_bad_quotes_never_generate_fake_points(self):
        bad = snapshot()
        bad["holding_stocks"]["601212"]["price"] = None
        self.assertEqual(self.build(bad)["stocks"]["601212"]["intraday_points"], [])
        bad = snapshot()
        bad["holding_stocks"]["601212"]["quote_time"] = "2026-10-12T14:27:00+08:00"
        self.assertEqual(self.build(bad)["stocks"]["601212"]["intraday_points"], [])
        bad = snapshot()
        bad["holding_stocks"] = {}
        with self.assertRaisesRegex(ValueError, "COVERAGE"):
            self.build(bad)

    def test_no_leaking_trade_fields_or_mixed_price_basis(self):
        path = self.directory / "6012.json"
        data = json.loads(path.read_text())
        data["stocks"]["601212"]["history"][1]["basis"] = "raw"
        path.write_text(json.dumps(data))
        result = self.build()
        self.assertEqual(len(result["stocks"]["601212"]["daily_bars"]), 1)
        text = json.dumps(result, ensure_ascii=False)
        for field in ["实际成交股数", "成本", "成交价", "company_name", "shares"]:
            self.assertNotIn(field, text)


if __name__ == "__main__":
    unittest.main()
