"""As-of attention ranking regression; never change trade permission."""
import copy
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("trend", ROOT / "scripts" / "trend_buy_engine.py")
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)
DAY = "2026-11-17"


def company(code, rank, *, recent=8, prior=3, ret3=2, drawdown=-4,
            higher=True, close=75, close3=65, core=.6, cash=1,
            status="WAIT", overhead=24, ma20=20, ma60=20):
    return {
        "code": code, "company_name": code, "trend_name": "test",
        "data_date": DAY, "current_price": 21, "status": status,
        "model_priority": rank, "trend_phase": "TRANSITION",
        "structure_confirmed": status == "READY",
        "entry_zone": None, "invalidation_price": None,
        "research_quality_evidence": {
            "status": "VERIFIED", "source": "FROZEN_F10_AND_COMPLETED_HISTORY_V1",
            "asof_date": DAY, "score": 60,
            "components": {"peer_percentiles": {"10": .5, "20": .5, "60": .5},
                           "core_growth_component": core, "cashflow_component": cash}},
        "technical_context": {"ma20": ma20, "ma60": ma60, "higher_low": higher,
            "distance_to_ma20_pct": (21/ma20-1)*100,
            "first_effective_resistance": {"price": overhead},
            "close_location_pct": close, "chase_risk": "low"},
        "phase_evidence": {"return_5d_pct": recent,
            "previous_5d_return_pct": prior, "return_3d_pct": ret3,
            "positive_days_5d": 3, "fresh_break": False,
            "max_close_drawdown_10d_pct": drawdown,
            "close_location_pct": close, "close_location_3d_avg_pct": close3,
            "up_day_volume_ratio_5d": 1.5, "down_day_volume_ratio_5d": 1.0,
            "volume_ratio_1d": 1.5, "weak_close_high_volume": False,
            "signal_uses_completed_bars_only": True},
    }


def groups(rows):
    return engine.dynamic_top5_by_theme(
        [x for x in rows if x["status"] == "READY"],
        [x for x in rows if x["status"] == "WAIT"],
        {"prescreen_version": "CANONICAL", "trade_date": DAY,
         "companies": [{"trend_name": "test"}]})[0]


class TestAsOfTrendQualityRanking(unittest.TestCase):
    def test_rebound_vs_continuation_combination(self):
        strong = company("A", 2, recent=8, drawdown=-4, higher=True)
        rebound = company("B", 1, recent=8, drawdown=-15, higher=False)
        a, b = [engine.opportunity_rank_evidence(x, DAY) for x in (strong, rebound)]
        self.assertEqual(a["continuation_context"]["stage"], "CONTINUATION")
        self.assertEqual(b["continuation_context"]["stage"], "REBOUND_UNCONFIRMED")
        self.assertGreater(a["score"], b["score"])
        self.assertEqual([x["code"] for x in groups([strong, rebound])["items"]], ["A", "B"])

    def test_single_day_close_has_bounded_influence(self):
        a = company("A", 1, close=100)
        b = company("B", 2, close=50)
        x, y = [engine.opportunity_rank_evidence(z, DAY) for z in (a, b)]
        self.assertAlmostEqual(x["score"]-y["score"], .30*.15*50, places=3)

    def test_ma_distance_not_double_counted(self):
        a = company("A", 1, ma20=20, ma60=20)
        b = company("B", 2, ma20=15, ma60=25)
        x, y = [engine.opportunity_rank_evidence(z, DAY) for z in (a, b)]
        self.assertEqual(x["score"], y["score"])
        self.assertNotIn("penalties", y)
        self.assertEqual(y["entry_evidence_status"], "UNCONFIRMED_NEUTRAL")

    def test_ready_priority_never_changes_input_status(self):
        a = company("A", 1, recent=15, core=1)
        b = company("B", 2, status="READY", recent=1, core=0)
        before = copy.deepcopy([a, b])
        group = groups([a, b])
        self.assertEqual(group["attention_ranking_policy"], engine.OPPORTUNITY_RANK_POLICY)
        self.assertEqual([x["code"] for x in group["items"]], ["B", "A"])
        self.assertEqual([a, b], before)
        self.assertTrue(all(x["opportunity_rank_evidence"]["not_trade_permission"]
                            for x in group["items"]))

    def test_ordinal_model_rank_is_not_quality_score(self):
        a = company("A", 1)
        x = engine.opportunity_rank_evidence(a, DAY)
        a["model_priority"] = 99
        self.assertEqual(x["score"], engine.opportunity_rank_evidence(a, DAY)["score"])

    def test_financial_components_have_bounded_impact(self):
        a = company("A", 1, core=.8)
        b = company("B", 2, core=.5)
        x, y = [engine.opportunity_rank_evidence(z, DAY) for z in (a, b)]
        self.assertAlmostEqual(x["score"]-y["score"], .20*.80*100*.3, places=3)

    def test_missing_or_future_evidence_falls_back_whole_theme(self):
        for mutation in ("missing", "future", "bad_quality", "missing_drawdown"):
            a, b = company("A", 1), company("B", 2, recent=15)
            if mutation == "missing":
                a["research_quality_evidence"] = None
            elif mutation == "future":
                a["research_quality_evidence"]["asof_date"] = "2026-11-18"
            elif mutation == "bad_quality":
                a["research_quality_evidence"]["score"] = 150
            else:
                a["phase_evidence"]["max_close_drawdown_10d_pct"] = None
            g = groups([a,b])
            self.assertEqual(g["attention_ranking_policy"], "MODEL_RANK_FALLBACK_DATA_GAP")
            self.assertEqual([x["code"] for x in g["items"]], ["A", "B"])

    def test_overhead_only_scores_a_paired_trade_setup(self):
        near, far = company("A",1,overhead=21.2), company("B",2,overhead=24)
        self.assertEqual(engine.opportunity_rank_evidence(near,DAY)["score"],
                         engine.opportunity_rank_evidence(far,DAY)["score"])
        for x in (near, far):
            x["structure_confirmed"] = True
            x["entry_zone"], x["invalidation_price"] = [21,21.1], 20.6
        a,b = [engine.opportunity_rank_evidence(x,DAY) for x in (near,far)]
        self.assertEqual(a["entry_evidence_status"], "PAIRED_SETUP")
        self.assertGreater(b["entry_value_score"],a["entry_value_score"])
        self.assertEqual(near["status"],"WAIT")



