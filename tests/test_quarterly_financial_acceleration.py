import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))

from refresh_core_financial_only import (
    build_quarterly_acceleration,
    find_asof_row,
)
from prepare_trend_buy_candidates import quarterly_acceleration_shadow_scores


def row(period, notice, *, update=None, profit_yoy=None, revenue_yoy=None,
        core=100.0, cumulative_yoy=10.0):
    return {
        "SECURITY_CODE":"600519",
        "REPORT_DATE":period,
        "NOTICE_DATE":notice,
        "UPDATE_DATE":update or notice,
        "KCFJCXSYJLR":core,
        "KCFJCXSYJLRTZ":cumulative_yoy,
        "DJD_DEDUCTDPNP_YOY":profit_yoy,
        "DJD_TOI_YOY":revenue_yoy,
        "PARENTNETPROFIT":120.0,
    }


class QuarterlyFinancialAccelerationTests(unittest.TestCase):
    def test_calculates_adjacent_single_quarter_yoy_acceleration(self):
        record=find_asof_row([
            row("2026-09-30","2026-10-31",profit_yoy=42.0,revenue_yoy=18.0),
            row("2026-06-30","2026-08-18",profit_yoy=15.0,revenue_yoy=12.0),
        ],"600519","2026-11-20")

        accel=record["quarterly_acceleration"]
        self.assertEqual(accel["status"],"VERIFIED")
        self.assertEqual(accel["deduct_profit_acceleration_pp"],27.0)
        self.assertEqual(accel["revenue_acceleration_pp"],6.0)
        self.assertEqual(accel["revenue_alignment"],"ALIGNED_ACCELERATION")
        self.assertEqual(len(record["quarterly_history"]),2)

    def test_rejects_non_adjacent_previous_report_period(self):
        record=find_asof_row([
            row("2026-09-30","2026-10-31",profit_yoy=42.0,revenue_yoy=18.0),
            row("2026-03-31","2026-04-30",profit_yoy=10.0,revenue_yoy=8.0),
        ],"600519","2026-11-20")
        accel=record["quarterly_acceleration"]
        self.assertEqual(accel["status"],"UNKNOWN")
        self.assertEqual(
            accel["reason"],
            "PREVIOUS_QUARTER_REPORT_MISSING_OR_NOT_ADJACENT",
        )

    def test_ignores_future_updated_restatement(self):
        record=find_asof_row([
            row("2026-09-30","2026-10-31",update="2026-12-01",
                profit_yoy=999.0,revenue_yoy=999.0),
            row("2026-09-30","2026-10-31",update="2026-10-31",
                profit_yoy=42.0,revenue_yoy=18.0),
            row("2026-06-30","2026-08-18",profit_yoy=15.0,revenue_yoy=12.0),
        ],"600519","2026-11-20")
        self.assertEqual(
            record["quarterly_acceleration"]["deduct_profit_acceleration_pp"],
            27.0,
        )

    def test_missing_revenue_growth_keeps_acceleration_unknown(self):
        record=find_asof_row([
            row("2026-09-30","2026-10-31",profit_yoy=42.0,revenue_yoy=None),
            row("2026-06-30","2026-08-18",profit_yoy=15.0,revenue_yoy=12.0),
        ],"600519","2026-11-20")
        accel=record["quarterly_acceleration"]
        self.assertEqual(accel["status"],"UNKNOWN")
        self.assertIn("latest_single_quarter_revenue_yoy_pct",accel["missing_fields"])

    def test_shadow_score_activates_only_with_sufficient_peer_coverage(self):
        rows=[]
        for i,profit_accel in enumerate((5.0,15.0,25.0,35.0)):
            rows.append({
                "code":f"6005{i:02d}",
                "quarterly_acceleration":{
                    "status":"VERIFIED",
                    "deduct_profit_acceleration_pp":profit_accel,
                    "latest_single_quarter_deduct_profit_yoy_pct":30.0,
                    "latest_single_quarter_revenue_yoy_pct":12.0,
                    "revenue_acceleration_pp":4.0,
                    "revenue_alignment":"ALIGNED_ACCELERATION",
                },
            })
        base=[(.5,.5,.5,.5,.5,False) for _ in rows]
        shadow,audit=quarterly_acceleration_shadow_scores(rows,base)
        self.assertTrue(audit["activated"])
        self.assertEqual(audit["available_count"],4)
        self.assertGreater(shadow[-1][0],shadow[0][0])

    def test_shadow_score_does_not_activate_below_coverage_threshold(self):
        rows=[
            {"code":"600001","quarterly_acceleration":{
                "status":"VERIFIED","deduct_profit_acceleration_pp":10.0,
                "latest_single_quarter_deduct_profit_yoy_pct":20.0,
                "latest_single_quarter_revenue_yoy_pct":10.0,
                "revenue_acceleration_pp":2.0,
            }},
            {"code":"600002","quarterly_acceleration":{"status":"UNKNOWN"}},
            {"code":"600003","quarterly_acceleration":{"status":"UNKNOWN"}},
            {"code":"600004","quarterly_acceleration":{"status":"UNKNOWN"}},
        ]
        base=[(.5,.5,.5,.5,.5,False) for _ in rows]
        shadow,audit=quarterly_acceleration_shadow_scores(rows,base)
        self.assertFalse(audit["activated"])
        self.assertEqual(audit["reason"],"INSUFFICIENT_FINANCIAL_ACCELERATION_COVERAGE")
        self.assertEqual(shadow,base)

    def test_future_notice_is_not_used(self):
        record=find_asof_row([
            row("2026-09-30","2026-11-25",profit_yoy=42.0,revenue_yoy=18.0),
            row("2026-06-30","2026-08-18",profit_yoy=15.0,revenue_yoy=12.0),
        ],"600519","2026-11-20")
        self.assertEqual(record["report_date"],"2026-06-30")
        self.assertEqual(record["quarterly_acceleration"]["status"],"UNKNOWN")


if __name__=="__main__":
    unittest.main()
