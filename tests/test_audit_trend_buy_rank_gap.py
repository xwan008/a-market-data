#!/usr/bin/env python3
"""Tests for single-source read-only trend-buy audit (never a trade model)."""
import importlib.util
from pathlib import Path
import unittest

FILE = Path(__file__).resolve().parents[1] / "scripts" / "audit_trend_buy_rank_gap.py"
spec = importlib.util.spec_from_file_location("audit_trend_buy_rank_gap", FILE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def row(code, rank, previous, recent, up, fresh):
    return {
        "code": code, "company_name": code, "trend_name": "线下药店",
        "data_date": "2026-11-17", "model_priority": rank, "status": "WAIT",
        "current_price": 26.61, "structure_confirmed": False,
        "wait_reason": "WAIT_PULLBACK",
        "phase_evidence": {
            "previous_5d_return_pct": previous, "return_5d_pct": recent,
            "return_3d_pct": 7.08, "positive_days_5d": up, "fresh_break": fresh,
        },
        "technical_context": {
            "distance_to_ma20_pct": 3.1, "close_location_pct": 95,
            "volume_ratio_1d_vs_20d": 0.958,
            "first_effective_resistance": {"price": 27.68},
        },
    }


class TestRankGapAudit(unittest.TestCase):
    def setUp(self):
        self.formal = {
            "result_kind": "a_share_trend_buy_result", "mode": "FORMAL",
            "trade_date": "2026-11-17", "ready": [],
            "wait": [
                row("603233", 1, -3.06, 2.66, 4, False),
                row("002727", 2, -5.74, 7.26, 3, True),
                row("603939", 4, -10.28, 8.48, 4, True),
            ],
        }

    def test_identifies_opportunity_gap_without_trade_promotion(self):
        result = mod.audit(self.formal)
        self.assertEqual(result["reversal_observation_count"], 2)
        self.assertEqual(result["reversal_outside_top2_count"], 1)
        yi = next(x for x in result["rows"] if x["code"] == "603939")
        self.assertTrue(yi["reversal_observed"])
        self.assertEqual(yi["official_rank"], 4)
        self.assertEqual(yi["official_status"], "WAIT")
        self.assertFalse(yi["ready_unchanged"])
        self.assertFalse(yi["setup_confirmed"])
        self.assertEqual(yi["overhead_distance_pct"], 4.02)
        self.assertEqual(self.formal["wait"][2]["status"], "WAIT")

    def test_missing_data_fails_reversal_positive(self):
        self.formal["wait"][2]["phase_evidence"]["return_5d_pct"] = None
        yi = next(x for x in mod.audit(self.formal)["rows"] if x["code"] == "603939")
        self.assertFalse(yi["reversal_observed"])

    def test_future_date_rejected(self):
        self.formal["wait"][1]["data_date"] = "2026-11-18"
        with self.assertRaisesRegex(ValueError, "ASOF_PRICE_EVIDENCE_MISMATCH"):
            mod.audit(self.formal)

    def test_outcomes_cannot_change_rank_or_permission(self):
        history = {"items": [{"trade_date": "2026-11-17", "code": "603939",
                              "horizons": {
                                  "1": {"state": "pending", "excess_vs_market_pct": 30},
                                  "3": {"state": "matured", "excess_vs_market_pct": 2.15},
                              }}]}
        yi = next(x for x in mod.audit(self.formal, history)["rows"]
                  if x["code"] == "603939")
        self.assertEqual(yi["observed_excess_vs_market_pct"], {"3": 2.15})
        self.assertEqual(yi["official_rank"], 4)
        self.assertFalse(yi["ready_unchanged"])


if __name__ == "__main__":
    unittest.main()
