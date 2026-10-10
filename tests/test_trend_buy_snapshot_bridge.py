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
         "wait_reason":None,"market_state":"趋势确认","trend_state":"T1","setup_type":"BREAKOUT","entry_zone":[20.1,20.4],
         "max_entry_price":20.4,"invalidation_price":19.6,"invalidation_rule":"confirmed failure",
         "entry_trigger":"breakout close and volume confirmed","initial_risk_pct":4,
         "exit_plan":{"failed_setup":"exit"}}
    formal={"schema_version":"trend_buy_result_v2","status":"COMPLETE",
            "production_eligible":True,"run_id":"formal-20261009","trade_date":"2026-10-09",
            "ready":[row],"wait":[],
            "top5_by_theme":[{"trend_name":"示例","items":[{"code":"600001"}]}]}
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
            self.assertEqual(rows[0]["setup_type"],"BREAKOUT")

    def test_handoff_is_dynamic_top5_not_all_researched_wait(self):
        with tempfile.TemporaryDirectory() as t:
            fp,hp=self.setup_files(t)
            formal=json.loads(fp.read_text())
            wait_row={**formal["ready"][0], "code":"600002", "rank":2,
                      "status":"WAIT","wait_reason":"WAIT_CONFIRMATION",
                      "entry_zone":None,"max_entry_price":None,
                      "invalidation_price":None,"setup_type":None}
            formal["wait"].append(wait_row)
            payload=json.dumps(formal,ensure_ascii=False).encode()
            fp.write_bytes(payload)
            h=json.loads(hp.read_text())
            h["source_formal_blob_sha"]=hashlib.sha1(
                b"blob "+str(len(payload)).encode()+b"\0"+payload).hexdigest()
            hp.write_text(json.dumps(h,ensure_ascii=False))
            with patch.object(snap,"TREND_BUY_FORMAL_PATH",fp),patch.object(snap,"TREND_BUY_PATH",hp):
                _,items,_=snap.active_stock_handoff()
            self.assertEqual([r["code"] for r in items],["600001"])

    def test_formal_without_dynamic_top5_is_not_current_main_flow(self):
        with tempfile.TemporaryDirectory() as t:
            fp,hp=self.setup_files(t)
            formal=json.loads(fp.read_text())
            del formal["top5_by_theme"]
            payload=json.dumps(formal,ensure_ascii=False).encode()
            fp.write_bytes(payload)
            h=json.loads(hp.read_text())
            h["source_formal_blob_sha"]=hashlib.sha1(
                b"blob "+str(len(payload)).encode()+b"\0"+payload).hexdigest()
            hp.write_text(json.dumps(h,ensure_ascii=False))
            with patch.object(snap,"TREND_BUY_FORMAL_PATH",fp),patch.object(snap,"TREND_BUY_PATH",hp):
                with self.assertRaisesRegex(ValueError,"DYNAMIC_TOP5_MISSING"):
                    snap.active_stock_handoff()

    def test_missing_handoff_prevents_execution(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"absent.json"
            with patch.object(snap,"TREND_BUY_PATH",p):
                with self.assertRaises(FileNotFoundError):
                    snap.active_stock_handoff()

    def test_unavailable_baseline_blocks_execution(self):
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
