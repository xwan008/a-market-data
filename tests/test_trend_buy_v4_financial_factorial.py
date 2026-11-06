"""Factorial V4 vs original must use identical dated finance and unchanged model budget."""
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"experiments"))
sys.path.insert(0,str(ROOT/"scripts"))
import trend_buy_v4_financial_factorial_shadow as factor
import build_trend_buy_manual_research as original

DAY="2026-11-05"
def row(code,growth,net_growth,noncore=None):
    return {
        "code":code,"price":10,"ma20":9,"ma60":8,
        "pe_dynamic":11,"revenue_yoy":growth,
        "net_profit_yoy":net_growth,"roe":9,
        "operating_cashflow_per_share":1,
        "basic_eps":.25,"deduct_basic_eps":None,
        "deduct_net_profit_yoy":noncore,"nonrecurring_profit_share_pct":None
    }


class CoreFactorialTest(unittest.TestCase):
    def test_default_legacy_score_unchanged_even_with_new_field(self):
        rows=[row("000001",10,20),row("000002",12,30),row("000003",14,40)]
        legacy=original.scores(rows)
        patched=[{**r,"deduct_net_profit_yoy":-30 if i==2 else 100+i}
                 for i,r in enumerate(rows)]
        self.assertEqual(original.scores(patched),legacy)
        self.assertNotEqual(original.scores(patched,financial_mode="CORE_FIRST"),
                            legacy)

    def test_same_model_weights_no_new_technical_rule(self):
        rows=[row("000001",10,20),row("000002",12,30),row("000003",14,40)]
        scores=original.scores(rows,financial_mode="LEGACY")
        self.assertTrue(all(0<=z[0]<=1 for z in scores))
        with self.assertRaisesRegex(ValueError,"unsupported_financial_scoring_mode"):
            original.scores(rows,financial_mode="ARTIFICIAL")

    def test_date_and_period_guard(self):
        stock={"code":"000506","report_date":"2026-09-30"}
        source={
            "source_report":factor.SOURCE,"report_date":"2026-09-30",
            "notice_date":"2026-10-27","update_date":"2026-10-27",
            "deduct_net_profit_yoy":127.1,"deduct_net_profit":115251654.93,
            "nonrecurring_profit_share_pct":50.87,
        }
        values,reason=factor.validated_patch(stock,source,DAY,DAY)
        self.assertEqual(reason,"VALID_MATCH")
        self.assertEqual(values["deduct_net_profit_yoy"],127.1)
        values,reason=factor.validated_patch(stock,source,"2026-10-25",DAY)
        self.assertIsNone(values)
        self.assertIn("UNDISCLOSED",reason)
        values,reason=factor.validated_patch(stock,source,DAY,"2026-11-04")
        self.assertIsNone(values)
        self.assertEqual(reason,"SOURCE_SNAPSHOT_BEFORE_ASOF")
        values,reason=factor.validated_patch({**stock,"report_date":"2026-06-30"},
                                                 source,DAY,DAY)
        self.assertIsNone(values)
        self.assertEqual(reason,"REPORT_PERIOD_MISMATCH")

    def test_unknown_and_existing_values_stay_unknown_or_unchanged(self):
        stock={"code":"000506","report_date":"2026-09-30",
               "deduct_net_profit_yoy":4}
        source={"source_report":factor.SOURCE,
            "report_date":"2026-09-30",
            "notice_date":"2026-10-27","update_date":"2026-10-27",
            "deduct_net_profit_yoy":127.1,"deduct_net_profit":115251654.93}
        values,_=factor.validated_patch(stock,source,DAY,DAY)
        self.assertNotIn("deduct_net_profit_yoy",values)
        self.assertEqual(values["deduct_net_profit"],115251654.93)
        source["update_date"]=None
        values,reason=factor.validated_patch(stock,source,DAY,DAY)
        self.assertIsNone(values)
        self.assertEqual(reason,"UPDATE_TIME_NOT_VERIFIED")

    def test_missing_data_not_interpreted_as_zero(self):
        stock={"code":"000506","report_date":"2026-09-30"}
        source={"source_report":factor.SOURCE,"report_date":"2026-09-30",
           "notice_date":"2026-10-27","update_date":"2026-10-27",
           "deduct_net_profit_yoy":None}
        values,reason=factor.validated_patch(stock,source,DAY,DAY)
        self.assertIsNone(values)
        self.assertEqual(reason,"NO_NEW_VERIFIED_FIELDS")


if __name__=="__main__":
    unittest.main()
