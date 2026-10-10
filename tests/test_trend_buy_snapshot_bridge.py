"""Single-version intraday reader requires valid V2 result and exact SHA."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import build_intraday_snapshot as snap


def fixtures():
    row={"rank":1,"code":"600001","trade_date":"2026-10-09","status":"READY",
         "wait_reason":None,"setup_type":"BREAKOUT","entry_zone":[20.1,20.4],
         "max_entry_price":20.4,"invalidation_price":19.6,"invalidation_rule":"confirmed failure",
         "entry_trigger":"breakout close and volume confirmed","initial_risk_pct":4,
         "exit_plan":{"failed_setup":"exit"}}
    formal={"schema_version":"trend_buy_result_v2","status":"COMPLETE",
            "production_eligible":True,"run_id":"formal-20261009","trade_date":"2026-10-09",
            "ready":[row],"wait":[]}
    handoff={"schema_version":"trend_buy_handoff_v2","status":"COMPLETE",
             "shadow":False,"source_run_id":"formal-20261009","source_formal_blob_sha":None,
             "trade_date":"2026-10-09","items":[row]}
    return formal,handoff


class SingleVersionReaderTests(unittest.TestCase):
    def setup_files(self,folder):
        formal,handoff=fixtures()
        fp=Path(folder)/"trend_buy_formal_result.json"
        hp=Path(folder)/"trend_buy_handoff.json"
        payload=json.dumps(formal,ensure_ascii=False).encode()
        fp.write_bytes(payload)
        handoff["source_formal_blob_sha"]=hashlib.sha1(b"blob "+str(len(payload)).encode()+b"\0"+payload).hexdigest()
        hp.write_text(json.dumps(handoff,ensure_ascii=False))
        return fp,hp

    def test_only_promoted_v2_can_be_read(self):
        with tempfile.TemporaryDirectory() as t:
            fp,hp=self.setup_files(t)
            with patch.object(snap,"TREND_BUY_FORMAL_PATH",fp),patch.object(snap,"TREND_BUY_PATH",hp):
                _,rows,kind=snap.active_stock_handoff()
            self.assertEqual(kind,"trend_buy_v2")
            self.assertEqual(rows[0]["entry_zone"],[20.1,20.4])
            self.assertNotIn("low_risk_buy_range",rows[0])

    def test_missing_new_handoff_never_uses_old_data(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"absent.json"
            with patch.object(snap,"TREND_BUY_PATH",p):
                with self.assertRaises(FileNotFoundError):
                    snap.active_stock_handoff()

    def test_unready_migration_baseline_blocks_execution(self):
        with tempfile.TemporaryDirectory() as t:
            _,hp=self.setup_files(t)
            x=json.loads(hp.read_text())
            x["status"]="BASELINE_UNAVAILABLE"
            x["source_run_id"]=None
            hp.write_text(json.dumps(x))
            with patch.object(snap,"TREND_BUY_PATH",hp):
                with self.assertRaisesRegex(ValueError,"NO_VALID_TREND_BUY_HANDOFF"):
                    snap.active_stock_handoff()

    def test_formal_readback_mismatch_blocks_execution(self):
        with tempfile.TemporaryDirectory() as t:
            fp,hp=self.setup_files(t)
            data=json.loads(fp.read_text())
            data["trade_date"]="2026-10-08"
            fp.write_text(json.dumps(data))
            with patch.object(snap,"TREND_BUY_FORMAL_PATH",fp),patch.object(snap,"TREND_BUY_PATH",hp):
                with self.assertRaisesRegex(ValueError,"MISMATCH"):
                    snap.active_stock_handoff()

    def test_hand_off_must_match_formal_prices(self):
        with tempfile.TemporaryDirectory() as t:
            fp,hp=self.setup_files(t)
            data=json.loads(hp.read_text())
            data["items"][0]["entry_zone"]=[20.2,20.4]
            hp.write_text(json.dumps(data))
            with patch.object(snap,"TREND_BUY_FORMAL_PATH",fp),patch.object(snap,"TREND_BUY_PATH",hp):
                with self.assertRaisesRegex(ValueError,"ITEM_MISMATCH"):
                    snap.active_stock_handoff()


if __name__=="__main__":
    unittest.main()
