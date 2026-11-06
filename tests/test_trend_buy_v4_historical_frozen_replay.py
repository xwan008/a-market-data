"""No lookahead in frozen asof Git publications or future outcome use."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"experiments"))
spec=importlib.util.spec_from_file_location(
    "v4hist",ROOT/"experiments/trend_buy_v4_historical_frozen_replay.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class V4HistoricalTests(unittest.TestCase):
    def test_earliest_real_published_formal_not_late_rewrite(self):
        lines=("late\t2026-11-04T09:00:00+00:00\n"
               "first\t2026-11-03T11:01:00+00:00\n"
               "rankless\t2026-11-03T10:00:00+00:00\n")
        def show(root,sha,path):
            if sha=="rankless":
                return {"trade_date":"2026-11-03","status":"COMPLETE",
                        "top5_by_theme":[]}
            return {"trade_date":"2026-11-03","status":"COMPLETE",
                    "top5_by_theme":[{"trend_name":"游戏","items":[{"code":"002517"}]}]}
        with patch.object(mod,"git",return_value=lines),patch.object(
            mod,"show_json",side_effect=show):
            items=mod.first_published_rankings(ROOT,{"2026-11-03"})
        self.assertEqual(items["2026-11-03"]["sha"],"first")

    def test_unpublished_or_out_of_range_date_excluded(self):
        lines=("late\t2026-11-08T11:00:00+00:00\n")
        with patch.object(mod,"git",return_value=lines),patch.object(
            mod,"show_json",return_value={
                "trade_date":"2026-11-03","status":"COMPLETE",
                "top5_by_theme":[{"items":[{"code":"000001"}]}]}):
            items=mod.first_published_rankings(ROOT,{"2026-11-03"})
        self.assertEqual(items,{})

if __name__=="__main__":
    unittest.main()
