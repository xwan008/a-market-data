"""Offline, no-lookahead validation of shadow cyclical PB/ROE tool."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("shadow_cyclical",ROOT/"scripts"/"shadow_cyclical_valuation.py")
engine=importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)

def sample():
    return {"model":"CYCLICAL_PB_ROE_SHADOW_V1","as_of_date":"2026-10-09",
        "companies":[{"code":"600971","name":"恒源煤电","formal_status":"WAIT",
            "current_price":8.39,"price_date":"2026-10-09",
            "attributable_equity":11738921566.95,"issued_shares":1200004884,
            "source":{"url":"https://example.com/company-report","published_at":"2026-08-21","report_date":"2026-06-30"},
            "assumptions":{"required_return":.10,"long_term_growth":.02},"scenarios":None}]}

def scenarios():
    return [
        {"kind":"bear","probability":.3,"forward_roe":.04,"forward_bvps":9.8,
         "evidence":[{"url":"https://example.com/fin","published_at":"2026-08-21"}],
         "assumption_rationale":"Hypothetical stressed coal ROE; not a disclosed forecast","falsifier":"profit collapse"},
        {"kind":"base","probability":.5,"forward_roe":.09,"forward_bvps":10.2,
         "evidence":[{"url":"https://example.com/fin","published_at":"2026-08-21"}],
         "assumption_rationale":"Hypothetical recoverable ROE for unit validation","falsifier":"margin erosion"},
        {"kind":"bull","probability":.2,"forward_roe":.15,"forward_bvps":10.7,
         "evidence":[{"url":"https://example.com/fin","published_at":"2026-08-21"}],
         "assumption_rationale":"Hypothetical high-coal-price case solely for test","falsifier":"coal price drops"}]

class CyclicalTests(unittest.TestCase):
    def test_actual_filing_conditional_pb_and_roe(self):
        p=ROOT/"research"/"shadow"/"cyclical_pb_roe_input_2026-10-09.json"
        if not p.is_file():
            self.skipTest("archived input not checked out")
        raw=json.loads(p.read_text(encoding="utf-8"))
        row=engine.run(raw)["companies"][0]
        self.assertEqual(row["original_formal_status"],"WAIT")
        self.assertEqual(row["status"],"CONDITIONAL_SENSITIVITY_ONLY")
        self.assertAlmostEqual(row["book_value_per_share"],9.782395,places=5)
        self.assertAlmostEqual(row["implied_pb_at_current_price"],.857663,places=5)
        self.assertAlmostEqual(row["market_implied_sustainable_roe"]["roe_fraction"],.088613,places=5)
        self.assertIsNone(row["forward_scenario_value"])

    def test_futuristic_filing_rejected(self):
        p=sample()
        p["companies"][0]["source"]["published_at"]="2026-10-10"
        row=engine.run(p)["companies"][0]
        self.assertIn("FUTURE_SOURCE",row["flags"])
        self.assertIsNone(row["book_value_per_share"])

    def test_date_mismatch(self):
        p=sample()
        p["companies"][0]["price_date"]="2026-10-08"
        row=engine.run(p)["companies"][0]
        self.assertIn("PRICE_DATE_MISMATCH",row["flags"])

    def test_missing_equity_not_quietly_estimated_from_stale_pb(self):
        p=sample()
        p["companies"][0]["attributable_equity"]=None
        row=engine.run(p)["companies"][0]
        self.assertIn("BOOK_VALUE_MISSING",row["flags"])
        self.assertIsNone(row["market_implied_sustainable_roe"])

    def test_incorrect_gordon_parameters(self):
        p=sample()
        p["companies"][0]["assumptions"]["long_term_growth"]=.10
        row=engine.run(p)["companies"][0]
        self.assertIn("MISSING_CONDITIONAL_ASSUMPTIONS",row["flags"])

    def test_synthetic_scenario_calculation_is_not_ready(self):
        p=sample()
        p["companies"][0]["scenarios"]=scenarios()
        p["companies"][0]["assumptions"]["horizon_years"]=1
        row=engine.run(p)["companies"][0]
        self.assertEqual(row["status"],"SCENARIO_ASSUMPTIONS_TO_VERIFY")
        self.assertEqual(row["original_formal_status"],"WAIT")
        self.assertIsNotNone(row["forward_scenario_value"]["expected_value_ex_dividends"])

    def test_invalid_probability_rejected(self):
        p=sample()
        p["companies"][0]["scenarios"]=scenarios()
        p["companies"][0]["scenarios"][0]["probability"]=.4
        row=engine.run(p)["companies"][0]
        self.assertIn("INVALID_PROBABILITIES",row["flags"])

    def test_scenario_future_evidence_rejected(self):
        p=sample()
        p["companies"][0]["scenarios"]=scenarios()
        p["companies"][0]["assumptions"]["horizon_years"]=1
        p["companies"][0]["scenarios"][0]["evidence"][0]["published_at"]="2026-10-11"
        row=engine.run(p)["companies"][0]
        self.assertIn("SCENARIO_EVIDENCE_INCOMPLETE",row["flags"])
        self.assertIsNone(row["forward_scenario_value"])

    def test_duplicate_codes(self):
        p=sample()
        p["companies"].append(dict(p["companies"][0]))
        with self.assertRaises(ValueError):
            engine.run(p)

if __name__=="__main__":
    unittest.main()
