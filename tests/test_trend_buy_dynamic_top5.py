"""Canonical theme Top5, technical observations, and no hidden ordering gates."""
import importlib.util
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def load(filename,name):
    spec=importlib.util.spec_from_file_location(name,ROOT/"scripts"/filename)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


engine=load("trend_buy_engine.py","trend_engine")
technical=load("build_full_market_price_structure.py","technical")


def stock(code,priority,phase="REPAIRING",status="WAIT",near=True):
    ma20=9.9 if near else 14.5
    return {
        "code":code,"company_name":"测试"+code,"trend_name":"游戏",
        "industry_code":"S720401","market_state":"趋势确认",
        "status":status,"wait_reason":"WAIT_CONFIRMATION" if status=="WAIT" else None,
        "transmission":"SUPPORTED","trend_phase":phase,
        "model_priority":priority,"model_reason":"主营财务与业务证据已经研究，风险准入需要单独评估",
        "current_price":10.0,"data_date":"2026-11-05",
        "technical_context":{"ma20":ma20,"ma60":9.5 if near else 15.0,
                             "volume_ratio_1d_vs_20d":1.5,
                             "close_location_pct":80},
        "phase_evidence":{"positive_days_5d":3,"return_5d_pct":2},
    }


def research():
    return {"prescreen_version":"CANONICAL","trade_date":"2026-11-05",
            "companies":[{"trend_name":"游戏"}]}


class CanonicalTop5Tests(unittest.TestCase):
    def test_model_rank_before_five_name_cutoff(self):
        nearby=[stock(f"{600001+i:06d}",i+2) for i in range(5)]
        remote=stock("600099",1,phase="TRANSITION",near=False)
        result=engine.dynamic_top5_by_theme([],nearby+[remote],research())[0]
        self.assertEqual(len(result["items"]),5)
        self.assertEqual(result["items"][0]["code"],"600099")
        self.assertEqual(result["items"][0]["entry_opportunity"],"TREND_WATCH_ONLY")
        self.assertNotIn("600005",{x["code"] for x in result["items"]})
        self.assertEqual(result["qualified_opportunity_count"],5)
        self.assertEqual(result["trend_watch_candidate_count"],1)

    def test_ready_precedes_wait_without_changing_model_reason(self):
        ready=stock("600001",88,status="READY")
        waiting=stock("600002",1)
        result=engine.dynamic_top5_by_theme([ready],[waiting],research())
        self.assertEqual([x["code"] for x in result[0]["items"]],
                         ["600001","600002"])
        engine.add_attention_priorities(result,[ready],[waiting],research())
        self.assertIn("模型同主题相对研究次序",result[0]["items"][0]["attention_judgement"])
        self.assertIn("WAIT不是买入许可",result[0]["items"][1]["attention_judgement"])
        self.assertNotIn("量价及相对强度综合",result[0]["items"][0]["attention_judgement"])

    def test_missing_or_duplicate_model_rank_blocks(self):
        first=stock("600001",1)
        second=stock("600002",1)
        with self.assertRaisesRegex(ValueError,"DUPLICATE_MODEL_RANK_WITHIN_THEME"):
            engine.dynamic_top5_by_theme([], [first,second],research())
        second["model_priority"]=None
        with self.assertRaisesRegex(ValueError,"MODEL_RESEARCH_RANK_MISSING"):
            engine.dynamic_top5_by_theme([], [first,second],research())

    def test_noncanonical_ranking_is_not_an_entrypoint(self):
        with self.assertRaisesRegex(ValueError,"CANONICAL_MODEL_RANK_REQUIRED"):
            engine.dynamic_top5_by_theme([],[stock("600001",1)],
                                         {"companies":[{"trend_name":"游戏"}]})

    def test_cooling_and_failed_do_not_enter_display_top5(self):
        cooling=stock("600001",1,phase="COOLING")
        failed=stock("600002",2,phase="FAILED")
        recovering=stock("600003",3,phase="REPAIRING")
        group=engine.dynamic_top5_by_theme([],[cooling,failed,recovering],research())[0]
        self.assertEqual([x["code"] for x in group["items"]],["600003"])

    def test_technical_context_cannot_override_model_rank(self):
        first=stock("600001",1)
        second=stock("600002",2)
        first["technical_context"]["close_location_pct"]=20
        first["technical_context"]["volume_ratio_1d_vs_20d"]=0.6
        second["technical_context"]["close_location_pct"]=99
        second["technical_context"]["volume_ratio_1d_vs_20d"]=5.0
        self.assertEqual([x["code"] for x in
            engine.dynamic_top5_by_theme([], [second,first],research())[0]["items"]],
            ["600001","600002"])

    def test_attention_risk_annotations_do_not_resort_or_promote(self):
        a=stock("600001",1)
        b=stock("600002",2,near=False)
        a["technical_context"]["chase_risk"]="high"
        g=engine.dynamic_top5_by_theme([], [b,a],research())
        before=[x["code"] for x in g[0]["items"]]
        engine.add_attention_priorities(g,[],[b,a],research())
        self.assertEqual([x["code"] for x in g[0]["items"]],before)
        self.assertTrue(g[0]["items"][0]["attention_resistance_check"]["chase_risk_high"])
        self.assertEqual(g[0]["items"][0]["attention_rank"],1)
        self.assertIn("暂缓追涨",g[0]["items"][0]["attention_resistance_check"]["note"])

    def test_technical_observations_never_compute_ranking_key(self):
        observed=engine.technical_observation_details(stock("600001",1))
        self.assertNotIn("ranking_key",observed)
        self.assertNotIn("volume_strength",observed)
        self.assertTrue(observed["no_r_assumed"])
        self.assertEqual(observed["risk_basis"],"UNKNOWN_NOT_ZERO")

    def test_closing_acceptance_never_uses_future_bars(self):
        rows=[
            {"date":"2026-10-20","open":43.19,"high":45.68,"low":43.15,"close":45.20,"volume":100},
            {"date":"2026-10-21","open":45.22,"high":45.38,"low":44.33,"close":44.46,"volume":100},
            {"date":"2026-10-22","open":44.32,"high":45.40,"low":44.32,"close":44.46,"volume":100},
            {"date":"2026-10-23","open":44.05,"high":47.12,"low":42.90,"close":47.07,"volume":200},
        ]
        fact=technical.recent_closing_acceptance(rows)
        self.assertEqual(fact["pattern"],"SAME_DAY_SWEEP_RECLAIM")
        self.assertEqual(fact["support_dates"],["2026-10-21","2026-10-22"])
        rows.append({"date":"2026-10-26","open":25,"high":25,"low":25,"close":25,"volume":1000})
        self.assertEqual(fact,technical.recent_closing_acceptance(rows[:-1]))


if __name__=="__main__":
    unittest.main()
