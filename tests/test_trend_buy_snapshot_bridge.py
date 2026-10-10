"""Only the promoted trend V2 handoff is a valid intraday entry source."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import build_intraday_snapshot as snap


def ready_payload():
    return {"schema_version":"trend_buy_handoff_v2","status":"COMPLETE",
        "shadow":False,"source_run_id":"run-20261009","source_formal_blob_sha":"verifiedsha",
        "trade_date":"2026-10-09",
        "items":[{"rank":1,"code":"600001","trade_date":"2026-10-09","status":"READY",
                  "wait_reason":None,"setup_type":"BREAKOUT","entry_zone":[20.1,20.4],
                  "max_entry_price":20.4,"invalidation_price":19.6,"invalidation_rule":"confirmed failure",
                  "entry_trigger":"breakout close and volume confirmed","initial_risk_pct":4,
                  "exit_plan":{"failed_setup":"exit"}}]}


class SoleHandoffTests(unittest.TestCase):
    def test_v2_handoff_is_the_only_accepted_format(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"trend_buy_handoff.json"
            p.write_text(json.dumps(ready_payload()))
            with patch.object(snap,"TREND_BUY_PATH",p):
                h,rows,kind=snap.active_stock_handoff()
            self.assertEqual(kind,"trend_buy_v2")
            self.assertEqual(rows[0]["entry_zone"],[20.1,20.4])
            self.assertNotIn("reasonable_buy_range",rows[0])

    def test_missing_v2_does_not_fallback_to_legacy(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"trend_buy_handoff.json"
            with patch.object(snap,"TREND_BUY_PATH",p):
                with self.assertRaises(FileNotFoundError):
                    snap.active_stock_handoff()

    def test_shadow_result_must_not_enter_intraday(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"trend_buy_handoff.json"
            x=ready_payload()
            x["shadow"]=True
            p.write_text(json.dumps(x))
            with patch.object(snap,"TREND_BUY_PATH",p):
                with self.assertRaisesRegex(ValueError,"not_production"):
                    snap.active_stock_handoff()

    def test_legacy_state_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"trend_buy_handoff.json"
            p.write_text(json.dumps({"status":"COMPLETE","trade_date":"2026-10-09",
                                     "items":[{"code":"600001","wait_reason":"WAIT_PRICE","status":"WAIT"}]}))
            with patch.object(snap,"TREND_BUY_PATH",p):
                with self.assertRaisesRegex(ValueError,"not_production"):
                    snap.active_stock_handoff()


if __name__=="__main__":
    unittest.main()
