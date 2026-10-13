"""No-live-source regression tests for the isolated validation pipeline."""
import json
import tempfile
import unittest
from pathlib import Path

from analyze import compile_results, future_result, basket_result


def save(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class ValidationTests(unittest.TestCase):
    def test_future_is_pending_before_horizon_matures(self):
        prices = {"2026-10-13": {"stocks": {"000001": {"close": 10, "history_basis": "qfq"}}}}
        calendar = ["2026-10-13", "2026-10-14"]
        self.assertEqual(future_result("000001", "2026-10-13", 1, prices, calendar,
                                       "2026-10-13")["state"], "pending")

    def test_missing_close_is_not_counted_as_loss(self):
        prices = {
            "2026-10-13": {"stocks": {"000001": {"close": 10, "history_basis": "qfq"}}},
            "2026-10-14": {"stocks": {}, "market_daily_return_pct": -2},
        }
        calendar = list(prices)
        self.assertEqual(future_result("000001", calendar[0], 1, prices, calendar,
                                       calendar[-1])["state"], "data_gap")

    def test_trend_lifecycle_distinguishes_downgrade_from_disappearance(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            start = "2026-10-13"
            next_day = "2026-10-14"
            final = "2026-10-15"
            for day, state in [(start, "趋势确认"),
                               (next_day, "候选趋势"),
                               (final, "观察")]:
                folder = base / "archive" / day
                save(folder / "manifest.json", {"trade_date": day})
                save(folder / "trend_registry.json", {"trade_date": day})
                save(folder / "universe.json", {"板块A": {
                    "market_state": state, "constituents": ["000001"],
                    "constituents_usable": True, "universe_issues": []}})
                save(folder / "trend_buy_formal_result.json",
                     {"trade_date": day, "run_id": "run-" + day, "ready": [],
                      "wait": [], "uncertain": [], "drop": []})
                save(base / "prices" / (day + ".json"), {
                    "trade_date": day,
                    "expected_market_calendar": [start, next_day, final],
                    "market_daily_return_pct": 0,
                    "stocks": {"000001": {"close": 10, "history_basis": "qfq"}}
                })
            result = compile_results(base)
            self.assertEqual(result["closed_confirmations"], 1)
            self.assertEqual(result["one_day_confirmations"], 1)
            events = json.loads((base / "results" / "trends.json").read_text())["items"]
            self.assertEqual(events[0]["first_downgrade_date"], next_day)
            self.assertEqual(events[0]["ending"], "lost_confirmation")

    def test_missing_archive_day_right_censors_episode(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            dates = ["2026-10-13", "2026-10-14", "2026-10-15"]
            for day in (dates[0], dates[2]):
                folder = base / "archive" / day
                save(folder / "manifest.json", {"trade_date": day})
                save(folder / "trend_registry.json", {"trade_date": day})
                save(folder / "universe.json", {"板块A": {
                    "market_state": "趋势确认", "constituents": ["000001"],
                    "constituents_usable": True, "universe_issues": []}})
                save(folder / "trend_buy_formal_result.json",
                     {"trade_date": day, "ready": [], "wait": [], "uncertain": [], "drop": []})
            save(base / "prices" / (dates[-1] + ".json"), {
                "expected_market_calendar": dates, "market_daily_return_pct": 0,
                "stocks": {"000001": {"close": 10, "history_basis": "qfq"}}
            })
            result = compile_results(base)
            self.assertEqual(result["closed_confirmations"], 0)
            self.assertEqual(result["censored_confirmations"], 1)
            self.assertEqual(result["trend_episodes"], 2)

    def test_basket_requires_near_complete_coverage(self):
        days = ["2026-10-13", "2026-10-14"]
        prices = {
            days[0]: {"stocks": {"000001": {"close": 10, "history_basis": "qfq"}}},
            days[1]: {"stocks": {"000001": {"close": 11, "history_basis": "qfq"}},
                      "market_daily_return_pct": 1}
        }
        value = basket_result(["000001", "000002"], days[0], 1, prices, days, days[-1])
        self.assertEqual(value["state"], "data_gap")


if __name__ == "__main__":
    unittest.main()
