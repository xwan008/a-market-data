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
    def test_slot_window(self):
        self.assertEqual(f.planned_slot(dt.datetime(2026,11,30,9,37,30,tzinfo=f.p.TZ)).strftime("%H:%M"),"09:37")
        self.assertIsNone(f.planned_slot(dt.datetime(2026,11,30,9,40,tzinfo=f.p.TZ)))
        self.assertIsNone(f.planned_slot(dt.datetime(2026,12,5,9,37,tzinfo=f.p.TZ)))
        self.assertIsNone(f.planned_slot(dt.datetime(2027,1,4,9,37,tzinfo=f.p.TZ)))
        self.assertEqual(f.previous_session(dt.date(2026,11,30)),"2026-11-27")
    def test_no_live_quote(self):
        self.assertEqual(f.stock_gate({"components":{}},"2026-11-27"),"QUOTE_UNAVAILABLE")
    def test_board_normalization_unique(self):
        row={"components":{"east_quote":{"status":"ok","data":{"provider_industry":"银行Ⅱ"}}}}
        out=f.related_board("sh601328",row,{"银行":{"name":"银行"}},{},{"sh601328":"国有大型银行Ⅲ"})
        self.assertEqual(out["status"],"ok")
        self.assertEqual(out["data"]["name"],"银行")
        fallback=f.related_board("sh601328",row,{},{"sz399986":{"status":"ok","data":{"name":"中证银行"}}},{})
        self.assertEqual(fallback["status"],"PROXY_ONLY")
        self.assertEqual(fallback["data"]["name"],"中证银行")
        ambiguous=f.related_board("sh601328",row,{"银行Ⅰ":{},"银行Ⅲ":{}},{},{})
        self.assertEqual(ambiguous["status"],"UNRESOLVED")
if __name__=="__main__": unittest.main()
