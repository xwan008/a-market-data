"""Shadow-only secondary entry formation tests."""
import importlib.util
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("v2_shapes",
    ROOT/"experiments/trend_buy_v2_secondary_entries_shadow.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
ASOF="2026-11-05"


def series():
    rows=[]
    # all dated strictly prior to the as-of bar, with adequate history.
    for i in range(30):
        date="2026-09-%02d"%(i+1)
        rows.append({"date":date,"open":10,"high":10.2,"low":9.8,
                     "close":10,"volume":100})
    rows[-3]={"date":"2026-11-02","open":10.6,"high":10.75,"low":10.52,
              "close":10.68,"volume":120}
    rows[-2]={"date":"2026-11-03","open":10.7,"high":10.92,"low":10.69,
              "close":10.85,"volume":130}
    rows[-1]={"date":ASOF,"open":10.93,"high":11.14,"low":10.91,
              "close":11.1,"volume":280}
    return rows


class ShapeTests(unittest.TestCase):
    def test_non_future_trade_structure_only(self):
        x=mod.detect(series(),ASOF,11.1)
        self.assertTrue(x["trend_follow"])
        self.assertIsNone(x["trade_entry_zone"])
        self.assertIsNone(x["trade_invalidation_price"])
        self.assertIsNone(x["trade_R"])

    def test_future_big_bar_does_not_change_today_signal(self):
        bars=series()
        before=mod.detect(bars,ASOF,11.1)
        bars.append({"date":"2026-11-06","open":20,"close":24,
                     "high":25,"low":19,"volume":10000})
        after=mod.detect(bars,ASOF,11.1)
        self.assertEqual(before,after)

    def test_last_bar_missing_or_adjusted_mismatch_fails(self):
        bars=series()
        with self.assertRaisesRegex(ValueError,"missing_completed_asof_bar"):
            mod.detect(bars,"2026-11-04",11.1)
        with self.assertRaisesRegex(ValueError,"frozen_price_history_basis_mismatch"):
            mod.detect(bars,ASOF,8.1)

    def test_consolidation_break_has_no_executable_stop(self):
        bars=series()
        for i in range(-7,-1):
            bars[i]={"date":"2026-10-%02d"%(20+i+7),
                     "open":10.1,"high":10.3,"low":9.96,
                     "close":10.1,"volume":80}
        bars[-1]={"date":ASOF,"open":10.4,"high":10.66,
                  "low":10.35,"close":10.62,"volume":200}
        x=mod.detect(bars,ASOF,10.62)
        self.assertTrue(x["consolidation_rebreak"])
        self.assertIsNone(x["trade_R"])
        self.assertIsNone(x["trade_invalidation_price"])

    def test_missing_volume_does_not_promote(self):
        bars=series()
        bars[-1]["volume"]=None
        with self.assertRaisesRegex(ValueError,"invalid_ohlcv"):
            mod.detect(bars,ASOF,11.1)

if __name__=="__main__":
    unittest.main()
