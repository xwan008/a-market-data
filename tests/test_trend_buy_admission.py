"""Entry-first canonical admission, frozen review and model/READY separation.

Prior company reviews cannot be silently reused after the admission changes.
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
    def require_current_paired_working_set(self):
        # Data pipeline may update quotes before the next confirmed sector
        # handoff. That is an expected closed gate, not a screening failure.
        handoff=json.loads((ROOT/"research/trend_handoff.json").read_text())
        idx=json.loads((ROOT/"data/low_risk/index.json").read_text())
        if handoff.get("trade_date")!=idx.get("trade_date"):
            self.skipTest("confirmed_sector_and_market_working_set_dates_not_paired")
        return handoff["trade_date"]

    def test_python_admission_is_current_replayable_and_five_max(self):
        self.require_current_paired_working_set()
        a=intake.prepare(ROOT)
        mapping=intake.validate_admission(ROOT,a)
        self.assertEqual(a["trade_date"],self.require_current_paired_working_set())
        self.assertGreaterEqual(len(mapping),1)
        self.assertEqual(a["selected_company_count"],sum(map(len,mapping.values())))
        self.assertEqual(a["selection_policy"],"ENTRY_FIRST_NO_QUOTAS")
        self.assertTrue(all(len(codes)<=5 for codes in mapping.values()))
        self.assertTrue(all(g["selection_policy"]=="ENTRY_FIRST_NO_QUOTAS"
                            for g in a["industries"]))
        self.assertTrue(all(g["entry_selected_count"]+g["watch_fallback_count"]
                            ==len(g["selected_codes"]) for g in a["industries"]))
        self.assertFalse(a["checks"]["model_invocations"])

    @staticmethod
    def synthetic_competitors(entry_flags, *, strong_first=True):
        entries=[]
        for i,qualified in enumerate(entry_flags):
            trend=100-i*8 if strong_first else 15+i*8
            entries.append({
                "code":f"{600100+i:06d}",
                "history":{
                    "returns_pct":{"10":trend*.4,"20":trend*.65,"60":trend},
                    "positive_days_10":max(1,10-i),
                },
                "fundamental_score":0.5,
                "entry_channel_eligible":qualified,
                "entry_reference_score":(.99-i*.03) if qualified else 0.0,
                "price_structure_score":0.8 if qualified else 0.0,
            })
        return entries

    def test_six_entry_qualified_compete_without_leadership_reservation(self):
        import trend_buy_prescreen_core as core
        # Strongest two historic leaders lack current entry evidence.
        entries=self.synthetic_competitors([False,False,True,True,True,True,True,True])
        selected,audit=core.rank_entry_first(entries)
        self.assertEqual(len(selected),5)
        self.assertEqual({x["code"] for x in selected},
                         {"600102","600103","600104","600105","600106"})
        self.assertTrue(all(x["selected_channel"]=="ENTRY_PRIORITY"
                            for x in selected))
        self.assertEqual(audit["entry_selected_count"],5)
        self.assertEqual(audit["watch_fallback_count"],0)
        self.assertEqual(audit["selection_policy"],"ENTRY_FIRST_NO_QUOTAS")

    def test_entry_shortage_adds_explicit_watch_fallback_not_fake_buy(self):
        import trend_buy_prescreen_core as core
        entries=self.synthetic_competitors([False,True,False,False,True,False])
        selected,audit=core.rank_entry_first(entries)
        self.assertEqual([x["code"] for x in selected[:2]],["600101","600104"])
        self.assertEqual([x["code"] for x in selected[2:]],
                         ["600100","600102","600103"])
        self.assertEqual([x["selected_channel"] for x in selected],
                         ["ENTRY_PRIORITY"]*2+["WATCH_FALLBACK"]*3)
        self.assertTrue(audit["entry_proxy_does_not_authorize_ready"])

    def test_eligible_competition_uses_entry_score_not_pure_leader_return(self):
        import trend_buy_prescreen_core as core
        entries=self.synthetic_competitors([True]*6)
        entries[0]["entry_reference_score"]=0.05
        selected,_=core.rank_entry_first(entries)
        self.assertNotIn("600100",[x["code"] for x in selected])
        self.assertEqual(len(selected),5)

    def test_model_rank_can_include_remote_wait_before_nearby_group(self):
        nearby=[shape(f"{600110+i:06d}",i+2,
                      "同日已确认公司公告和主营逻辑，仍应由风险Gate限制交易执行")
                for i in range(5)]
        remote=shape("600199",1,"公司核验完成，尚待远端观察位置确认，本次不存在即时买点",
                     phase="TRANSITION")
        remote["technical_context"].update(ma20=15.0,ma60=16.0)
        remote["phase_evidence"]={}
        research={"prescreen_version":"CANONICAL",
                  "trade_date":"2026-11-05",
                  "companies":[{"trend_name":"游戏"}]}
        group=engine.dynamic_top5_by_theme([],nearby+[remote],research)[0]
        codes=[item["code"] for item in group["items"]]
        self.assertEqual(codes[0],"600199")
        self.assertNotIn("600114",codes)
        self.assertEqual(len(codes),5)
        self.assertEqual(group["items"][0]["entry_opportunity"],"TREND_WATCH_ONLY")

    def test_ready_always_precedes_better_ranked_wait(self):
        ready=shape("600120",90,"已确认完整交易形态，但仍仅属于条件性计划")
        ready["status"]="READY"
        wait=shape("600121",1,"候选公司模型名次更靠前，但未通过独立买点风险核验")
        research={"prescreen_version":"CANONICAL",
                  "trade_date":"2026-11-05",
                  "companies":[{"trend_name":"游戏"}]}
        group=engine.dynamic_top5_by_theme([ready],[wait],research)[0]
        self.assertEqual([item["code"] for item in group["items"]],
                         ["600120","600121"])

    def test_admission_mutation_fails_closed(self):
        self.require_current_paired_working_set()
        a=intake.prepare(ROOT)
        tampered=deepcopy(a)
        tampered["selection_policy"]="LEADERS_3_ENTRY_2"
        with self.assertRaisesRegex(ValueError,"ADMISSION"):
            intake.validate_admission(ROOT,tampered)
        tampered=deepcopy(a)
        tampered["industries"][0]["reason"]="PYTHON_3_LEADERS_2_ENTRY_FINANCE_CORE_FIRST"
        with self.assertRaisesRegex(ValueError,"ADMISSION"):
            intake.validate_admission(ROOT,tampered)
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
        self.require_current_paired_working_set()
        if self.require_current_paired_working_set()!="2026-11-05":
            self.skipTest("historical_original_16_reviews_only_relevant_to_nov05")
        a=intake.prepare(ROOT)
        with tempfile.TemporaryDirectory() as d:
            candidate=Path(d)/"trend_buy_research_admission.json"
            candidate.write_text(json.dumps(a,ensure_ascii=False))
            # The pipeline must NOT silently reuse the prior 16 reviews to
            # forge a current formal COMPLETE result.
            old=builder.build(ROOT/"research/trend_buy_company_reviews/latest.json",
                              admission_path=candidate)
            self.assertEqual(old["prescreen_version"],"CANONICAL")
            self.assertEqual(old["screen_audit"]["financial_scoring_mode"],"VERIFIED_CORE")
            self.assertEqual(old["mode"],"SHADOW")
            self.assertGreater(old["screen_audit"]["source_review_pending_count"],0)
            self.assertTrue(old["screen_audit"]["model_rank_missing_codes"])
            self.assertFalse(old["publication_audit"]["fresh_company_research"])
            self.assertEqual(old["selected_company_count"],a["selected_company_count"])

    def test_complete_synthetic_model_reviews_can_reach_formal_risk_engine(self):
        self.require_current_paired_working_set()
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
                    "transmission":"NOT_SUPPORTED" if not reviews else "SUPPORTED",
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
            self.assertEqual(result["screen_audit"]["financial_scoring_mode"],"VERIFIED_CORE")
            self.assertEqual(result["selected_company_count"],intake_result["selected_company_count"])
            self.assertTrue(all(result["publication_audit"].values()))
            output=engine.generate(result,json.loads(structures.read_text()))
            self.assertTrue(output["production_eligible"])
            self.assertEqual(output["prescreen_version"],"CANONICAL")
            self.assertEqual(output["coverage"]["judged"],intake_result["selected_company_count"])
            self.assertEqual(len(output["drop"]),1)
            self.assertEqual(result["selected_company_count"],intake_result["selected_company_count"])
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
