import copy
import unittest

from scripts.validate_commodity_freshness import evaluate


ASOF_MORNING = "2026-11-09T06:30:00+08:00"
ASOF_CLOSE = "2026-11-09T18:30:00+08:00"
CALENDAR = "https://www.cmegroup.com/markets/metals/precious/gold.html"
SOURCE = "https://example.com/verified-session"
INSTRUMENT = "COMEX Gold futures"


def registry(reference_date="2026-11-05", quote_at=None):
    quote = ({"price_basis": "INTRADAY", "source": SOURCE,
              "observed_at": quote_at} if quote_at else None)
    return {"trends": [{
        "episode_id": "gold#2026-11-04",
        "trend_basis": "COMMODITY",
        "commodity_anchor": {"instrument": INSTRUMENT},
        "confirmation_audit": {"commodity_price_review": {
            "completed_reference": {"trade_date": reference_date},
            "current_quote": quote,
        }},
    }]}


def evidence(asof=ASOF_MORNING, status="WEEKEND", latest="2026-11-06",
             quote_at=None):
    row = {
        "episode_id": "gold#2026-11-04",
        "instrument": INSTRUMENT,
        "market_status": status,
        "calendar_source": CALENDAR,
        "calendar_checked_at": "2026-11-09T06:25:00+08:00",
        "latest_completed": {
            "trade_date": latest,
            "price_basis": "SETTLEMENT",
            "source": SOURCE,
            "available_at": "2026-11-07T06:00:00+08:00",
        },
        "latest_quote": None,
    }
    if quote_at:
        row["latest_quote"] = {
            "price_basis": "INTRADAY", "source": SOURCE,
            "observed_at": quote_at,
        }
    if asof == ASOF_CLOSE:
        row["calendar_checked_at"] = "2026-11-09T18:25:00+08:00"
    return {"asof": asof, "markets": [row]}


class FreshnessTests(unittest.TestCase):
    def test_monday_winter_closed_and_previous_friday_current(self):
        result = evaluate(registry("2026-11-06"), evidence(), "morning")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["results"][0]["completed_status"], "CURRENT")
        self.assertEqual(result["results"][0]["quote_status"], "NOT_REQUIRED_CLOSED")

    def test_monday_winter_closed_but_friday_reference_missing(self):
        result = evaluate(registry("2026-11-05"), evidence(), "morning")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["results"][0]["completed_status"], "NEW_COMPLETED_SESSION")

    def test_close_stale_completed_reference_blocks(self):
        result = evaluate(registry("2026-11-05"),
                          evidence(ASOF_CLOSE, "OPEN",
                                   quote_at="2026-11-09T18:20:00+08:00"), "close")
        self.assertFalse(result["ok"])
        self.assertIn("gold#2026-11-04:stale_completed_reference", result["errors"])

    def test_close_current_completed_and_quote_passes(self):
        quote_at = "2026-11-09T18:20:00+08:00"
        result = evaluate(registry("2026-11-06", quote_at),
                          evidence(ASOF_CLOSE, "OPEN", quote_at=quote_at), "close")
        self.assertTrue(result["ok"], result)

    def test_close_stale_intraday_quote_blocks(self):
        result = evaluate(registry("2026-11-06", "2026-11-06T09:17:00+08:00"),
                          evidence(ASOF_CLOSE, "OPEN",
                                   quote_at="2026-11-09T18:20:00+08:00"), "close")
        self.assertIn("gold#2026-11-04:stale_intraday_quote", result["errors"])

    def test_open_market_without_quote_is_not_silently_current(self):
        result = evaluate(registry("2026-11-06"),
                          evidence(ASOF_CLOSE, "OPEN"), "close")
        self.assertIn("gold#2026-11-04:open_quote_unverified", result["errors"])

    def test_source_availability_after_asof_is_rejected(self):
        event = evidence()
        event["markets"][0]["latest_completed"]["available_at"] = "2026-11-09T07:30:00+08:00"
        result = evaluate(registry("2026-11-06"), event, "morning")
        self.assertIn("gold#2026-11-04:latest_completed_unverified", result["errors"])

    def test_stale_calendar_verification_is_rejected(self):
        event = evidence()
        event["markets"][0]["calendar_checked_at"] = "2026-11-06T06:25:00+08:00"
        result = evaluate(registry("2026-11-06"), event, "morning")
        self.assertIn("gold#2026-11-04:session_calendar_unverified", result["errors"])

    def test_missing_market_evidence_is_rejected(self):
        event = evidence()
        event["markets"] = []
        result = evaluate(registry("2026-11-06"), event, "morning")
        self.assertIn("gold#2026-11-04:evidence_missing", result["errors"])

    def test_unverified_schedule_is_not_assumed_holiday(self):
        event = evidence()
        event["markets"][0]["market_status"] = "UNKNOWN"
        result = evaluate(registry("2026-11-06"), event, "morning")
        self.assertIn("gold#2026-11-04:session_calendar_unverified", result["errors"])

    def test_no_commodity_trends_need_no_commodity_evidence(self):
        self.assertTrue(evaluate({"trends": []}, {"asof": ASOF_MORNING, "markets": []},
                                 "morning")["ok"])

    def test_intraday_quote_in_the_future_is_rejected(self):
        event = evidence(ASOF_CLOSE, "OPEN",
                         quote_at="2026-11-09T19:00:00+08:00")
        result = evaluate(registry("2026-11-06"), event, "close")
        self.assertIn("gold#2026-11-04:latest_quote_invalid", result["errors"])


if __name__ == "__main__":
    unittest.main()
