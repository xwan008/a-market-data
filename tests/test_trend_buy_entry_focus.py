"""Early trend watch candidates: one per researched sector, never a READY."""
import importlib.util
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("trend_entry",ROOT/"scripts"/"trend_buy_engine.py")
engine=importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


def item(code, sector, price, ma20, ma60, support, market="候选趋势",
         trans="SUPPORTED", vol1=1.2, rel=1.0, confirmed=False):
    return {
        "code":code,"company_name":"合成"+code,"trend_name":sector,
        "status":"WAIT","wait_reason":"WAIT_CONFIRMATION",
        "current_price":price,"market_state":market,
        "transmission":trans,"structure_confirmed":confirmed,
        "technical_context":{
            "ma20":ma20,"ma60":ma60,"support_invalidation":support,
            "volume_ratio_1d_vs_20d":vol1,
            "volume_ratio_5d_vs_20d":1.07,
            "relative_strength_20d_vs_market_pct":rel,
            "ma20_slope_5d_pct":0.1,"close_location_pct":65,
            "higher_low":True,
        },
    }


def research(names):
    return {"trade_date":"2026-10-09","companies":[{"trend_name":n} for n in names],
            "screen_audit":{"pre_screen_selected":[]}}


class EarlyFocusTests(unittest.TestCase):
    def test_one_per_sector_even_unconfirmed_gold(self):
        wait=[
            item("001337","黄金",47.03,48.954,45.8845,45.2,vol1=.7,rel=-3),
            item("600489","黄金",22.95,23.7695,23.5001,22.55,vol1=1.3,rel=2),
            item("002128","煤炭",28.8,28.5,27.7,27.4,confirmed=True),
        ]
        picks=engine.select_focus_watchlist([],wait,research(["黄金","煤炭"]))
        self.assertEqual(len(picks),2)
        gold=next(x for x in picks if x["trend_name"]=="黄金")
        self.assertEqual(gold["code"],"600489")
        self.assertEqual(gold["status"],"EARLY_FOCUS_NOT_READY")
        self.assertTrue(gold["not_buy_order"])
        self.assertIn("板块趋势仍待确认",gold["remaining_blocks_to_ready"])
        self.assertIsNotNone(gold["reference"]["reference_trigger_price"])

    def test_far_60day_breakout_doesnt_drive_early_trigger(self):
        gold=item("001337","黄金",47.03,48.954,45.8845,45.2)
        gold.update({"entry_zone":[59.168,60.526],"invalidation_price":58.164,
                     "setup_type":"BREAKOUT"})
        p=engine.select_focus_watchlist([], [gold], research(["黄金"]))[0]
        self.assertEqual(p["code"],"001337")
        self.assertAlmostEqual(p["reference"]["reference_trigger_price"],48.954,places=3)
        self.assertLess(p["reference_trigger_distance_pct"],5)
        self.assertTrue(p["not_buy_order"])

    def test_confirmed_stock_plan_beats_unconfirmed_but_high_volume_candidate(self):
        earlier=item("002128","煤炭",28.8,28.5,27.7,27.557,
                     vol1=.85,rel=-1,confirmed=True)
        earlier.update({"setup_type":"PULLBACK","entry_zone":[28.656,29.146],
                        "invalidation_price":27.557,"initial_risk_pct":5.45})
        volume=item("601918","煤炭",11.58,10.752,10.3,10.35,
                    vol1=1.9,rel=4,confirmed=False)
        chosen=engine.select_focus_watchlist([], [volume,earlier], research(["煤炭"]))[0]
        self.assertEqual(chosen["code"],"002128")
        self.assertEqual(chosen["reference"]["stage"],"STOCK_CONFIRMED_SECTOR_PENDING")
        self.assertEqual(chosen["reference"]["reference_zone"],[28.656,29.146])
        self.assertTrue(chosen["not_buy_order"])

    def test_no_close_stop_must_not_generate_buy_zone(self):
        gold=item("600489","黄金",22.95,23.77,23.50,18.3)
        p=engine.select_focus_watchlist([], [gold], research(["黄金"]))[0]
        self.assertEqual(p["code"],"600489")
        self.assertIsNone(p["reference"]["reference_zone"])
        self.assertIsNone(p["reference"]["invalidation_price"])
        self.assertIn("尚缺可靠",p["remaining_blocks_to_ready"][2])

    def test_company_without_ma_still_in_research_not_ready(self):
        x=item("123456","矿业",11,10.9,10.7,10.5)
        x["technical_context"]={}
        p=engine.select_focus_watchlist([], [x], research(["矿业"]))[0]
        self.assertEqual(p["status"],"NO_CURRENT_BUY_OPPORTUNITY")
        self.assertIsNone(p["code"])

    def test_no_wait_and_ready(self):
        p=engine.select_focus_watchlist([],[],research(["黄金"]))[0]
        self.assertEqual(p["status"],"NO_CURRENT_BUY_OPPORTUNITY")
        self.assertEqual(engine.select_focus_watchlist([{"code":"600000","trend_name":"黄金","status":"READY","current_price":10,"market_state":"趋势确认","structure_confirmed":True,"setup_type":"BREAKOUT","entry_zone":[10,10.1],"invalidation_price":9.6,"initial_risk_pct":4}],[],research(["黄金"]))[0]["status"],"CURRENT_READY_FOCUS")

    def test_no_one_dropped_and_more_flow_signals_rank_higher(self):
        a=item("000001","工业",10,9.7,9.5,9.3,vol1=.5,rel=-5)
        a["status"]="DROP"
        b=item("000002","工业",10,10.1,9.8,9.2,vol1=1.2,rel=2)
        p=engine.select_focus_watchlist([], [b], research(["工业"]))[0]
        self.assertEqual(p["code"],"000002")
        self.assertGreaterEqual(p["early_signal_count"],3)


if __name__=="__main__":
    unittest.main()
