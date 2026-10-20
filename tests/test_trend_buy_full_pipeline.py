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

builder=module("build_trend_buy_manual_research.py","trend_buy_builder")


class FreshReviewScopeTests(unittest.TestCase):
    def setUp(self):
        self.evidence={"reviews":[
            {"code":"A","transmission":"SUPPORTED"},
            {"code":"B","transmission":"EARLY_EVIDENCE"},
            {"code":"C","transmission":"NOT_SUPPORTED"}]}
        self.research={"companies":[{"code":"A"},{"code":"B"}],
                       "screen_audit":{
                           "research_replacements":["C"],
                           "pre_screened_out":[{"code":"C","reason":"THEME_NOT_SUPPORTED"}]}}

    def test_rejected_review_justifies_replacement_without_filling_slot(self):
        builder.validate_fresh_review_scope(self.evidence,self.research)

    def test_selected_company_without_review_blocks(self):
        self.evidence["reviews"]=[row for row in self.evidence["reviews"] if row["code"]!="B"]
        with self.assertRaisesRegex(ValueError,"RESEARCH_SELECTED_REVIEW_MISSING"):
            builder.validate_fresh_review_scope(self.evidence,self.research)

    def test_unaudited_extra_review_blocks(self):
        self.evidence["reviews"].append({"code":"D","transmission":"SUPPORTED"})
        with self.assertRaisesRegex(ValueError,"RESEARCH_NEGATIVE_REPLACEMENT_AUDIT_MISMATCH"):
            builder.validate_fresh_review_scope(self.evidence,self.research)

    def test_extra_review_must_be_explicitly_negative(self):
        self.evidence["reviews"][-1]["transmission"]="SUPPORTED"
        with self.assertRaisesRegex(ValueError,"RESEARCH_EXTRA_REVIEW_NOT_NEGATIVE"):
            builder.validate_fresh_review_scope(self.evidence,self.research)

    def test_rejection_requires_matching_prescreen_audit(self):
        self.research["screen_audit"]["pre_screened_out"]=[]
        with self.assertRaisesRegex(ValueError,"RESEARCH_NEGATIVE_REPLACEMENT_AUDIT_MISMATCH"):
            builder.validate_fresh_review_scope(self.evidence,self.research)

    def test_rejected_company_cannot_be_selected(self):
        self.evidence["reviews"][0]["transmission"]="NOT_SUPPORTED"
        with self.assertRaisesRegex(ValueError,"RESEARCH_REJECTED_COMPANY_SELECTED"):
            builder.validate_fresh_review_scope(self.evidence,self.research)

    def test_duplicate_company_review_blocks(self):
        self.evidence["reviews"].append(dict(self.evidence["reviews"][0]))
        with self.assertRaisesRegex(ValueError,"RESEARCH_DUPLICATE_REVIEW"):
            builder.validate_fresh_review_scope(self.evidence,self.research)




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
        self.assertEqual(result["top5_by_theme"][0]["items"][0]["attention_rank"],1)
        self.assertEqual(published["items"][0]["attention_rank"],1)
        self.assertTrue(published["items"][0]["attention_judgement"])
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
