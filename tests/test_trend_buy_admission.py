"""现行 can replace the program and model ranking only when both are real.

Previous company reviews cannot be silently reused for the canonical selection
because its 15 company slots differ from the same-day 现行 Python selection.
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import prepare_trend_buy_candidates as intake
import build_trend_buy_manual_research as builder
import trend_buy_engine as engine

def shape(code,priority,reason,phase="INITIATING"):
    return {
        "code":code,"company_name":code,"trend_name":"游戏",
        "status":"WAIT","wait_reason":"WAIT_CONFIRMATION",
        "transmission":"SUPPORTED","market_state":"趋势确认",
        "trend_phase":phase,"current_price":10.0,"data_date":"2026-11-05",
        "phase_evidence":{"fresh_break":True,"return_5d_pct":3.0,"positive_days_5d":4},
        "technical_context":{
            "ma20":9.8,"ma60":9.4,"volume_ratio_1d_vs_20d":1.5,
            "close_location_pct":80,"distance_to_ma20_pct":2,
            "relative_strength_20d_vs_market_pct":3},
        "model_priority":priority,"model_reason":reason,
    }


class CanonicalAdmissionTests(unittest.TestCase):
    def test_python_admission_is_current_replayable_and_five_max(self):
        a=intake.prepare(ROOT)
        mapping=intake.validate_admission(ROOT,a)
        self.assertEqual(a["trade_date"],"2026-11-05")
        self.assertEqual(len(mapping),3)
        self.assertEqual(a["selected_company_count"],15)
        self.assertTrue(all(len(codes)<=5 for codes in mapping.values()))
        self.assertEqual(mapping["S720401"],[
            "603258","002624","002605","002517","603444"])
        self.assertFalse(a["checks"]["model_invocations"])

    def test_admission_mutation_fails_closed(self):
        a=intake.prepare(ROOT)
        tampered=deepcopy(a)
        tampered["trade_date"]="2026-11-06"
        with self.assertRaisesRegex(ValueError,"ADMISSION"):
            intake.validate_admission(ROOT,tampered)
        tampered=deepcopy(a)
        tampered["industries"][0]["selected_codes"]+=["000001"]
        with self.assertRaisesRegex(ValueError,"ADMISSION"):
            intake.validate_admission(ROOT,tampered)
        tampered=deepcopy(a)
        tampered["source"]["finance_evidence_sha256"]="not_same_file"
        with self.assertRaisesRegex(ValueError,"ADMISSION"):
            intake.validate_admission(ROOT,tampered)

    def test_model_rank_changes_attention_but_not_trade_ready(self):
        first=shape("002517",2,"经营现金流持续改善，行业持续强势，但存在较高追高风险")
        second=shape("603444",1,"盈利质量较稳，当前价格结构需要等待回踩承接确认")
        research={"prescreen_version":"CANONICAL","trade_date":"2026-11-05",
                  "companies":[{"trend_name":"游戏"}]}
        group=engine.dynamic_top5_by_theme([], [first,second],research)
        self.assertEqual([x["code"] for x in group[0]["items"]],
                         ["603444","002517"])
        engine.add_attention_priorities(group,[],[first,second],research)
        self.assertTrue(group[0]["items"][0]["attention_judgement"].startswith(
            "模型同主题相对研究次序："))
        self.assertEqual(group[0]["items"][0]["status"],"WAIT")
        self.assertEqual(group[0]["items"][0]["attention_rank"],1)

    def test_current_reviews_do_not_cover_new_canonical_companies(self):
        a=intake.prepare(ROOT)
        with tempfile.TemporaryDirectory() as d:
            candidate=Path(d)/"trend_buy_research_admission.json"
            candidate.write_text(json.dumps(a,ensure_ascii=False))
            # The research pipeline must NOT silently reuse 11/05 original 16
            # reviews to give 现行 a fake formal COMPLETE result.
            old=builder.build(ROOT/"research/trend_buy_company_reviews/latest.json",
                              admission_path=candidate)
            self.assertEqual(old["prescreen_version"],"CANONICAL")
            self.assertEqual(old["mode"],"SHADOW")
            self.assertGreater(old["screen_audit"]["source_review_pending_count"],0)
            self.assertTrue(old["screen_audit"]["model_rank_missing_codes"])
            self.assertFalse(old["publication_audit"]["fresh_company_research"])
            self.assertEqual(old["selected_company_count"],15)

    def test_complete_synthetic_model_reviews_can_reach_formal_risk_engine(self):
        # Tests contract wiring only, NOT real issuer evidence or an executable
        # financial recommendation. All synthetic inputs live in /tmp.
        intake_result=intake.prepare(ROOT)
        d=intake_result["trade_date"]
        reviews=[]
        next_rank=1
        for group in intake_result["industries"]:
            for code in group["selected_codes"]:
                reviews.append({
                    "code":code,
                    "transmission":"SUPPORTED",
                    "review_evidence_date":d,
                    "review_basis":"SYNTHETIC_UNIT_TEST_ONLY",
                    "source_review":"SYNTHETIC TEST: placeholder proof to exercise Python→model→risk interface only.",
                    "source_materials":[{
                        "asof":d,"published_at":d,
                        "url":"https://example.org/test-fixture-not-real-source"}],
                    "research_falsifier":"SYNTHETIC: real negative evidence invalidates hypothesis",
                    "early_evidence_risk_review_passed":True,
                    "evidence_gap":False,
                    "model_rank":next_rank,
                    "model_reason":"SYNTHETIC: simulated comparison of income, cashflow, expectations and actual peer strength.",
                })
                next_rank+=1
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            admission=root/"trend_buy_research_admission.json"
            evidence=root/"synthetic_only.json"
            structures=root/"technical.json"
            admission.write_text(json.dumps(intake_result,ensure_ascii=False))
            evidence.write_text(json.dumps({
                "as_of_date":d,"reviews":reviews,
                "explicit_no_prior_formal_or_archive_input":True,
            },ensure_ascii=False))
            result=builder.build(
                evidence,structure_output_path=structures,
                admission_path=admission)
            self.assertEqual(result["mode"],"FORMAL")
            self.assertEqual(result["prescreen_version"],"CANONICAL")
            self.assertEqual(result["selected_company_count"],15)
            self.assertTrue(all(result["publication_audit"].values()))
            output=engine.generate(result,json.loads(structures.read_text()))
            self.assertTrue(output["production_eligible"])
            self.assertEqual(output["prescreen_version"],"CANONICAL")
            self.assertEqual(output["coverage"]["judged"],15)
            self.assertTrue(all(len(x["items"])<=5 for x in output["top5_by_theme"]))
            self.assertTrue(all(x["status"]=="WAIT" or x["status"]=="READY"
                for x in output["ready"]+output["wait"]))
            self.assertTrue(all(x.get("entry_zone") is None
                for x in output["wait"]))
            self.assertTrue(all(x.get("model_priority") is not None
                for x in output["ready"]+output["wait"]))

    def test_formal_research_requires_frozen_admission(self):
        with self.assertRaisesRegex(ValueError,"ADMISSION_REQUIRED"):
            builder.build(ROOT/"research/trend_buy_company_reviews/latest.json")

if __name__=="__main__":
    unittest.main()
