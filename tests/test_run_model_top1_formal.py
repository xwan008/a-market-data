import copy
import unittest
from unittest.mock import patch
import test_research_model_top1 as fixture
from scripts import run_model_top1_formal as formal, trend_buy_handoff as handoff

class FormalTop1Tests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.ModelTop1Test()
        self.f.setUp()
        f=self.f
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
        self.assertTrue(result["production_eligible"])
        self.assertEqual(result["coverage"]["selected"],5)
        self.assertEqual(result["coverage"]["judged"],1)
        self.assertEqual(result["summary"]["wait"],1)
        h=handoff.project(result,"synthetic-sha")
        self.assertEqual([x["code"] for x in h["items"]],["601328"])
        self.assertIsNone(h["items"][0]["entry_zone"])
        self.assertEqual(h["items"][0]["attention_rank"],1)

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
