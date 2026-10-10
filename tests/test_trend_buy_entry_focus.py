"""An attention pick is a credible near-entry WAIT, not best-looking company."""
import importlib.util
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("trend_entry",ROOT/"scripts"/"trend_buy_engine.py")
engine=importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


def item(code,sector,price,zone=None,stop=None,confirmed=False,market="候选趋势",
         trans="SUPPORTED",risk=3.5,wait_reason="WAIT_CONFIRMATION",setup="BREAKOUT"):
    return {"code":code,"company_name":"测试"+code,"trend_name":sector,
            "status":"WAIT","wait_reason":wait_reason,"current_price":price,
            "entry_zone":zone,"invalidation_price":stop,"initial_risk_pct":risk,
            "market_state":market,"transmission":trans,"structure_confirmed":confirmed,
            "setup_type":setup}


def research(sectors,scores=None):
    scores=scores or {}
    return {"trade_date":"2026-10-09",
            "companies":[{"trend_name":name} for name in sectors],
            "screen_audit":{"pre_screen_selected":[{"code":k,"score":v} for k,v in scores.items()]}}


class EntryFocusTests(unittest.TestCase):
    def test_far_breakout_cannot_beat_near_but_unconfirmed_ma60(self):
        gold=[
            item("001337","黄金",47.03,[59.168,60.526],58.164),
            item("600489","黄金",22.95,None,None),
        ]
        picks=engine.select_focus_watchlist([],gold,research(["黄金"],{"001337":.784,"600489":.547}))
        self.assertEqual(picks[0]["status"],"NO_NEAR_TERM_SETUP")
        self.assertIsNone(picks[0]["code"])

    def test_already_confirmed_structure_can_be_closest_when_sector_candidate(self):
        coal=[
            item("002128","煤炭",28.8,[28.656,29.146],27.557,confirmed=True,setup="PULLBACK",risk=5.45),
            item("600546","煤炭",13.9,[14.569,14.903],14.322,confirmed=False),
        ]
        picks=engine.select_focus_watchlist([],coal,research(["煤炭"],{"002128":.61,"600546":.91}))
        self.assertEqual(picks[0]["status"],"WATCH_ONLY")
        self.assertEqual(picks[0]["code"],"002128")
        self.assertIn("上游板块尚未趋势确认",picks[0]["blocking_conditions"])

    def test_company_score_does_not_beat_nearer_valid_entry(self):
        wait=[
            item("000001","固态电池",20,[22.1,22.5],21.2,market="趋势确认",risk=4),
            item("000002","固态电池",20,[20.4,20.8],19.9,market="趋势确认",risk=4),
        ]
        best=engine.select_focus_watchlist([],wait,research(["固态电池"],{"000001":.96,"000002":.35}))[0]
        self.assertEqual(best["code"],"000002")
        self.assertLess(best["distance_to_entry_zone_pct"],3)

    def test_no_wait_and_ready_do_not_force_focus(self):
        a=engine.select_focus_watchlist([],[],research(["黄金"]))[0]
        self.assertEqual(a["status"],"NO_QUALIFIED_WAIT")
        self.assertEqual(engine.select_focus_watchlist([{"code":"1"}],[],research(["黄金"])),[])

    def test_unconfirmed_sector_and_stock_cannot_fake_imminent_entry(self):
        w=[item("000001","煤炭",10,[10.1,10.3],9.8,confirmed=False,market="候选趋势")]
        self.assertEqual(engine.select_focus_watchlist([],w,research(["煤炭"]))[0]["status"],"NO_NEAR_TERM_SETUP")


if __name__=="__main__":
    unittest.main()
