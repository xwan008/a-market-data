"""Offline tests for independent forward-valuation SHADOW (stdlib only)."""
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("shadow", ROOT / "scripts" / "shadow_forward_valuation.py")
shadow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shadow)


def fixture():
    return {
        "model": "FORWARD_SHADOW_V1",
        "as_of_date": "2026-10-09",
        "companies": [{
            "code": "TEST01", "name": "Demo",
            "current_price": 30.0, "price_date": "2026-10-09",
            "valuation_date": "2026-09-18", "report_date": "2026-06-30",
            "formal_status": "WAIT", "transmission": "SUPPORTED",
            "valuation_archetype": "PE_FORWARD",
            "ma20": 27.0, "ma60": 25.0,
            "assumptions": {"reference_exit_pe": 20.0, "horizon_years": 1.0, "required_return": 0.1},
            "scenarios": None,
        }]
    }


def cases():
    def evidence():
        return [{"source_url": "https://example.com/quarter", "published_at": "2026-06-30", "business_line": "primary"}]
    return [
        {"kind": "bear", "forward_eps": 1, "exit_pe": 15, "probability": .2, "evidence": evidence(), "falsifier": "loss of customer"},
        {"kind": "base", "forward_eps": 2, "exit_pe": 20, "probability": .5, "evidence": evidence(), "falsifier": "gross margin fall"},
        {"kind": "bull", "forward_eps": 3, "exit_pe": 25, "probability": .3, "evidence": evidence(), "falsifier": "capacity delay"},
    ]


class ShadowTests(unittest.TestCase):
    def test_stale_pe_does_not_become_valuation(self):
        row = shadow.evaluate(fixture())["companies"][0]
        self.assertIn("STALE_MULTIPLE", row["data_flags"])
        self.assertEqual(row["market_implied"]["status"], "CONDITIONAL_SENSITIVITY")
        self.assertAlmostEqual(row["market_implied"]["implied_forward_eps"], 1.65)
        self.assertIsNone(row["scenario_valuation"]["expected_value_now"])

    def test_valid_assumptions_are_just_scenarios_not_ready(self):
        payload = fixture()
        payload["companies"][0]["scenarios"] = cases()
        row = shadow.evaluate(payload)["companies"][0]
        self.assertEqual(row["formal_status_unchanged"], "WAIT")
        self.assertEqual(row["scenario_valuation"]["status"], "SCENARIO_ASSUMPTIONS_TO_VERIFY")
        # (0.2*15 + 0.5*40 + 0.3*75)/1.1
        self.assertAlmostEqual(row["scenario_valuation"]["expected_value_now"], 41.3636, places=4)

    def test_future_evidence_rejected(self):
        p = fixture()
        p["companies"][0]["scenarios"] = cases()
        p["companies"][0]["scenarios"][0]["evidence"][0]["published_at"] = "2026-10-10"
        row = shadow.evaluate(p)["companies"][0]
        self.assertEqual(row["scenario_valuation"]["status"], "INSUFFICIENT_EVIDENCE")
        self.assertIsNone(row["scenario_valuation"]["expected_value_now"])

    def test_incomplete_probability_rejected(self):
        p = fixture()
        p["companies"][0]["scenarios"] = cases()
        p["companies"][0]["scenarios"][0]["probability"] = .3
        row = shadow.evaluate(p)["companies"][0]
        self.assertEqual(row["scenario_valuation"]["status"], "INVALID_PROBABILITIES")

    def test_early_evidence_never_becomes_wait(self):
        p = fixture()
        p["companies"][0]["transmission"] = "EARLY_EVIDENCE"
        p["companies"][0]["formal_status"] = "PRE_SCREENED_OUT"
        row = shadow.evaluate(p)["companies"][0]
        self.assertEqual(row["shadow_scope"], "EARLY_OPPORTUNITY_OBSERVATION")
        self.assertEqual(row["formal_status_unchanged"], "PRE_SCREENED_OUT")

    def test_cyclical_does_not_use_pe_model(self):
        p = fixture()
        p["companies"][0]["valuation_archetype"] = "CYCLICAL_NORMALIZED"
        row = shadow.evaluate(p)["companies"][0]
        self.assertEqual(row["scenario_valuation"]["status"], "UNSUPPORTED_ARCHETYPE")
        self.assertIsNone(row["market_implied"]["implied_forward_eps"])

    def test_old_price_and_future_report_rejected(self):
        p = fixture()
        p["companies"][0]["price_date"] = "2026-10-08"
        row = shadow.evaluate(p)["companies"][0]
        self.assertIn("PRICE_DATE_OR_PRICE_INVALID", row["data_flags"])
        p = fixture()
        p["companies"][0]["report_date"] = "2026-10-11"
        row = shadow.evaluate(p)["companies"][0]
        self.assertIn("FUTURE_REPORT_DATE", row["data_flags"])

    def test_no_duplicate_codes_and_no_implicit_default_assumptions(self):
        p = fixture()
        p["companies"][0]["assumptions"] = None
        row = shadow.evaluate(p)["companies"][0]
        self.assertIsNone(row["market_implied"]["implied_forward_eps"])
        p["companies"].append(dict(p["companies"][0]))
        with self.assertRaises(ValueError):
            shadow.evaluate(p)

    def test_archived_case_data_exist(self):
        p = ROOT / "research" / "shadow" / "forward_valuation_input_2026-10-09.json"
        if p.is_file():
            payload = json.loads(p.read_text(encoding="utf-8"))
            result = shadow.evaluate(payload)
            self.assertEqual(result["company_count"], 4)
            self.assertTrue(all("STALE_MULTIPLE" in row["data_flags"] for row in result["companies"]))
            self.assertTrue(all(row["scenario_valuation"]["expected_value_now"] is None for row in result["companies"]))


if __name__ == "__main__":
    unittest.main()
