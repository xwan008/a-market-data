import copy
import datetime as dt
import unittest
from unittest.mock import patch
from top1_fund_flow import collect, normalize, expected_dates


class FundEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.days = [(dt.date(2026, 10, 26) + dt.timedelta(days=i)).isoformat()
                     for i in range(30) if (dt.date(2026, 10, 26) + dt.timedelta(days=i)).weekday() < 5][-20:]
        self.c = {"code": "603078", "close": 10, "change_pct": 1}
        self.f = [{"日期": d, "收盘价": 10, "涨跌幅": 1,
                   "主力净流入-净额": 100, "主力净流入-净占比": 10,
                   "大单净流入-净额": 40, "超大单净流入-净额": 60}
                  for d in self.days]
        self.q = [{"日期": d, "股票代码": "603078", "收盘": 10, "涨跌幅": 1,
                   "成交额": 1000, "换手率": 2} for d in self.days]
        self.packet = {"trade_date": self.days[-1], "calendar": self.days,
                       "industry_code": "S270601", "candidates": [self.c]}

    def test_weighted_windows(self):
        self.q[-1]["成交额"] = 2000
        self.f[-1]["主力净流入-净占比"] = 5
        r = normalize(self.f, self.q, self.days, self.c)["windows"]
        self.assertEqual(r["20"]["net_yuan"], 2000)
        self.assertAlmostEqual(r["5"]["net_to_amount_pct"], 500 / 6000 * 100)
        self.assertEqual(r["5"]["turnover_sum_pct"], 10)

    def test_stale_missing_and_duplicate(self):
        for f in (self.f[:-1], self.f[1:], self.f + self.f[-1:]):
            with self.subTest(n=len(f)):
                with self.assertRaises(ValueError):
                    normalize(f, self.q, self.days, self.c)

    def test_conflicts(self):
        for target, field, value in (("f", "收盘价", 11), ("f", "涨跌幅", 2),
                                      ("f", "主力净流入-净占比", 25),
                                      ("f", "大单净流入-净额", 1),
                                      ("q", "股票代码", "603931"),
                                      ("q", "成交额", 0),
                                      ("q", "换手率", float("nan"))):
            with self.subTest(field=field):
                f, q = copy.deepcopy(self.f), copy.deepcopy(self.q)
                (f if target == "f" else q)[-1][field] = value
                with self.assertRaises(ValueError):
                    normalize(f, q, self.days, self.c)

    def test_future_rows_not_used(self):
        f = self.f + [dict(self.f[-1], 日期="2026-12-01")]
        self.assertEqual(len(normalize(f, self.q, self.days, self.c)["rows"]), 20)

    def test_partial_group_not_comparable(self):
        p = copy.deepcopy(self.packet)
        p["candidates"].append(dict(self.c, code="603931"))
        def fetcher(c, dates):
            if c["code"] == "603931":
                raise RuntimeError("unavailable")
            return self.f, self.q, "fixture"
        with patch("top1_fund_flow.time.sleep"):
            r = collect(p, fetcher)
        self.assertEqual(r["coverage"], 1)
        self.assertFalse(r["comparable"])
        self.assertFalse(r["production_eligible"])
        self.assertFalse(r["point_in_time_verified"])

    def test_calendar_and_roster(self):
        with self.assertRaises(ValueError):
            expected_dates(dict(self.packet, calendar=self.days[:-1]))
        with self.assertRaises(ValueError):
            collect(dict(self.packet, candidates=[self.c, self.c]))


if __name__ == "__main__":
    unittest.main()
