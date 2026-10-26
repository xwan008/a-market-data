"""No-network regression for keyed, code-first concept member catalog."""
import importlib.util
import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import fetch_concept_memberships_fuyao as adapter

DAY="2026-10-26"
STAMP=int(datetime(2026,10,26,16,0,tzinfo=ZoneInfo("Asia/Shanghai")).timestamp()*1000)


class Response:
    def __init__(self,payload):self.payload=payload
    def raise_for_status(self):pass
    def json(self):return self.payload


class FakeSession:
    def __init__(self,one=None,bad_timestamp=False):
        self.calls=[]
        self.one=one if one is not None else ["000001","300001"]
        self.bad_timestamp=bad_timestamp
    def get(self,url,params=None,headers=None,timeout=None):
        assert headers["X-api-key"]=="TEST-KEY"
        self.calls.append((url,params))
        stamp=STAMP-86400000 if self.bad_timestamp else STAMP
        if "ths-index-list" in url:
            items=[{"thscode":f"{880000+i:06d}.TI","name":f"无关概念{i}"}
                   for i in range(100)]
            items.append({"thscode":"886069.TI","name":"人形机器人"})
            return Response({"code":0,"data":{"timestamp":stamp,"item":items}})
        assert params=={"thscode":"886069.TI"}
        return Response({"code":0,"data":{
            "timestamp":stamp,"item":[{"ticker":x,"thscode":x+".SZ"}
                                       for x in self.one]}})


class SourceAdapterTest(unittest.TestCase):
    def handoff(self):
        return {"trade_date":DAY,
                "signals":[{"trend_name":"工业自动化/机器人"}]}

    def test_catalog_matches_real_index_names_not_unrelated_names(self):
        session=FakeSession()
        res=adapter.build(self.handoff(),"TEST-KEY",session=session,
                          observed_trade_date=DAY)
        self.assertEqual(res["source"],"THS_FUYAO")
        self.assertEqual(res["catalog_scope"],"MATCHED_HOTSPOT_CONCEPTS_COMPLETE")
        self.assertEqual(res["concepts"][0]["concept_id"],"886069.TI")
        self.assertEqual(res["concepts"][0]["member_codes"],["000001","300001"])
        self.assertEqual(len(session.calls),2)

    def test_missing_provider_data_cannot_be_claimed_complete(self):
        for data in ([],["000001","000001"]):
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    adapter.build(self.handoff(),"TEST-KEY",FakeSession(data),
                                  observed_trade_date=DAY)

    def test_provider_response_from_wrong_day_rejected(self):
        with self.assertRaisesRegex(ValueError,"NOT_CURRENT_SESSION"):
            adapter.build(self.handoff(),"TEST-KEY",FakeSession(bad_timestamp=True),
                          observed_trade_date=DAY)

    def test_historical_replay_from_current_source_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"CANNOT_REPLAY_HISTORICAL"):
            adapter.build(self.handoff(),"TEST-KEY",FakeSession(),
                          observed_trade_date="2026-10-27")


if __name__=="__main__":
    unittest.main()
