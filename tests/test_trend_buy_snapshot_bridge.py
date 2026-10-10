"""The intraday snapshot must not confuse V2 trend prices with old value ranges."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import build_intraday_snapshot as snap


class SnapshotBridgeTests(unittest.TestCase):
    def test_legacy_remains_active_until_formal_v2_handoff_exists(self):
        with tempfile.TemporaryDirectory() as t:
            legacy=Path(t)/"low_risk_handoff.json"
            trend=Path(t)/"trend_buy_handoff.json"
            legacy.write_text(json.dumps({"schema_version":1,"status":"COMPLETE","items":[
                {"code":"600001","status":"WAIT","wait_reason":"WAIT_PRICE"}]}))
            with patch.object(snap,"LOW_RISK_PATH",legacy),patch.object(snap,"TREND_BUY_PATH",trend):
                h,items,kind=snap.active_stock_handoff()
            self.assertEqual(kind,"low_risk_legacy")
            self.assertEqual(items[0]["wait_reason"],"WAIT_PRICE")

    def test_v2_preferred_over_legacy_only_when_committed_contract_is_valid(self):
        with tempfile.TemporaryDirectory() as t:
            legacy=Path(t)/"legacy.json"
            trend=Path(t)/"trend_buy_handoff.json"
            legacy.write_text(json.dumps({"status":"COMPLETE","items":[]}))
            item={"rank":1,"code":"600001","trade_date":"2026-10-09","status":"READY",
                  "wait_reason":None,"setup_type":"BREAKOUT","entry_zone":[20.1,20.4],
                  "max_entry_price":20.4,"invalidation_price":19.6,"invalidation_rule":"confirmed failure",
                  "entry_trigger":"breakout close and volume confirmed","initial_risk_pct":4,
                  "exit_plan":{"failed_setup":"exit"}}
            trend.write_text(json.dumps({"schema_version":"trend_buy_handoff_v2","status":"COMPLETE",
                  "shadow":False,"source_run_id":"run-20261009","source_formal_blob_sha":"verifiedsha",
                  "trade_date":"2026-10-09","items":[item]}))
            with patch.object(snap,"LOW_RISK_PATH",legacy),patch.object(snap,"TREND_BUY_PATH",trend):
                _,rows,kind=snap.active_stock_handoff()
            self.assertEqual(kind,"trend_buy_v2")
            self.assertEqual(rows[0]["entry_zone"],[20.1,20.4])
            self.assertNotIn("reasonable_buy_range",rows[0])

    def test_shadow_result_not_allowed_as_active_handoff(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"trend_buy_handoff.json"
            p.write_text(json.dumps({"schema_version":"trend_buy_handoff_v2","status":"COMPLETE","shadow":True,
                         "source_run_id":"test","source_formal_blob_sha":"sha","trade_date":"2026-10-09","items":[]}))
            with patch.object(snap,"TREND_BUY_PATH",p):
                with self.assertRaisesRegex(ValueError,"not_production"):
                    snap.active_stock_handoff()

if __name__=="__main__":
    unittest.main()
