"""As-of, single-official-list ranking regression without altering trade permission."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("trend", ROOT / "scripts" / "trend_buy_engine.py")
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)
DAY = "2026-11-17"


def company(code, name, priority, *, status="WAIT", theme="线下药店",
            previous=-2, recent=4, up5=4, fresh=False, close=75,
            ma_gap=3, volume=1.0, ma60=20, price=21, overhead=None,
            phase="TRANSITION", trade_date=DAY, research_quality=50):
    ctx = {
        "ma20": price / (1 + ma_gap / 100),
        "ma60": ma60, "distance_to_ma20_pct": ma_gap,
        "volume_ratio_1d_vs_20d": volume,
        "close_location_pct": close,
        "chase_risk": "low",
        "first_effective_resistance": ({"price": overhead} if overhead else None),
        "attention_resistance": None,
    }
    return {
        "code": code, "company_name": name, "trend_name": theme,
        "status": status, "data_date": trade_date,
        "current_price": price, "model_priority": priority,
        "research_quality_evidence": {
            "status":"VERIFIED",
            "source":"FROZEN_F10_AND_COMPLETED_HISTORY_V1",
            "asof_date":DAY, "score":research_quality,
            "components":{"test_fixture":True}},
        "trend_phase": phase, "technical_context": ctx,
        "phase_evidence": {
            "previous_5d_return_pct": previous, "return_5d_pct": recent,
            "positive_days_5d": up5, "fresh_break": fresh,
            "signal_uses_completed_bars_only": True,
        },
        "wait_reason": "WAIT_PULLBACK" if status == "WAIT" else None,
        "structure_confirmed": status == "READY",
        "entry_zone": None, "invalidation_price": None,
    }


def groups(rows):
    return engine.dynamic_top5_by_theme(
        [x for x in rows if x["status"] == "READY"],
        [x for x in rows if x["status"] == "WAIT"],
        {"prescreen_version": "CANONICAL", "trade_date": DAY,
         "companies": [{"trend_name": x["trend_name"]} for x in rows]},
    )


class TestAsOfEntryValueRanking(unittest.TestCase):
    def test_pharmacy_repair_is_not_suppressed_by_20d_leadership(self):
        xs = [
            company("603233", "大参林", 1, previous=-3.06, recent=2.66,
                    fresh=False, close=55.93, ma_gap=4.98, volume=.74,
                    price=20.82, overhead=21.69, research_quality=77.7),
            company("002727", "一心堂", 2, previous=-5.74, recent=7.26,
                    fresh=True, close=78.18, ma_gap=4.64, volume=1.143,
                    price=13.74, overhead=None, research_quality=81.9),
            company("603883", "老百姓", 3, previous=-5.59, recent=5.07,
                    fresh=False, close=75, ma_gap=1.97, volume=.801,
                    price=14.91, overhead=15.33, research_quality=56.4),
            company("603939", "益丰药房", 4, previous=-10.28, recent=8.48,
                    fresh=True, close=95, ma_gap=3.10, volume=.958,
                    price=26.61, overhead=27.68, research_quality=50.7),
            company("600833", "第一医药", 5, previous=-.21, recent=-2.98,
                    up5=1, fresh=False, close=25, ma_gap=-4.88,
                    volume=.729, price=9.13, ma60=10.27, overhead=9.70,
                    research_quality=20),
        ]
        g = groups(xs)[0]
        self.assertEqual(g["attention_ranking_policy"], engine.OPPORTUNITY_RANK_POLICY)
        ordered = [x["company_name"] for x in g["items"]]
        self.assertEqual(ordered[:2], ["益丰药房", "一心堂"])
        self.assertEqual(ordered[-1], "第一医药")
        self.assertLess(ordered.index("益丰药房"), ordered.index("大参林"))
        self.assertTrue(all(x["status"] == "WAIT" for x in g["items"]))
        self.assertTrue(all(x["opportunity_rank_evidence"]["not_trade_permission"]
                            for x in g["items"]))
        self.assertEqual(g["items"][0]["original_model_rank"], 4)
        self.assertEqual(g["items"][0]["opportunity_rank_evidence"]["research_quality_score"], 50.7)
        self.assertEqual(xs[3]["status"], "WAIT")
        self.assertIsNone(xs[3]["entry_zone"])

    def test_extreme_game_rebound_is_not_automatically_top(self):
        xs = [
            company("002602", "世纪华通", 1, theme="游戏", previous=-7.07,
                    recent=13.62, fresh=True, close=77.97, ma_gap=4.18,
                    volume=2.003, price=13.6, ma60=15, phase="REPAIRING"),
            company("002558", "巨人网络", 2, theme="游戏", previous=-5.56,
                    recent=7.29, fresh=True, close=80, ma_gap=1.70,
                    volume=1.6, price=21.1, ma60=20, phase="TRANSITION"),
        ]
        g = groups(xs)[0]
        self.assertEqual(g["items"][0]["company_name"], "巨人网络")
        self.assertEqual(g["items"][1]["company_name"], "世纪华通")
        self.assertTrue(any(
            x in g["items"][1]["opportunity_rank_evidence"]["penalties"]
            for x in ("recent_5d_surge", "below_ma60_unconfirmed")))

    def test_ready_remains_ahead_of_higher_scoring_wait(self):
        xs = [
            company("000001", "平安银行", 6, theme="银行", status="READY",
                    previous=.76, recent=3.29, up5=3, close=66.67,
                    ma_gap=4.91, price=12.25, ma60=11.525),
            company("600000", "浦发银行", 1, theme="银行", previous=1.09,
                    recent=6.47, up5=4, fresh=True, close=86.67,
                    ma_gap=8.08, price=10.86, ma60=9.5387, volume=1.317),
            company("002966", "苏州银行", 3, theme="银行", previous=.1,
                    recent=5.53, up5=3, fresh=True, close=67.74,
                    ma_gap=6.10, price=10.12, ma60=9.2255, volume=1.059),
        ]
        g = groups(xs)[0]
        self.assertEqual(g["items"][0]["code"], "000001")
        self.assertEqual(g["items"][0]["status"], "READY")
        self.assertEqual(g["items"][1]["code"], "002966")
        self.assertEqual(g["items"][2]["code"], "600000")
        self.assertEqual(xs[1]["status"], "WAIT")


    def test_model_rank_spacing_never_becomes_quality_points(self):
        a=company("100001","A",1,research_quality=50)
        first=engine.opportunity_rank_evidence(a,DAY)
        a["model_priority"]=99
        last=engine.opportunity_rank_evidence(a,DAY)
        self.assertEqual(first["score"],last["score"])
        self.assertEqual(last["research_quality_score"],50)
        self.assertEqual(last["research_quality_source"],
                         "FROZEN_F10_AND_COMPLETED_HISTORY_V1")

    def test_continuous_research_quality_has_proportional_not_ordinal_impact(self):
        a=company("100001","A",1,research_quality=81.9)
        b=company("100002","B",99,research_quality=50.7)
        aa=engine.opportunity_rank_evidence(a,DAY)
        bb=engine.opportunity_rank_evidence(b,DAY)
        self.assertAlmostEqual(aa["score"]-bb["score"],
                               .15*(81.9-50.7),places=3)

    def test_missing_or_future_research_evidence_falls_back_whole_theme(self):
        a=company("100001","A",1,recent=1,research_quality=70)
        b=company("100002","B",2,recent=9,previous=-10,fresh=True,
                  research_quality=90)
        a["research_quality_evidence"]=None
        g=groups([a,b])[0]
        self.assertEqual(g["attention_ranking_policy"],
                         "MODEL_RANK_FALLBACK_DATA_GAP")
        self.assertEqual([z["code"] for z in g["items"]],["100001","100002"])
        a["research_quality_evidence"]={
            "status":"VERIFIED","asof_date":"2026-11-18","score":70,
            "source":"FROZEN_F10_AND_COMPLETED_HISTORY_V1"}
        self.assertEqual(groups([a,b])[0]["attention_ranking_policy"],
                         "MODEL_RANK_FALLBACK_DATA_GAP")
        a["research_quality_evidence"]["asof_date"]=DAY
        a["research_quality_evidence"]["score"]=150
        self.assertEqual(groups([a,b])[0]["attention_ranking_policy"],
                         "MODEL_RANK_FALLBACK_DATA_GAP")

    def test_missing_or_future_bar_falls_back_for_whole_theme(self):
        xs = [
            company("100001", "A", 1, recent=1),
            company("100002", "B", 2, recent=9, previous=-10, fresh=True),
        ]
        xs[0]["phase_evidence"]["return_5d_pct"] = None
        g = groups(xs)[0]
        self.assertEqual(g["attention_ranking_policy"], "MODEL_RANK_FALLBACK_DATA_GAP")
        self.assertEqual([x["code"] for x in g["items"]], ["100001", "100002"])
        xs[0]["phase_evidence"]["return_5d_pct"] = 1.0
        xs[0]["data_date"] = "2026-11-18"
        g = groups(xs)[0]
        self.assertEqual(g["attention_ranking_policy"], "MODEL_RANK_FALLBACK_DATA_GAP")

    def test_near_verified_pivot_is_not_infinite_headroom(self):
        xs = [
            company("200001", "阻力近", 1, overhead=21.1),
            company("200002", "阻力远", 2, overhead=24),
        ]
        g = groups(xs)[0]
        near = next(x for x in g["items"] if x["code"] == "200001")
        far = next(x for x in g["items"] if x["code"] == "200002")
        self.assertIn("near_verified_overhead",
                      near["opportunity_rank_evidence"]["penalties"])
        self.assertGreater(far["opportunity_rank_evidence"]["score"],
                           near["opportunity_rank_evidence"]["score"])


if __name__ == "__main__":
    unittest.main()