class TestOfflineModelTradePlan(unittest.TestCase):
    """Synthetic guardrail checks only; never financial recommendations."""
    def setUp(self):
        from datetime import date,timedelta
        spec = importlib.util.spec_from_file_location(
            "model_plan",ROOT/"scripts"/"replay_model_trade_plan.py")
        self.validator=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.validator)
        end=date(2026,11,23)
        self.rows=[{"date":(end-timedelta(days=179-i)).isoformat(),
                    "open":9.9,"high":10.0,"low":9.8,"close":9.9,"volume":1000}
                   for i in range(180)]
        self.rows[30]["high"]=12.0
        self.rows[-1].update(open=9.99,high=10.12,low=9.9,close=10.10,volume=1600)
        self.day=self.rows[-1]["date"]
        self.row={"code":"600001","current_price":10.10,"market_state":"趋势确认",
                  "transmission":"SUPPORTED","trend_phase":"TRANSITION",
                  "technical_context":{"chase_risk":"low"}}
        anchor={"date":self.rows[-2]["date"],"field":"high","price":10.0}
        self.plan={"code":"600001","model_rank":1,
                   "model_reason":"Synthetic test only, not issuer research or a recommendation.",
                   "decision":"PROPOSE_ENTRY","setup":"BREAKOUT",
                   "structure_anchor":anchor,"failure_anchor":dict(anchor),
                   "confirmation_pattern":"CLOSE_ABOVE_PREVIOUS_HIGH",
                   "entry_zone":[10.01,10.12],"invalidation_price":9.95,
                   "entry_trigger":"Synthetic breakout entry",
                   "invalidation_rule":"Synthetic boundary failure"}

    def validate(self):
        return self.validator.validate_plan(self.plan,self.row,self.rows,self.day)

    def test_valid_proposal_preserves_model_prices_and_rank(self):
        result=self.validate()
        self.assertEqual(result["status"],"READY")
        self.assertEqual(result["model_rank"],1)
        self.assertEqual(result["entry_zone"],self.plan["entry_zone"])
        self.assertEqual(result["invalidation_price"],self.plan["invalidation_price"])
        self.assertTrue(result["not_trade_permission"])

    def test_risk_veto_does_not_generate_substitute_plan(self):
        self.plan["invalidation_price"]=9.4
        result=self.validate()
        self.assertEqual(result["status"],"WAIT")
        self.assertEqual(result["decision_reason"],"STRUCTURAL_RISK_FAILED")
        self.assertIsNone(result["entry_zone"])
        self.assertIsNone(result["invalidation_price"])

    def test_fabricated_anchor_is_rejected(self):
        self.plan["structure_anchor"]["price"]=10.03
        result=self.validate()
        self.assertEqual(result["decision_reason"],"ANCHOR_PRICE_MISMATCH")
        self.assertEqual(result["status"],"WAIT")

    def test_verified_overhead_veto(self):
        self.rows[30]["high"]=10.15
        result=self.validate()
        self.assertEqual(result["status"],"WAIT")
        self.assertEqual(result["decision_reason"],"RISK_REWARD_FAILED")

    def test_wait_never_promoted(self):
        self.plan.update(decision="WAIT",entry_zone=None,invalidation_price=None,
                         watch_anchor=self.plan["structure_anchor"],
                         watch_condition="Observe only")
        result=self.validate()
        self.assertEqual(result["status"],"WAIT")
        self.assertTrue(result["watch_reference"]["observation_only"])
        self.assertIsNone(result["entry_zone"])

    def test_future_history_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"HISTORY_NOT_FROZEN_ASOF"):
            self.validator.history_rows({"history":self.rows},self.rows[-2]["date"],9.9)


if __name__ == "__main__":
    unittest.main()
