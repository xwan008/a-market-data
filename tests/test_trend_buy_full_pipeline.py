"""The sole production V2 pipeline is publishable only after its explicit gates."""
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def module(path,name):
    spec=importlib.util.spec_from_file_location(name,ROOT/"scripts"/path)
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

engine=module("trend_buy_engine.py","trend_engine")
handoff=module("trend_buy_handoff.py","trend_handoff")


def fixture():
    audit={x:True for x in ("fresh_company_research","working_set_frozen",
            "pre_screen_coverage","company_research_coverage",
            "structure_same_day","no_future_evidence","json_schema_valid")}
    research={"schema_version":"trend_buy_research_v2","trade_date":"2026-10-09",
       "mode":"FORMAL","run_id":"2026-10-09T19-00-test","coverage_complete":True,
       "selected_company_count":1,"publication_audit":audit,
       "companies":[{"code":"600001","company_name":"纯虚构测试股票","industry_code":"S000000",
          "industry_name":"纯测试","asof_price":20.2,
          "trend_name":"测试趋势","market_state":"趋势确认","trend_state":"T1","filter_passed":True,"theme_link_verified":True,
          "transmission":"SUPPORTED","source_review":"2026-10-09 synthetic proof",
          "research_falsifier":"商业传导被证伪"}]}
    structure={"contract_id":"a-share-low-risk-price-structure",
       "reference_trade_date":"2026-10-09",
       "companies":{"600001":{
           "data_status":"verified","data_date":"2026-10-09","history_points":180,
           "low_risk_eligible":True,"current_price":20.2,"ma20":19.8,
           "ma60":19.2,"support_invalidation":19.55,
           "prior_60d_high":20.0,"breakout_level":20.0,
           "breakout_confirmed":True,"structure_type":"breakout",
           "chase_risk":"low","distance_to_ma20_pct":2,
           "first_effective_resistance":None}}}
    return research,structure


class SingleVersionContractTests(unittest.TestCase):
    def test_formal_generates_only_v2_handoff(self):
        r,s=fixture()
        result=engine.generate(r,s)
        self.assertTrue(result["production_eligible"])
        self.assertEqual(result["summary"]["ready"],1)
        blob=(json.dumps(result,ensure_ascii=False,indent=2)+"\n").encode()
        sha=hashlib.sha1(b"blob "+str(len(blob)).encode()+b"\0"+blob).hexdigest()
        published=handoff.project(result,sha,shadow=False)
        self.assertEqual(published["schema_version"],"trend_buy_handoff_v2")
        self.assertEqual(published["source_formal_blob_sha"],sha)
        self.assertTrue(set(published["items"][0]).issubset(handoff.ALLOWED_ITEM_FIELDS))
        self.assertEqual(published["items"][0]["max_entry_price"],result["ready"][0]["max_entry_price"])

    def test_formal_missing_one_gate_fails_closed(self):
        r,s=fixture()
        r["publication_audit"]["fresh_company_research"]=False
        with self.assertRaisesRegex(ValueError,"formal_publication_gate"):
            engine.generate(r,s)

    def test_formal_refuses_unreviewed_company(self):
        r,s=fixture()
        r["companies"][0]["source_review"]=""
        with self.assertRaisesRegex(ValueError,"formal_company_research_missing"):
            engine.generate(r,s)

    def test_historical_shadows_cannot_be_promoted(self):
        r,s=fixture()
        r["mode"]="SHADOW_HISTORICAL"
        result=engine.generate(r,s)
        self.assertFalse(result["production_eligible"])
        with self.assertRaisesRegex(ValueError,"not_promoted"):
            handoff.project(result,"testsha",shadow=False)


if __name__=="__main__":
    unittest.main()
