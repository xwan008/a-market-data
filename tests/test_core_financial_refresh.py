"""Point-in-time and no-price-write regressions for weekly financial repair."""
from pathlib import Path
import importlib.util
from unittest.mock import patch
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location(
    "core_finance",ROOT/"scripts/refresh_core_financial_only.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
ASOF="2026-11-05"


def row(period,notice,updated=None,core=100,yoy=25,parent=140):
    return {"SECURITY_CODE":"000506","SECUCODE":"000506.SZ",
            "REPORT_DATE":period,"NOTICE_DATE":notice,
            "UPDATE_DATE":updated or notice,
            "KCFJCXSYJLR":core,"KCFJCXSYJLRTZ":yoy,
            "PARENTNETPROFIT":parent}


class CoreProfitTests(unittest.TestCase):
    def test_batch_code_syntax_prevents_bad_codes(self):
        self.assertEqual(m.secu_code("000506"),"000506.SZ")
        self.assertEqual(m.secu_code("600547"),"600547.SH")
        with self.assertRaisesRegex(ValueError,"invalid_ashare_stock_code"):
            m.secu_code("00);drop table")

    def test_future_disclosure_or_revision_cannot_backfill_history(self):
        sample=[
            row("2026-09-30","2026-11-06",core=999),
            row("2026-09-30","2026-10-27","2026-11-06",core=999),
            row("2026-06-30","2026-08-20",core=90,yoy=10),
        ]
        result=m.find_asof_row(sample,"000506",ASOF)
        self.assertEqual(result["report_date"],"2026-06-30")
        self.assertEqual(result["deduct_net_profit"],90)
        self.assertEqual(result["deduct_net_profit_yoy"],10)

    def test_realistic_core_profit_and_noncore_ratio(self):
        sample=[row("2026-09-30","2026-10-27",
                    core=115251654.93,parent=234611745.19,yoy=127.188379)]
        result=m.find_asof_row(sample,"000506",ASOF)
        self.assertEqual(result["deduct_net_profit"],115251654.93)
        self.assertAlmostEqual(result["nonrecurring_profit_share_pct"],50.8756,places=2)
        self.assertEqual(result["notice_date"],"2026-10-27")

    def test_unknown_evidence_stays_unknown(self):
        self.assertIsNone(m.find_asof_row(
            [row("2026-09-30",None,core=None,yoy=None)],"000506",ASOF))
        self.assertIsNone(m.find_asof_row(
            [row("2026-09-30","2026-11-08")],"000506",ASOF))

    def test_only_matching_reporting_period_adds_core_fields(self):
        base={"trade_date":ASOF,"fundamental_stats":{"financial_usable":3},
              "stocks":{
                "000506":{"price":3.5,"fundamentals":{
                    "report_date":"2026-09-30","net_profit_yoy":185.55}},
                "600547":{"price":35.1,"fundamentals":{
                    "report_date":"2026-09-30","deduct_net_profit_yoy":12}},
                "002517":{"price":17.1,"fundamentals":{
                    "report_date":"2026-09-30","net_profit_yoy":10}},
              }}
        records={
            "000506":m.find_asof_row(
                 [row("2026-09-30","2026-10-27")],"000506",ASOF),
            "600547":{
                "report_date":"2026-09-30","notice_date":"2026-10-30",
                "update_date":"2026-10-30","deduct_net_profit_yoy":75,
                "deduct_net_profit":17,"deduct_basic_eps":None,
                "nonrecurring_profit_share_pct":0},
            "002517":{
                "report_date":"2026-06-30","notice_date":"2026-08-25",
                "update_date":"2026-08-25","deduct_net_profit_yoy":-5,
                "deduct_net_profit":22,"deduct_basic_eps":None,
                "nonrecurring_profit_share_pct":0},
        }
        updated,detail=m.apply_to_copy(base,records)
        self.assertEqual(base["stocks"]["000506"]["fundamentals"].get("deduct_net_profit_yoy"),None)
        self.assertEqual(updated["stocks"]["000506"]["price"],3.5)
        self.assertEqual(updated["stocks"]["000506"]["fundamentals"]["deduct_net_profit_yoy"],25)
        self.assertEqual(updated["stocks"]["600547"]["fundamentals"]["deduct_net_profit_yoy"],12)
        self.assertEqual(updated["stocks"]["002517"]["fundamentals"].get("deduct_net_profit_yoy"),None)
        self.assertEqual(updated["fundamental_stats"]["deduct_profit_growth_usable"],2)
        self.assertEqual(len(detail["report_date_mismatches"]),1)

    def test_no_zero_from_missing_evidence(self):
        r=m.find_asof_row([
          row("2026-09-30","2026-10-30",core=None,yoy=None,parent=140)],
          "000506",ASOF)
        self.assertIsNone(r)

    def test_batch_endpoint_is_explicitly_limited_to_public_codes(self):
        class Resp:
            def raise_for_status(self):return None
            def json(self):
                return {"success":True,"result":{"data":[
                    row("2026-09-30","2026-10-27")]}}
        with patch.object(m.requests,"get",return_value=Resp()) as get:
            x=m.query_batch(["000506"],attempts=1)
            self.assertEqual(len(x),1)
            filt=get.call_args.kwargs["params"]["filter"]
            self.assertIn('SECUCODE in ("000506.SZ")',filt)

if __name__=="__main__":
    unittest.main()
