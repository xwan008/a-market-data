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

    def test_only_five_per_theme_across_industries(self):
        rows=[wait_stock("%06d"%(600001+i),"REPAIRING",support=9.4)
              for i in range(9)]
        result=engine.dynamic_top5_by_theme([], rows,
            {"trade_date":"2026-10-09","companies":[{"trend_name":"固态电池"}]})
        self.assertEqual(len(result[0]["items"]),5)
        self.assertEqual(result[0]["qualified_opportunity_count"],9)

    def test_no_forced_nominee(self):
        rows=[wait_stock("002074","COOLING")]
        research={"trade_date":"2026-10-09","companies":[{"trend_name":"固态电池"}]}
        g=engine.dynamic_top5_by_theme([],rows,research)
        self.assertEqual(g[0]["items"],[])
        self.assertEqual(engine.select_focus_watchlist([],rows,research,g)[0]["status"],
                         "NO_CURRENT_BUY_OPPORTUNITY")

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
