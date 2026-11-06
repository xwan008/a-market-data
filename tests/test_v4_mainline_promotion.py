"""V4 can replace the program and model ranking only when both are real.

The current 11/05 old company research should NOT be promoted through V4
because its 15 company slots differ from the same-day V4 Python selection.
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
import v4_prepare_research_candidates as intake
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
        "v4_model_priority":priority,"v4_model_reason":reason,
    }


class V4MainlinePromotionTests(unittest.TestCase):
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
        with self.assertRaisesRegex(ValueError,"V4_ADMISSION"):
            intake.validate_admission(ROOT,tampered)
        tampered=deepcopy(a)
        tampered["industries"][0]["selected_codes"]+=["000001"]
        with self.assertRaisesRegex(ValueError,"V4_ADMISSION"):
            intake.validate_admission(ROOT,tampered)
        tampered=deepcopy(a)
        tampered["source"]["finance_evidence_sha256"]="not_same_file"
        with self.assertRaisesRegex(ValueError,"V4_ADMISSION"):
            intake.validate_admission(ROOT,tampered)

    def test_v4_model_rank_changes_attention_but_not_trade_ready(self):
        first=shape("002517",2,"经营现金流持续改善，行业持续强势，但存在较高追高风险")
        second=shape("603444",1,"盈利质量较稳，当前价格结构需要等待回踩承接确认")
        research={"prescreen_version":"V4_B1","trade_date":"2026-11-05",
                  "companies":[{"trend_name":"游戏"}]}
        group=engine.dynamic_top5_by_theme([], [first,second],research)
        self.assertEqual([x["code"] for x in group[0]["items"]],
                         ["603444","002517"])
        engine.add_attention_priorities(group,[],[first,second],research)
        self.assertTrue(group[0]["items"][0]["attention_judgement"].startswith(
            "V4模型同主题相对研究次序："))
        self.assertEqual(group[0]["items"][0]["status"],"WAIT")
        self.assertEqual(group[0]["items"][0]["attention_rank"],1)

    def test_current_reviews_do_not_cover_new_v4_companies(self):
        a=intake.prepare(ROOT)
        with tempfile.TemporaryDirectory() as d:
            candidate=Path(d)/"v4_research_admission.json"
            candidate.write_text(json.dumps(a,ensure_ascii=False))
            # The research pipeline must NOT silently reuse 11/05 original 16
            # reviews to give V4 a fake formal COMPLETE result.
            old=builder.build(ROOT/"research/trend_buy_company_reviews/latest.json",
                              v4_admission_path=candidate)
            self.assertEqual(old["prescreen_version"],"V4_B1")
            self.assertEqual(old["mode"],"SHADOW")
            self.assertGreater(old["screen_audit"]["source_review_pending_count"],0)
            self.assertTrue(old["screen_audit"]["v4_model_rank_missing_codes"])
            self.assertFalse(old["publication_audit"]["fresh_company_research"])
            self.assertEqual(old["selected_company_count"],15)

    def test_original_pipeline_without_v4_does_not_change(self):
        d=builder.build(ROOT/"research/trend_buy_company_reviews/latest.json")
        self.assertEqual(d["prescreen_version"],"LEGACY")
        self.assertEqual(d["mode"],"FORMAL")
        self.assertEqual(d["selected_company_count"],16)

if __name__=="__main__":
    unittest.main()
