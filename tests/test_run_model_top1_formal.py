import copy
import json
import unittest
from unittest.mock import patch
import test_research_model_top1 as fixture
from scripts import run_model_top1_formal as formal, trend_buy_handoff as handoff

class FormalTop1Tests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.ModelTop1Test()
        self.f.setUp()
        f=self.f
        dates=["2026-11-18","2026-11-19","2026-11-20","2026-11-23",f.day]
        stamp=f.day+"T19:00:00+08:00"
        industry=f.pick["industry_code"]
        stocks={}
        for code in f.codes:
            rows=[{"date":d,"main_net_cny":1,"amount_cny":100} for d in dates]
            stocks[code]={"code":code,"provider":"tencent","trade_date":f.day,"queried_at":stamp,
                          "sources":["https://example.com/synthetic"],"daily":rows,"windows":formal.funds.metrics(rows)}
            f.pick["research_matrix"][code]["A"]["frozen_fund_ref"]="fund_flow.groups/"+industry+"/stocks/"+code
        f.admission["fund_flow"]={"trade_date":f.day,"collected_at":stamp,"groups":[{
            "industry_code":industry,"candidate_codes":f.codes,"status":"VERIFIED","provider":"tencent",
            "definition":formal.funds.DEFINITIONS["tencent"],"stocks":stocks,
            "attempts":[{"provider":"tencent","queried_at":stamp,"errors":{}}]}]}
        f.raw=json.dumps(f.admission).encode()
        f.selections["source_blob"]=formal.model.git_blob_sha(f.raw)
        for c in f.research["companies"]:
            c.update(trend_name="银行",industry_name="国有大型银行Ⅲ",company_name=c["code"])
        self.evidence={"as_of_date":f.day,"explicit_no_prior_formal_or_archive_input":True,
                       "reviews":[{"code":c,"review_evidence_date":f.day,
                                   "transmission":"SUPPORTED","source_review":"synthetic",
                                   "review_basis":"synthetic"} for c in f.codes],
                       "top1_selection":f.selections}
    def run_formal(self):
        f=self.f
        return formal.generate(f.raw,f.research,f.structure,self.evidence,"synthetic-run")

    def test_wait_only_top1_and_roster_retained(self):
        with patch.object(formal.engine,"evaluate_candidate",wraps=formal.engine.evaluate_candidate) as evaluate:
            result=self.run_formal()
        self.assertEqual(evaluate.call_count,1)
        self.assertEqual(result["python_top5_by_industry"][0]["selected_codes"],self.f.codes)
        self.assertEqual(result["selection_policy"],formal.POLICY)
        self.assertNotIn("top5_by_theme",result)
        self.assertEqual(result["top1_by_industry"][0]["items"][0]["code"],"601328")
        self.assertEqual(len(result["company_reviews"]),5)
        self.assertTrue(result["production_eligible"])
        self.assertEqual(result["coverage"]["selected"],5)
        self.assertEqual(result["coverage"]["judged"],1)
        self.assertEqual(result["summary"]["wait"],1)
        h=handoff.project(result,"synthetic-sha")
        self.assertEqual([x["code"] for x in h["items"]],["601328"])
        self.assertEqual(h["selection_policy"],formal.POLICY)
        self.assertIsNone(h["items"][0]["entry_zone"])
        self.assertEqual(h["items"][0]["attention_rank"],1)

    def test_fund_missing_blocks_complete_before_risk(self):
        del self.f.admission["fund_flow"]
        self.f.raw=json.dumps(self.f.admission).encode()
        self.f.selections["source_blob"]=formal.model.git_blob_sha(self.f.raw)
        with patch.object(formal.engine,"evaluate_candidate") as evaluate:
            with self.assertRaisesRegex(ValueError,"FUND_SNAPSHOT_REQUIRED"):
                self.run_formal()
            evaluate.assert_not_called()

    def test_abstention_empty_handoff(self):
        self.f.pick.update(status="INCOMPLETE",top1_code=None)
        with patch.object(formal.engine,"evaluate_candidate") as evaluate:
            result=self.run_formal()
        evaluate.assert_not_called()
        self.assertEqual(result["coverage"]["judged"],0)
        self.assertEqual(handoff.project(result,"synthetic-sha")["items"],[])

    def test_drop_uncertain_no_handoff(self):
        for status in ("DROP","UNCERTAIN"):
            with self.subTest(status=status), patch.object(formal.engine,"evaluate_candidate",
                    return_value={"code":"601328","status":status}):
                result=self.run_formal()
                self.assertEqual(handoff.project(result,"synthetic-sha")["items"],[])
                self.assertEqual(result["summary"][status.lower()],1)

    def test_reject_legacy_or_fake_extra_handoff(self):
        result=self.run_formal()
        result["top1_decisions"][0]["top1_code"]="601288"
        with self.assertRaises(ValueError):
            handoff.project(result,"synthetic-sha")
        self.evidence.pop("top1_selection")
        with self.assertRaises(KeyError):
            self.run_formal()

    def test_legacy_policy_blocked_for_all_publication_dates(self):
        result=self.run_formal()
        result["top5_by_theme"]=result.pop("top1_by_industry")
        result.pop("selection_policy")
        for day in ("2026-10-09", "2026-11-25", "2026-12-01"):
            with self.subTest(day=day):
                result["trade_date"]=day
                with self.assertRaisesRegex(ValueError,"LEGACY_TOP5_FORMAL_DISABLED"):
                    handoff.project(result,"synthetic-sha")
        with self.assertRaisesRegex(ValueError,"HISTORICAL_LEGACY_READBACK_ONLY"):
            handoff.replay_historical_projection(result,"synthetic-sha")

    def test_ambiguous_new_top5_field_rejected(self):
        result=self.run_formal()
        result["top5_by_theme"]=[]
        with self.assertRaisesRegex(ValueError,"AMBIGUOUS_LEGACY_TOP5_FIELD"):
            handoff.project(result,"synthetic-sha")

    def test_old_or_future_reviews_rejected(self):
        self.evidence["reviews"][0]["review_evidence_date"]="2026-11-23"
        with self.assertRaises(ValueError):
            self.run_formal()
        self.evidence["reviews"][0]["review_evidence_date"]=self.f.day
        self.evidence["reviews"][0]["source_materials"]=[{
            "asof":self.f.day,"published_at":"2026-11-25","url":"https://example.com"}]
        with self.assertRaises(ValueError):
            self.run_formal()

if __name__=="__main__":
    unittest.main()
