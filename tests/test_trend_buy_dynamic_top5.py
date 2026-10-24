"""Regression for new-entry phase, full thematic ranking and no future leakage."""
import copy
import importlib.util
import json
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
    def test_pinned_20261023_top5_explanations_change_not_member_rank_risk_values(self):
        """Labels may change, but all previously published non-prose fields stay."""
        snapshot = json.loads((ROOT / "tests" / "fixtures" /
                               "top5_cleanup_2026-10-23.json").read_text(
                                   encoding="utf-8"))
        self.assertEqual(snapshot["trade_date"], "2026-10-23")
        original = snapshot["groups"]
        rerun = copy.deepcopy(original)
        for group in rerun:
            for item in group["items"]:
                for annotation in ("attention_rank", "attention_judgement",
                                   "attention_resistance_check"):
                    item.pop(annotation, None)
        result = engine.add_attention_priorities(
            rerun, [], snapshot["rows"], snapshot["research"])
        self.assertEqual(len(original), len(result))
        for past, current in zip(original, result):
            self.assertEqual(past["trend_name"], current["trend_name"])
            self.assertEqual(
                [x["code"] for x in past["items"]],
                [x["code"] for x in current["items"]])
            for index, (old, new) in enumerate(zip(past["items"],
                                                    current["items"]), 1):
                self.assertEqual({k: v for k, v in old.items()
                                  if k not in ("attention_rank", "attention_judgement",
                                               "attention_resistance_check")},
                                 {k: v for k, v in new.items()
                                  if k not in ("attention_rank", "attention_judgement",
                                               "attention_resistance_check")})
                self.assertEqual(old["attention_rank"], new["attention_rank"])
                self.assertEqual(new["attention_rank"], index)
                self.assertEqual(
                    {k: v for k, v in old["attention_resistance_check"].items()
                     if k != "note"},
                    {k: v for k, v in new["attention_resistance_check"].items()
                     if k != "note"})
                self.assertTrue(new["attention_judgement"].startswith("Top5关注排序依据："))
                self.assertIn("不是交易买入许可", new["attention_judgement"])
                self.assertNotIn("PR #", new["attention_judgement"])
                self.assertNotIn("试错成本", new["attention_judgement"])
                self.assertIn("历史阻力和1.5R为交易准入检查",
                              new["attention_resistance_check"]["note"])
        self.assertEqual([x["code"] for x in result[1]["items"]],
                         ["603275", "603416", "002979", "603025", "603583"])
        self.assertTrue(all(x["status"] == "WAIT" for x in snapshot["rows"]))

    def test_rank_explanation_independent_of_old_formal_tiers(self):
        """Formal R and financial quality may change the risk note, never why ranked."""
        x = wait_stock("600001", "INITIATING", ma60=9.5)
        x.update(data_date="2026-10-23",
                 phase_evidence={"fresh_break": True, "return_5d_pct": 6.2,
                                 "positive_days_5d": 4})
        x["technical_context"].update({
            "volume_ratio_1d_vs_20d": 2.1, "close_location_pct": 93,
            "distance_to_ma20_pct": 2.04,
            "recent_acceptance": {
                "pattern": "SAME_DAY_SWEEP_RECLAIM",
                "data_date": "2026-10-23", "lookback_trading_days": 3,
                "support_close_band": [9.1, 9.1],
                "support_dates": ["2026-10-21", "2026-10-22"],
                "support_low": 8.9, "intraday_support_broken": True}})
        research = {"trade_date": "2026-10-23",
                    "companies": [{"trend_name": "固态电池"}],
                    "screen_audit": {"pre_screen_selected": [
                        {"code": "600001", "fundamental_score": .02}]}}
        group = engine.dynamic_top5_by_theme([], [x], research)
        engine.add_attention_priorities(group, [], [x], research)
        first = group[0]["items"][0]
        explanation = first["attention_judgement"]
        self.assertIn("盘中刺破后收复", explanation)
        self.assertIn("失效条件未定", explanation)
        self.assertNotIn("优先深研", explanation)
        self.assertIn("不据当日最低价新造止损",
                      first["attention_resistance_check"]["note"])
        altered = copy.deepcopy(x)
        altered.update(status="READY", structure_confirmed=True,
                       setup_type="BREAKOUT", entry_zone=[10.0,10.2],
                       invalidation_price=9.7, initial_risk_pct=4.9)
        altered["technical_context"]["attention_resistance"] = {
            "status":"VERIFIED", "price":12.5,"date":"2026-09-01",
            "source":"asof_180bar_confirmed_pivot","history_points":180}
        another = copy.deepcopy(group)
        research["screen_audit"]["pre_screen_selected"][0]["fundamental_score"] = .99
        engine.add_attention_priorities(another, [altered], [], research)
        second = another[0]["items"][0]
        self.assertEqual(second["attention_rank"], 1)
        self.assertEqual(second["attention_judgement"], explanation)
        self.assertNotEqual(second["attention_resistance_check"]["note"],
                            first["attention_resistance_check"]["note"])

    def test_recent_closing_support_uses_prior_bars_only(self):
        h = [
            {"date":"2026-10-20","open":43.19,"high":45.68,"low":43.15,"close":45.20,"volume":100},
            {"date":"2026-10-21","open":45.22,"high":45.38,"low":44.33,"close":44.46,"volume":100},
            {"date":"2026-10-22","open":44.32,"high":45.40,"low":44.32,"close":44.46,"volume":100},
            {"date":"2026-10-23","open":44.05,"high":47.12,"low":42.90,"close":47.07,"volume":200},
        ]
        result = technical.recent_closing_acceptance(h)
        self.assertEqual(result["support_close_band"], [44.46, 44.46])
        self.assertEqual(result["support_dates"], ["2026-10-21","2026-10-22"])
        self.assertEqual(result["support_low"], 44.32)
        self.assertEqual(result["signal_day_low"], 42.9)
        self.assertTrue(result["intraday_support_broken"])
        self.assertEqual(result["pattern"], "SAME_DAY_SWEEP_RECLAIM")
        h.append({"date":"2026-10-26","open":25,"high":25,"low":25,
                  "close":25,"volume":9999})
        self.assertEqual(result, technical.recent_closing_acceptance(h[:-1]))
        self.assertIsNone(technical.recent_closing_acceptance(h,1)["support_close_band"])

    def test_current_trend_and_recent_signal_rank_not_financials(self):
        a = wait_stock("600001", "INITIATING", ma60=9.5)
        b = wait_stock("600002", "INITIATING", ma60=9.5)
        for row in (a,b):
            row["data_date"] = "2026-10-23"
            row["phase_evidence"] = {"fresh_break": True,
                                      "positive_days_5d":3}
            row["technical_context"].update({
                "volume_ratio_1d_vs_20d":2,
                "close_location_pct":90,
            })
        a["technical_context"]["recent_acceptance"] = {
            "data_date":"2026-10-23","lookback_trading_days":3,
            "pattern":"SAME_DAY_SWEEP_RECLAIM",
            "support_close_band":[9.3,9.3],"support_dates":["2026-10-21","2026-10-22"]}
        b["technical_context"]["recent_acceptance"] = {
            "data_date":"2026-10-23","lookback_trading_days":3,
            "pattern":"LOCAL_SUPPORT_HOLD",
            "support_low":9.55,"support_close_band":[9.6,9.6],
            "support_dates":["2026-10-21","2026-10-22"]}
        research={"trade_date":"2026-10-23","companies":[{"trend_name":"固态电池"}],
                  "screen_audit":{"pre_screen_selected":[
                      {"code":"600001","growth":1,"quality":1,"valuation_match":1},
                      {"code":"600002","growth":0,"quality":0,"valuation_match":0}]}}
        first=engine.dynamic_top5_by_theme([], [a,b], research)[0]
        self.assertEqual([x["code"] for x in first["items"]], ["600002","600001"])
        self.assertEqual(engine.top5_rank_details(a)["risk_basis"],"UNKNOWN_NOT_ZERO")
        self.assertIsNone(engine.top5_rank_details(a)["observation_risk_pct"])
        research["screen_audit"]["pre_screen_selected"].reverse()
        self.assertEqual([x["code"] for x in engine.dynamic_top5_by_theme([], [a,b], research)[0]["items"]],
                         ["600002","600001"])
        self.assertEqual([x["status"] for x in first["items"]], ["WAIT","WAIT"])

    def test_legacy_breakout_gate_and_old_price_stop_cannot_change_rank(self):
        def stock(code, prior_support):
            x=wait_stock(code,"INITIATING",p=10,ma20=9.6,ma60=9.5)
            x["data_date"]="2026-10-23"
            x["phase_evidence"]={
                "fresh_break":True,"return_5d_pct":7,"positive_days_5d":4}
            x["technical_context"].update({
                "volume_ratio_1d_vs_20d":2,"close_location_pct":90,
                "recent_acceptance":{
                    "data_date":"2026-10-23","lookback_trading_days":3,
                    "pattern":prior_support,
                    "support_close_band":[9.1,9.15] if prior_support else None,
                    "support_dates":["2026-10-21","2026-10-22"] if prior_support else [],
                    "intraday_support_broken":prior_support=="SAME_DAY_SWEEP_RECLAIM",
                } if prior_support else {
                    "data_date":"2026-10-23","lookback_trading_days":3,
                    "pattern":"NO_RECENT_CLOSE_SUPPORT"}})
            return x
        sweep=stock("600002","SAME_DAY_SWEEP_RECLAIM")
        old60=stock("600001",None)
        old60.update({"structure_confirmed":True,"setup_type":"BREAKOUT",
                      "entry_zone":[9.95,10.10],
                      "invalidation_price":9.5,"initial_risk_pct":5.94})
        old60["technical_context"].update({
            "prior_60d_high":10,"breakout_level":10,
            "attention_resistance":{
                "status":"VERIFIED","price":11,"date":"2026-06-11",
                "source":"asof_180bar_confirmed_pivot","history_points":180}})
        research={"trade_date":"2026-10-23",
                  "companies":[{"trend_name":"固态电池"}]}
        group=engine.dynamic_top5_by_theme([], [old60,sweep], research)
        self.assertEqual([x["code"] for x in group[0]["items"]],
                         ["600002","600001"])
        key=engine.top5_rank_key(old60)
        old60["technical_context"]["prior_60d_high"]=100
        old60["technical_context"]["breakout_level"]=100
        old60["status"]="READY"
        old60["invalidation_price"]=9.9
        old60["entry_zone"]=[10,10.1]
        self.assertEqual(key,engine.top5_rank_key(old60))
        self.assertNotEqual(old60["status"],sweep["status"])
        self.assertEqual(engine.top5_rank_details(sweep)["recent_support_pattern"],
                         "SAME_DAY_SWEEP_RECLAIM")

    def test_formal_one_point_five_R_gate_remains_separate_from_rank(self):
        self.assertEqual(engine.MIN_UPSIDE_R, 1.5)
        self.assertEqual(engine.MAX_ENTRY_RISK_PCT, 6.0)
        row = wait_stock("600001", "INITIATING", ma60=9.5)
        info = engine.top5_rank_details(row)
        self.assertTrue(info["no_r_assumed"])
        self.assertNotIn("upside_to_resistance_R", info)
        self.assertEqual(info["risk_basis"], "UNKNOWN_NOT_ZERO")

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

    def test_prior_short_support_and_breakout_outrank_60day_plan(self):
        early = wait_stock("600985", "REPAIRING")
        early["data_date"] = "2026-10-09"
        early["phase_evidence"] = {"fresh_break": True,
                                     "return_5d_pct": 6, "positive_days_5d": 3}
        early["technical_context"].update({
            "volume_ratio_1d_vs_20d":2.0,"close_location_pct":86,
            "recent_acceptance":{
                "data_date":"2026-10-09","lookback_trading_days":3,
                "pattern":"SAME_DAY_SWEEP_RECLAIM",
                "support_close_band":[9.4,9.42],
                "support_dates":["2026-10-07","2026-10-08"],
                "intraday_support_broken":True,
                "signal_day_low":9.11}})
        stock_confirmed = wait_stock("002128", "TRANSITION")
        stock_confirmed.update({
            "structure_confirmed": True, "setup_type": "BREAKOUT",
            "data_date": "2026-10-09",
            "entry_zone": [10.0, 10.1], "invalidation_price": 9.5,
            "initial_risk_pct": 5.94
        })
        stock_confirmed["technical_context"]["prior_60d_high"]=10.0
        stock_confirmed["technical_context"]["attention_resistance"] = {
            "status": "VERIFIED", "price": 13.5, "date": "2026-09-22",
            "source": "asof_180bar_confirmed_pivot", "history_points": 180
        }
        research={"trade_date":"2026-10-09",
                  "companies":[{"trend_name":"固态电池"}]}
        top=engine.dynamic_top5_by_theme([], [early, stock_confirmed], research)
        self.assertEqual([i["code"] for i in top[0]["items"]],
                         ["600985", "002128"])
        self.assertEqual(engine.top5_rank_details(early)["follow_signal"],
                         "FRESH_BREAK_AND_RECENT_SWEEP_RECLAIM")
        self.assertTrue(engine.top5_rank_details(early)["ignores_formal_60day_confirmation"])
        self.assertIsNone(engine.top5_rank_details(early)["observation_risk_pct"])
        pick=engine.select_focus_watchlist([], [early, stock_confirmed], research, top)
        self.assertEqual(pick[0]["code"], "600985")
        self.assertEqual(pick[0]["status"], "EARLY_FOCUS_NOT_READY")


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

    def test_confirmed_setup_before_unconfirmed_no_zone(self):
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
        self.assertEqual(by_code["600002"]["attention_rank"], 2)
        self.assertEqual(by_code["600001"]["attention_rank"], 1)
        self.assertIsNone(by_code["600002"]["reference"]["reference_zone"])
        self.assertIn("不是交易买入许可", by_code["600002"]["attention_judgement"])

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
        self.assertIn("短线过热标记参与排序", by_code["600001"]["attention_judgement"])
        self.assertIn("暂缓追涨", by_code["600001"]["attention_resistance_check"]["note"])
        self.assertEqual([x["code"] for x in groups[0]["items"]], old_order)
        self.assertEqual(engine.select_focus_watchlist([], [hot, room], research, groups),
                         old_focus)

    def test_old_resistance_price_not_rank_decider(self):
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
                         ["600001","600002"])
        self.assertEqual(len(group["items"]),2)
        self.assertEqual(engine.MIN_UPSIDE_R,1.5)

    def test_confirmed_setup_prioritized_without_promoting_WAIT(self):
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
                         ["600001","600002"])
        self.assertEqual(len(group["items"]),2)
        self.assertTrue(all(x["status"]=="WAIT" for x in group["items"]))
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

    def test_financial_scores_do_not_change_final_theme_order(self):
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
                         ["600001", "600002"])
        self.assertEqual([x["status"] for x in g["items"]], ["WAIT", "WAIT"])
        audit["pre_screen_selected"].reverse()
        self.assertEqual([x["code"] for x in engine.dynamic_top5_by_theme(
            [], [weak,strong],research)[0]["items"]], ["600001","600002"])
        engine.add_attention_priorities([g], [], [weak, strong], research)
        self.assertEqual([x["attention_rank"] for x in g["items"]], [1, 2])
        self.assertIn("历史阻力和1.5R为交易准入检查",
                      g["items"][0]["attention_resistance_check"]["note"])
        focus = engine.select_focus_watchlist([], [weak, strong], research, [g])
        self.assertEqual(focus[0]["code"], "600001")
        self.assertEqual(focus[0]["status"], "EARLY_FOCUS_NOT_READY")

    def test_entry_position_precedes_volume_when_signal_equal(self):
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
        self.assertEqual([x["code"] for x in g["items"]], ["600001", "600002"])
        self.assertGreater(engine.top5_rank_details(strong)["volume_strength"],
                           engine.top5_rank_details(close)["volume_strength"])

    def test_R_is_for_ready_gate_not_a_top5_ranking_bonus(self):
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
        self.assertEqual(engine.MIN_UPSIDE_R, 1.5)
        self.assertTrue(all(engine.top5_rank_details(row)["no_r_assumed"]
                            for row in (low,high,unknown)))
        self.assertEqual(engine.top5_rank_key(low)[:-1],
                         engine.top5_rank_key(high)[:-1])
        research = {"trade_date": "2026-10-09",
                    "companies": [{"trend_name": "固态电池"}]}
        groups = engine.dynamic_top5_by_theme([], [low, high, unknown], research)
        self.assertEqual({x["code"] for x in groups[0]["items"]},
                         {"600001", "600002", "600003"})
        self.assertEqual([x["code"] for x in groups[0]["items"]][:2],
                         ["600001", "600002"])

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

    def test_future_pivot_invisible_to_rank_but_ready_gate_exists(self):
        row = wait_stock("600001", "INITIATING", ma60=9.5)
        row.update({"data_date": "2026-10-09",
                    "structure_confirmed": True, "setup_type": "BREAKOUT",
                    "entry_zone": [10.02, 10.12], "invalidation_price": 9.7,
                    "initial_risk_pct": 4.15})
        pivot = {"status": "VERIFIED", "price": 11.5,
                 "date": "2026-10-10", "source": "asof_180bar_confirmed_pivot",
                 "history_points": 180}
        row["technical_context"]["attention_resistance"] = pivot
        self.assertIsNone(engine.verified_overhead(
            row["technical_context"],10,"2026-10-09"))
        key=engine.top5_rank_key(row)
        pivot["date"]="2026-10-02"
        self.assertIsNotNone(engine.verified_overhead(
            row["technical_context"],10,"2026-10-09"))
        self.assertEqual(key,engine.top5_rank_key(row))
        self.assertEqual(engine.MIN_UPSIDE_R,1.5)
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
