"""Continuous as-of quality evidence regression: never inferred from ordinal ranks."""
import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))

from trend_buy_research_quality import verified_quality_for_selected
from prepare_trend_buy_candidates import F10_SOURCE

ASOF="2026-11-17"
PERIOD="2026-09-30"


def fixture(tmp,*,future=False,stale_history=False):
    root=Path(tmp)
    (root/"data/history_shards").mkdir(parents=True)
    ending=date.fromisoformat(ASOF)
    days=[ending-timedelta(days=i) for i in range(125)]
    days=[day.isoformat() for day in sorted(days) if day.weekday()<5][-75:]
    companies=[]
    histories={}
    records={}
    for i,(code,growth,ocf) in enumerate([
        ("600001",36.0,3.3),
        ("600002",13.5,2.3),
        ("600003",20.0,2.9),
        ("600004",-10.0,-.5),
    ]):
        price=100.
        bars=[{"date":day,"close":price,
               "volume":1000.} for day in days]
        if stale_history and code=="600004":
            bars=bars[:-1]
        histories[code]={"history":bars}
        companies.append({"code":code,"industry_code":"S370403",
                          "report_date":PERIOD,"price":price,
                          "operating_cashflow_per_share":ocf})
        records[code]={"source_report":F10_SOURCE,
                       "report_date":PERIOD,
                       "notice_date":"2026-10-30",
                       "update_date":"2026-11-18" if future and code=="600002" else "2026-11-13",
                       "deduct_net_profit_yoy":growth}
    (root/"data/history_shards/6000.json").write_text(
        json.dumps({"stocks":histories}),encoding="utf-8")
    finance={"records":records}
    signals=[{"trend_name":"线下药店","industry_codes":["S370403"]}]
    return companies,finance,signals,root


class ContinuousResearchQualityTests(unittest.TestCase):
    def test_research_quality_is_continuous_based_on_f10_and_10_20_60d(self):
        with tempfile.TemporaryDirectory() as d:
            selected,finance,signals,root=fixture(d)
            scored=verified_quality_for_selected(
                selected,finance,ASOF,signals,root)
            self.assertTrue(all(x["status"]=="VERIFIED" for x in scored.values()))
            self.assertGreater(scored["600001"]["score"],scored["600002"]["score"])
            self.assertLess(scored["600004"]["score"],scored["600002"]["score"])
            # All identical price histories: every stock gets the same 0.5
            # trend percentile, making the observed financial gap auditable.
            self.assertEqual(scored["600001"]["components"]["peer_percentiles"]["20"],.5)
            self.assertAlmostEqual(scored["600001"]["score"],70.6667,places=3)
            self.assertAlmostEqual(scored["600002"]["score"],55.6667,places=3)
            selected[0]["model_rank"]=99
            selected[1]["model_rank"]=1
            self.assertEqual(verified_quality_for_selected(
                selected,finance,ASOF,signals,root),scored)

    def test_future_f10_or_stale_bar_never_receives_a_quality_score(self):
        with tempfile.TemporaryDirectory() as d:
            selected,finance,signals,root=fixture(d,future=True,stale_history=True)
            scored=verified_quality_for_selected(
                selected,finance,ASOF,signals,root)
            self.assertEqual(scored["600002"]["status"],
                             "INCOMPLETE_ASOF_RESEARCH_QUALITY")
            self.assertIsNone(scored["600002"]["score"])
            self.assertIsNone(scored["600004"]["score"])


if __name__=="__main__":
    unittest.main()
