import unittest
import datetime as dt
from unittest.mock import patch
import sys
sys.path.insert(0,"scripts")
import intraday_focus_trial as f

class FocusTests(unittest.TestCase):
    def test_isolate_bad_holding(self):
        def row(code,q,status="持仓中"):
            return {"fields":{"股票代码":code,"持仓股数":q,"数据状态":"用户已确认","持仓状态":status}}
        good,bad=f.confirmed_positions([row("601328",100),row("002643",None),row("600000",0,"已清仓")])
        self.assertEqual(good,["sh601328"])
        self.assertEqual(bad,1)
    def test_duplicate_isolated(self):
        def row(code):
            return {"fields":{"股票代码":code,"持仓股数":100,"数据状态":"用户已确认","持仓状态":"持仓中"}}
        self.assertEqual(f.confirmed_positions([row("601328"),row("601328"),row("000001")]),(["sz000001"],1))
    def test_source_failure(self):
        def broken(): raise OSError("private data")
        self.assertEqual(f.wrapped(broken),{"status":"failed","error":"OSError"})
    def test_missing_metrics(self):
        self.assertIsNone(f.metrics({})["same_time_volume_ratio"])
    def test_collection_isolates(self):
        def bad(): raise ValueError("SOURCE_FAILED")
        with patch.object(f,"component_calls",lambda s:{"good":lambda:{"symbol":s},"bad":bad}):
            rows=f.collect(["sh601328","sz000001"])
        self.assertEqual(len(rows),2)
        self.assertEqual(rows["sh601328"]["components"]["bad"]["status"],"failed")
        self.assertEqual(rows["sz000001"]["components"]["good"]["status"],"ok")
    def test_private_transport_integrity(self):
        from focus_private_transport import encode,verify,row
        import json
        payload={"run_id":"123-1","trade_date":"2026-11-27","points":["数据"]*25000}
        text,digest,parts=encode(payload)
        manifest={"run_id":"123-1","trade_date":"2026-11-27","part_count":len(parts),"sha256":digest}
        rows={f"{i:04d}":row("key","123-1","2026-11-27",f"{i:04d}",part,digest)["fields"] for i,part in enumerate(parts)}
        rows["manifest"]=row("key","123-1","2026-11-27","manifest",json.dumps(manifest),digest)["fields"]
        self.assertEqual(verify(rows,"123-1")[0],payload)
        rows["0000"]["内容"]="corrupt"
        with self.assertRaises(ValueError): verify(rows,"123-1")
if __name__=="__main__": unittest.main()
