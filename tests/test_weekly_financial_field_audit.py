"""Weekly fundamental field coverage is diagnostic, not a gate override."""
import importlib.util
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location(
    "financial_audit",ROOT/"scripts/audit_weekly_financial_fields.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class FinancialCoverageTests(unittest.TestCase):
    def test_general_coverage_not_equivalent_to_deducted_coverage(self):
        payload={
           "trade_date":"2026-10-30",
           "fundamental_stats":{"financial_usable":3,
                "valuation_usable":3,"deduct_profit_growth_usable":1},
           "stocks":{
             "000001":{"fundamentals":{"revenue_yoy":8,
                 "net_profit_yoy":20,"deduct_net_profit_yoy":15}},
             "000002":{"fundamentals":{"revenue_yoy":9,
                 "net_profit_yoy":21,"deduct_net_profit_yoy":None}},
             "000003":{"fundamentals":{"revenue_yoy":10,
                 "net_profit_yoy":22,"deduct_basic_eps_yoy":False}},
           }
        }
        got=mod.calculate(payload)
        self.assertEqual(got["reported_financial_usable"],3)
        self.assertEqual(got["core_profit_growth_available"],1)
        self.assertEqual(got["field_coverage"]["net_profit_yoy"]["count"],3)
        self.assertEqual(got["field_coverage"]["deduct_net_profit_yoy"]["count"],1)
        self.assertTrue(got["data_quality_warning_not_failure"])
        self.assertFalse(got["new_stock_research_or_forecast_generated"])

    def test_no_stocks_is_not_valid_coverage_denominator(self):
        with self.assertRaisesRegex(ValueError,"missing_full_market_stocks"):
            mod.calculate({"stocks":{}})

if __name__=="__main__":
    unittest.main()
