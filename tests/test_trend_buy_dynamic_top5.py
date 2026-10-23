"""Regression for new-entry phase, full thematic ranking and no future leakage."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load(filename, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

technical = load("build_full_market_price_structure.py", "compact_stage")
engine = load("trend_buy_engine.py", "dynamic_opportunity")

def bars(values):
    return [{"date": "2026-09-%02d" % (i+1),
             "open": c, "high": c+0.1, "low": c-0.1,
             "close": c, "volume": 100.0}
            for i, c in enumerate(values)]

def wait_stock(code, phase, p=10, ma20=9.8, ma60=10.1, support=9.4, sector="固态电池"):
    return {"code": code, "company_name": code, "trend_name": sector,
            "industry_code": "S630701" if int(code)%2 else "S630702",
            "status": "WAIT", "wait_reason": "WAIT_CONFIRMATION",
            "market_state": "趋势确认", "current_price": p,
            "trend_phase": phase, "transmission": "SUPPORTED",
            "structure_confirmed": False,
            "technical_context": {"ma20":ma20,"ma60":ma60,
                                  "support_invalidation":support,
                                  "volume_ratio_1d_vs_20d":1.4,
                                  "close_location_pct":75}}

class DynamicStageTests(unittest.TestCase):
    def test_blowoff_volume_weak_close_is_cooling(self):
        data = bars([10.0]*25 + [10.1, 10.3, 10.8, 11.8, 12.4, 12.5])
        data[-1]["high"],data[-1]["low"]=13.5, 12.2
        stage = technical.trend_phase_metrics(data, 10.8, 10.0, 12.5, 3.2, 2.1, 0.23)
        self.assertEqual(stage["trend_phase"], "COOLING")
        self.assertTrue(stage["phase_evidence"]["weak_close_high_volume"])

    def test_recovering_below_ma60_is_not_automatically_failed(self):
        data = bars([10]*28 + [10.2,10.4,10.7])
        stage = technical.trend_phase_metrics(data, 10.1, 11.2, 10.7, 2.0, 1.3, .9)
        self.assertEqual(stage["trend_phase"], "REPAIRING")

    def test_cooling_leader_not_in_dynamic_top5(self):
        leader = wait_stock("002074", "COOLING", p=30.41, ma20=26.87, ma60=27.07, support=26.4)
        recovering = wait_stock("002709", "REPAIRING", p=35.68, ma20=32.92, ma60=35.8, support=35.4)
        researching = {"trade_date":"2026-10-09", "companies":[
            {"trend_name":"固态电池"}]}
        result = engine.dynamic_top5_by_theme([], [leader,recovering], researching)
        self.assertEqual([i["code"] for i in result[0]["items"]], ["002709"])
        f=engine.select_focus_watchlist([], [leader,recovering], researching, result)
        self.assertEqual(f[0]["code"], "002709")
        self.assertNotEqual(f[0]["status"], "CURRENT_READY_FOCUS")

    def test_verified_strong_rr_can_outrank_unconfirmed_repairing(self):
        early = wait_stock("600985", "REPAIRING")
        stock_confirmed = wait_stock("002128", "TRANSITION")
        stock_confirmed.update({
            "structure_confirmed": True, "setup_type": "PULLBACK",
            "data_date": "2026-10-09",
            "entry_zone": [10.0, 10.1], "invalidation_price": 9.5,
            "initial_risk_pct": 5.94
        })
        stock_confirmed["technical_context"]["attention_resistance"] = {
            "status": "VERIFIED", "price": 13.5, "date": "2026-09-22",
            "source": "asof_180bar_confirmed_pivot", "history_points": 180
        }
        research = {"trade_date": "2026-10-09",
                    "companies": [{"trend_name": "固态电池"}]}
        top = engine.dynamic_top5_by_theme([], [early, stock_confirmed], research)
        self.assertEqual(top[0]["items"][0]["code"], "002128")
        pick = engine.select_focus_watchlist([], [early, stock_confirmed], research, top)
        self.assertEqual(pick[0]["code"], "002128")

    def test_only_five_per_theme_across_industries(self):
        rows=[wait_stock("%06d"%(600001+i),"REPAIRING",support=9.4)
              for i in range(9)]
        result=engine.dynamic_top5_by_theme([], rows,
            {"trade_date":"2026-10-09","companies":[{"trend_name":"固态电池"}]})
        self.assertEqual(len(result[0]["items"]),5)
        self.assertEqual(result[0]["qualified_opportunity_count"],9)

    def test_remote_wait_with_confirmed_early_signal_is_watch_only(self):
        forming = wait_stock("600487", "TRANSITION", p=10, ma20=12.5,
                             ma60=13.0, support=9.2)
        forming["technical_context"]["higher_low"] = True
        forming["phase_evidence"] = {"pullback_low_holds": True}
        research = {"trade_date": "2026-10-09",
                    "companies": [{"trend_name": "固态电池"}]}
        groups = engine.dynamic_top5_by_theme([], [forming], research)
        self.assertEqual(groups[0]["qualified_opportunity_count"], 0)
        self.assertEqual(groups[0]["trend_watch_candidate_count"], 1)
        self.assertEqual(len(groups[0]["items"]), 1)
        watch = groups[0]["items"][0]
        self.assertEqual(watch["code"], "600487")
        self.assertEqual(watch["status"], "WAIT")
        self.assertEqual(watch["entry_opportunity"], "TREND_WATCH_ONLY")
        self.assertIsNone(watch["reference"]["reference_zone"])

    def test_top5_is_a_cap_not_a_minimum(self):
        rows = [wait_stock("%06d" % (600001+i), "TRANSITION", p=10,
                           ma20=13, ma60=13.5, support=9.2)
                for i in range(8)]
        for row in rows[:2]:
            row["technical_context"]["higher_low"] = True
            row["phase_evidence"] = {"pullback_low_holds": True}
        research = {"trade_date": "2026-10-09",
                    "companies": [{"trend_name": "固态电池"}]}
        groups = engine.dynamic_top5_by_theme([], rows, research)
        self.assertEqual(len(groups[0]["items"]), 2)
        self.assertEqual(groups[0]["qualified_opportunity_count"], 0)
        self.assertEqual(groups[0]["trend_watch_candidate_count"], 2)
        self.assertTrue(all(x["entry_opportunity"] == "TREND_WATCH_ONLY"
                            for x in groups[0]["items"]))

    def test_nearby_candidate_keeps_priority_over_remote_watch(self):
        nearby = wait_stock("600011", "TRANSITION", p=10,
                            ma20=9.8, ma60=10.1, support=9.4)
        remote = wait_stock("600012", "TRANSITION", p=10,
                            ma20=13, ma60=13.5, support=9.2)
        remote["technical_context"]["higher_low"] = True
        remote["phase_evidence"] = {"pullback_low_holds": True}
        groups = engine.dynamic_top5_by_theme([], [remote, nearby],
            {"trade_date": "2026-10-09",
             "companies": [{"trend_name": "固态电池"}]})
        self.assertEqual([x["code"] for x in groups[0]["items"]],
                         ["600011", "600012"])
        self.assertEqual([x["entry_opportunity"] for x in groups[0]["items"]],
                         ["EARLY_NOT_READY", "TREND_WATCH_ONLY"])

    def test_no_forced_nominee(self):
        rows=[wait_stock("002074","COOLING")]
        research={"trade_date":"2026-10-09","companies":[{"trend_name":"固态电池"}]}
        g=engine.dynamic_top5_by_theme([],rows,research)
        self.assertEqual(g[0]["items"],[])
        self.assertEqual(engine.select_focus_watchlist([],rows,research,g)[0]["status"],
                         "NO_CURRENT_BUY_OPPORTUNITY")

    def test_attention_sequence_matches_formal_top5_without_changing_members(self):
        weaker = wait_stock("600001", "TRANSITION", support=9.75)
        stronger = wait_stock("600002", "TRANSITION", support=9.75)
        research = {"trade_date": "2026-10-09", "companies": [{"trend_name": "固态电池"}],
                    "screen_audit": {"pre_screen_selected": [
                        {"code": "600001", "fundamental_score": .2},
                        {"code": "600002", "fundamental_score": .9}]}}
        groups = engine.dynamic_top5_by_theme([], [weaker, stronger], research)
        original_codes = [row["code"] for row in groups[0]["items"]]
        focus_before = engine.select_focus_watchlist([], [weaker, stronger], research, groups)
        engine.add_attention_priorities(groups, [], [weaker, stronger], research)
        self.assertEqual([row["code"] for row in groups[0]["items"]], original_codes)
        self.assertEqual(engine.select_focus_watchlist([], [weaker, stronger], research, groups), focus_before)
        by_code = {row["code"]: row for row in groups[0]["items"]}
        self.assertEqual([i["attention_rank"] for i in groups[0]["items"]], [1, 2])
        self.assertTrue(all(row["attention_judgement"] for row in groups[0]["items"]))

    def test_missing_watch_zone_remains_wait_even_if_ranked_above_confirmed_plan(self):
        valid = wait_stock("600001", "TRANSITION", support=9.75)
        valid.update({"structure_confirmed": True, "setup_type": "PULLBACK",
                      "entry_zone": [9.85,10.02],
                      "invalidation_price": 9.6, "initial_risk_pct": 4.2})
        no_stop = wait_stock("600002", "TRANSITION", support=None)
        research = {"trade_date": "2026-10-09", "companies": [{"trend_name": "固态电池"}],
                    "screen_audit": {"pre_screen_selected": [
                        {"code": "600001", "fundamental_score": .1},
                        {"code": "600002", "fundamental_score": .99}]}}
        groups = engine.dynamic_top5_by_theme([], [no_stop, valid], research)
        engine.add_attention_priorities(groups, [], [no_stop, valid], research)
        by_code = {row["code"]: row for row in groups[0]["items"]}
        self.assertEqual(by_code["600002"]["attention_rank"], 1)
        self.assertEqual(by_code["600001"]["attention_rank"], 2)
        self.assertIsNone(by_code["600002"]["reference"]["reference_zone"])
        self.assertIn("缺可靠观察区间", by_code["600002"]["attention_judgement"])

    def test_overhead_constraint_demotes_overheated_confirmed_wait_without_changing_focus(self):
        hot = wait_stock("600001", "REACCELERATING", p=10, ma20=9.2,
                         ma60=9.0, support=9.1)
        hot.update({"structure_confirmed": True, "setup_type": "BREAKOUT",
                    "entry_zone": [9.95, 10.1], "invalidation_price": 9.7,
                    "initial_risk_pct": 3.96})
        hot["data_date"] = "2026-10-09"
        hot["technical_context"].update({
            "attention_resistance": {"status": "VERIFIED", "price": 10.2,
                                      "date": "2026-09-10",
                                      "source": "asof_180bar_confirmed_pivot",
                                      "history_points": 180},
            "distance_to_ma20_pct": 8.7})
        room = wait_stock("600002", "REPAIRING", p=10, ma20=9.8,
                          ma60=10.1, support=9.75)
        room["data_date"] = "2026-10-09"
        room["technical_context"].update({
            "attention_resistance": {"status": "VERIFIED", "price": 11.5,
                                      "date": "2026-09-01",
                                      "source": "asof_180bar_confirmed_pivot",
                                      "history_points": 180},
            "distance_to_ma20_pct": 2.0})
        research = {"trade_date": "2026-10-09",
                    "companies": [{"trend_name": "固态电池"}],
                    "screen_audit": {"pre_screen_selected": [
                        {"code": "600001", "fundamental_score": .9},
                        {"code": "600002", "fundamental_score": .2}]}}
        groups = engine.dynamic_top5_by_theme([], [hot, room], research)
        old_order = [x["code"] for x in groups[0]["items"]]
        old_focus = engine.select_focus_watchlist([], [hot, room], research, groups)
        engine.add_attention_priorities(groups, [], [hot, room], research)
        by_code = {x["code"]: x for x in groups[0]["items"]}
        self.assertEqual(by_code["600002"]["attention_rank"], 1)
        self.assertEqual(by_code["600001"]["attention_rank"], 2)
        self.assertEqual(by_code["600001"]["attention_resistance_check"]["status"], "LIMITED")
        self.assertTrue(by_code["600001"]["attention_resistance_check"]["chase_risk_high"])
        self.assertIn("暂缓追涨", by_code["600001"]["attention_judgement"])
        self.assertEqual([x["code"] for x in groups[0]["items"]], old_order)
        self.assertEqual(engine.select_focus_watchlist([], [hot, room], research, groups),
                         old_focus)

    def test_higher_verified_R_wins_within_same_status_and_structure(self):
        lower = wait_stock("600001","INITIATING",ma60=9.5,support=9.6)
        higher = wait_stock("600002","INITIATING",ma60=9.5,support=9.6)
        for row, level in ((lower,10.9),(higher,11.8)):
            row.update({"status":"READY","structure_confirmed":True,
                        "data_date":"2026-10-09","setup_type":"BREAKOUT",
                        "entry_zone":[10.02,10.12],
                        "invalidation_price":9.7,"initial_risk_pct":4.15})
            row["technical_context"]["attention_resistance"] = {
                "status":"VERIFIED","price":level,"date":"2026-10-02",
                "source":"asof_180bar_confirmed_pivot","history_points":180}
        research={"trade_date":"2026-10-09",
                  "companies":[{"trend_name":"固态电池"}]}
        group=engine.dynamic_top5_by_theme([lower,higher],[],research)[0]
        self.assertEqual([x["code"] for x in group["items"]],
                         ["600002","600001"])
        self.assertEqual(len(group["items"]),2)

    def test_limited_R_wait_ranks_below_unpriced_wait_without_removing_it(self):
        limited=wait_stock("600001","INITIATING",p=10,ma20=9.8,
                           ma60=9.5,support=9.7)
        limited.update({"data_date":"2026-10-09","structure_confirmed":True,
                        "setup_type":"BREAKOUT","entry_zone":[10.02,10.12],
                        "invalidation_price":9.7,"initial_risk_pct":4.15})
        limited["technical_context"]["attention_resistance"] = {
            "status":"VERIFIED","price":10.2,"date":"2026-10-02",
            "source":"asof_180bar_confirmed_pivot","history_points":180}
        no_zone=wait_stock("600002","INITIATING",p=10,ma20=9.8,
                           ma60=9.5,support=None)
        research={"trade_date":"2026-10-09",
                  "companies":[{"trend_name":"固态电池"}]}
        group=engine.dynamic_top5_by_theme([], [limited,no_zone],research)[0]
        self.assertEqual([x["code"] for x in group["items"]],
                         ["600002","600001"])
        self.assertEqual(len(group["items"]),2)
        engine.add_attention_priorities([group], [], [limited,no_zone], research)
        self.assertEqual([x["attention_rank"] for x in group["items"]],[1,2])

    def test_only_setup_confirmed_wait_carries_executable_pair_as_watch(self):
        valid = wait_stock("600001", "INITIATING", p=10, ma20=9.8,
                           ma60=9.5, support=8.0)
        valid.update({"data_date":"2026-10-09",
                      "structure_confirmed":True,"setup_type":"PULLBACK",
                      "entry_zone":[9.9,10.1],
                      "invalidation_price":9.65,"initial_risk_pct":4.46})
        unconfirmed = wait_stock("600002", "INITIATING", p=10,
                                 ma20=9.8,ma60=9.5,support=9.9)
        unconfirmed.update({"data_date":"2026-10-09",
                            "setup_type":"PULLBACK"})
        # Even a convenient MA20 and older general trend support cannot
        # create a numeric stop before the specific rebound is confirmed.
        self.assertIsNotNone(engine.early_watch_reference(valid)["reference_zone"])
        self.assertIsNone(engine.early_watch_reference(unconfirmed)["reference_zone"])
        research={"trade_date":"2026-10-09","companies":[{"trend_name":"固态电池"}]}
        top=engine.dynamic_top5_by_theme([], [unconfirmed,valid],research)
        self.assertEqual({x["code"] for x in top[0]["items"]},
                         {"600001","600002"})
        engine.add_attention_priorities(top,[],[unconfirmed,valid],research)
        self.assertEqual([x["attention_rank"] for x in top[0]["items"]],[1,2])
        self.assertIsNone(next(x for x in top[0]["items"]
                               if x["code"]=="600002")["reference"]["reference_zone"])

    def test_unconfirmed_breakout_stays_unpriced_even_with_bounce_signal(self):
        row=wait_stock("600003","INITIATING",p=10,ma20=9.8,
                       ma60=9.5,support=9.8)
        row["technical_context"]["breakout_level"] = 10.2
        row.update({"data_date":"2026-10-09","setup_type":"BREAKOUT",
                    "phase_evidence":{"fresh_break":True,
                                      "pullback_low_holds":False}})
        pending=engine.early_watch_reference(row)
        self.assertEqual(pending["setup_mode"],"BREAKOUT_CONFIRMATION")
        self.assertIsNone(pending["reference_zone"])
        self.assertIsNone(pending["invalidation_price"])
        row["phase_evidence"]["pullback_low_holds"]=True
        still_pending=engine.early_watch_reference(row)
        self.assertEqual(still_pending["setup_mode"],"BREAKOUT_CONFIRMATION")
        self.assertIsNone(still_pending["reference_zone"])
        self.assertEqual(row["status"],"WAIT")

    def test_top5_frozen_financial_parts_change_order_without_selection_change(self):
        weak = wait_stock("600001", "INITIATING", ma60=9.5)
        strong = wait_stock("600002", "INITIATING", ma60=9.5)
        audit = {"pre_screen_selected": [
            {"code": "600001", "growth": 0.1, "quality": 0.1,
             "valuation_match": 0.1, "trend_health": 1.0},
            {"code": "600002", "growth": 0.9, "quality": 0.9,
             "valuation_match": 0.9, "trend_health": 0.0},
        ]}
        research = {"trade_date": "2026-10-09",
                    "companies": [{"trend_name": "固态电池"}],
                    "screen_audit": audit}
        g = engine.dynamic_top5_by_theme([], [weak, strong], research)[0]
        self.assertEqual([x["code"] for x in g["items"]],
                         ["600002", "600001"])
        self.assertEqual([x["status"] for x in g["items"]], ["WAIT", "WAIT"])
        eng = engine.top5_fundamental_evidence(research)
        high = engine.top5_score_details(strong, eng[strong["code"]])
        low = engine.top5_score_details(weak, eng[weak["code"]])
        self.assertAlmostEqual(high["score"] - low["score"], .20, places=6)
        self.assertEqual(high["fundamental_basis"], "asof_growth_quality_valuation")
        engine.add_attention_priorities([g], [], [weak, strong], research)
        self.assertEqual([x["attention_rank"] for x in g["items"]], [1, 2])
        self.assertIn("可信度", g["items"][0]["attention_resistance_check"]["note"])
        focus = engine.select_focus_watchlist([], [weak, strong], research, [g])
        self.assertEqual(focus[0]["code"], "600002")
        self.assertEqual(focus[0]["status"], "EARLY_FOCUS_NOT_READY")

    def test_volume_quality_not_nearest_watch_trigger_wins(self):
        close = wait_stock("600001", "INITIATING", ma20=9.92, ma60=9.5)
        strong = wait_stock("600002", "INITIATING", ma20=9.2, ma60=9.5)
        for row in (close, strong):
            row["data_date"] = "2026-10-09"
            row["phase_evidence"] = {"positive_days_5d": 3}
            row["technical_context"].update({
                "volume_ratio_1d_vs_20d": 1.1,
                "volume_ratio_5d_vs_20d": 1.0,
                "relative_strength_20d_vs_market_pct": 0,
                "close_location_pct": 50,
            })
        strong["technical_context"].update({
            "volume_ratio_1d_vs_20d": 2.6,
            "volume_ratio_5d_vs_20d": 1.5,
            "relative_strength_20d_vs_market_pct": 8.0,
            "close_location_pct": 99,
        })
        research = {"trade_date": "2026-10-09",
                    "companies": [{"trend_name": "固态电池"}]}
        g = engine.dynamic_top5_by_theme([], [close, strong], research)[0]
        self.assertEqual([x["code"] for x in g["items"]], ["600002", "600001"])

    def test_r_below_threshold_remains_continuous_unknown_is_neutral(self):
        low = wait_stock("600001", "INITIATING", ma60=9.5)
        high = wait_stock("600002", "INITIATING", ma60=9.5)
        unknown = wait_stock("600003", "INITIATING", ma60=9.5)
        for row, obstacle in ((low, 10.24), (high, 10.6)):
            row.update({"data_date": "2026-10-09", "structure_confirmed": True,
                        "setup_type": "BREAKOUT",
                        "entry_zone": [10.02, 10.12],
                        "invalidation_price": 9.7, "initial_risk_pct": 4.15})
            row["technical_context"]["attention_resistance"] = {
                "status": "VERIFIED", "price": obstacle, "date": "2026-10-02",
                "source": "asof_180bar_confirmed_pivot", "history_points": 180}
        unknown["data_date"] = "2026-10-09"
        l = engine.top5_score_details(low)
        h = engine.top5_score_details(high)
        u = engine.top5_score_details(unknown)
        self.assertLess(l["upside_to_resistance_R"], 1.5)
        self.assertLess(h["upside_to_resistance_R"], 1.5)
        self.assertGreater(h["score"], l["score"])
        self.assertIsNone(u["upside_to_resistance_R"])
        self.assertLess(u["evidence_coverage"], h["evidence_coverage"])
        research = {"trade_date": "2026-10-09",
                    "companies": [{"trend_name": "固态电池"}]}
        groups = engine.dynamic_top5_by_theme([], [low, high, unknown], research)
        self.assertEqual({x["code"] for x in groups[0]["items"]},
                         {"600001", "600002", "600003"})
        self.assertEqual(groups[0]["items"].index(
            next(x for x in groups[0]["items"] if x["code"] == "600002")) <
            groups[0]["items"].index(
            next(x for x in groups[0]["items"] if x["code"] == "600001")), True)

    def test_expensive_sixth_member_cannot_enter_with_high_quality(self):
        rows = [wait_stock("%06d" % (600001 + i), "INITIATING",
                           ma60=9.5) for i in range(6)]
        research = {"trade_date": "2026-10-09",
                    "companies": [{"trend_name": "固态电池"}],
                    "screen_audit": {"pre_screen_selected": [
                        {"code": r["code"], "growth": 1, "quality": 1,
                         "valuation_match": 1} for r in rows[5:]
                    ]}}
        g = engine.dynamic_top5_by_theme([], rows, research)[0]
        self.assertEqual(len(g["items"]), 5)
        self.assertNotIn(rows[5]["code"], {i["code"] for i in g["items"]})

    def test_missing_or_future_evidence_never_invents_rr(self):
        row = wait_stock("600001", "INITIATING", ma60=9.5)
        row.update({"data_date": "2026-10-09",
                    "structure_confirmed": True, "setup_type": "BREAKOUT",
                    "entry_zone": [10.02, 10.12], "invalidation_price": 9.7,
                    "initial_risk_pct": 4.15})
        pivot = {"status": "VERIFIED", "price": 11.5,
                 "date": "2026-10-10", "source": "asof_180bar_confirmed_pivot",
                 "history_points": 180}
        row["technical_context"]["attention_resistance"] = pivot
        x = engine.top5_score_details(row)
        self.assertIsNone(x["upside_to_resistance_R"])
        self.assertLess(x["evidence_coverage"], 1)
        pivot["date"] = "2026-10-02"
        y = engine.top5_score_details(row)
        self.assertIsNotNone(y["upside_to_resistance_R"])
        self.assertGreater(y["evidence_coverage"], x["evidence_coverage"])

    def test_single_ma60_cross_is_wait_not_drop(self):
        c={"code":"002709","company_name":"天赐材料",
           "trend_name":"固态电池","market_state":"趋势确认",
           "trend_state":"T1", "asof_price":35.68,
           "transmission":"SUPPORTED", "theme_link_verified":True,
           "filter_passed":True, "material_risk_unresolved":False}
        s={"data_status":"verified","data_date":"2026-10-09","history_points":180,
           "low_risk_eligible":True,"current_price":35.68,
           "ma20":32.92,"ma60":35.81, "trend_phase":"REPAIRING",
           "structure_type":"damaged", "support_invalidation":35.4}
        row=engine.evaluate_candidate(c,s,"2026-10-09")
        self.assertEqual(row["status"],"WAIT")
        self.assertEqual(row["trend_phase"],"REPAIRING")

if __name__ == "__main__":
    unittest.main()
