import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, "scripts")
import intraday_focus_history as h

DATES = ["2026-11-0" + str(i) for i in (2, 3, 4, 5, 6)]


def row(code="002815", dates=DATES, provider="tencent"):
    return {"code": code, "trade_date": dates[-1], "provider": provider,
            "daily": [{"date": d, "main_net_cny": 100, "amount_cny": 1000} for d in dates]}


class FocusHistoryTests(unittest.TestCase):
    def test_valid_partial_windows(self):
        x = h.checked_history(row(), "sz002815", DATES, "FORMAL_FROZEN_ADMISSION")
        self.assertEqual(x["coverage"], "PARTIAL")
        self.assertEqual(x["windows"]["5"]["net_pct"], 10)
        self.assertEqual(x["windows"]["20"]["status"], "UNKNOWN")

    def test_reject_wrong_identity_and_date_and_gap(self):
        for bad in (row("002816"), {**row(), "trade_date": "2026-11-05"},
                    {**row(), "daily": [*row()["daily"][:-1], row()["daily"][0]]}):
            with self.assertRaises(ValueError):
                h.checked_history(bad, "sz002815", DATES, "FORMAL_FROZEN_ADMISSION")

    def test_frozen_exact_formal_sha_and_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/"research/trend_buy_candidates").mkdir(parents=True)
            admission = {"trade_date": DATES[-1], "fund_flow": {"trade_date": DATES[-1],
                "groups": [{"status": "VERIFIED", "provider": "tencent", "stocks": {"002815": row()}}]}}
            raw = json.dumps(admission).encode()
            (root/"research/trend_buy_candidates/latest.json").write_bytes(raw)
            formal_path = root/"research/trend_buy_formal_result.json"
            formal = {"trade_date": DATES[-1], "run_id": "paired",
                "fresh_mainline_provenance": {"company_research_admission_sha": h.blob_sha(raw)}}
            formal_path.write_text(json.dumps(formal))
            result = h.frozen_histories(root, DATES[-1], ["sz002815", "sh600105"], DATES, "paired")
            self.assertEqual(list(result), ["sz002815"])
            self.assertEqual(result["sz002815"]["admission_blob_sha"], h.blob_sha(raw))
            self.assertEqual(h.frozen_histories(root, DATES[-1], ["sz002815"], DATES, "wrong"), {})
            formal["fresh_mainline_provenance"]["company_research_admission_sha"] = "wrong"
            formal_path.write_text(json.dumps(formal))
            self.assertEqual(h.frozen_histories(root, DATES[-1], ["sz002815"], DATES, "paired"), {})

    def test_actual_checked_in_pair_replay(self):
        root = Path(__file__).resolve().parents[1]
        formal = h.load(root/"research/trend_buy_formal_result.json")
        admission = h.load(root/"research/trend_buy_candidates/latest.json")
        if formal["trade_date"] != admission["trade_date"]:
            self.skipTest("current formal/admission are not paired")
        # Replay only the actual recorded dates; production uses the exchange calendar.
        group = next(g for g in admission["fund_flow"]["groups"] if g["status"] == "VERIFIED")
        code, stock = next(iter(group["stocks"].items()))
        sym = ("sh" if code.startswith("6") else "sz") + code
        dates = [r["date"] for r in stock["daily"]]
        result = h.frozen_histories(root, formal["trade_date"], [sym], dates, formal["run_id"])
        self.assertIn(sym, result)
        self.assertEqual(result[sym]["daily"][-1]["date"], formal["trade_date"])
        self.assertEqual(len(result[sym]["daily"]), len(dates))

    def test_completed_history_excludes_current_and_validates_amount(self):
        code = "002815"
        quotes = {d: {"close": 10, "amount": 1000} for d in DATES}
        dates = DATES + ["2026-11-09"]
        lines = [d+",100,-40,-60,40,60,10,-4,-6,4,6,10,0" for d in dates]
        response = {"rc":0,"data":{"code":code,"market":0,"klines":lines}}
        with patch.object(h.frozen,"actual_quotes",return_value=quotes), patch.object(h.probe,"get",
            return_value=(json.dumps(response),dt.datetime(2026,11,9,10,37,tzinfo=h.probe.TZ))):
            x=h.fetch_completed_history("sz"+code,DATES)
        self.assertEqual(len(x["daily"]),5)
        self.assertEqual(x["daily"][-1]["date"],DATES[-1])
        self.assertEqual(x["provider"],"eastmoney")

    def test_no_cross_provider_mixing_and_failure_isolation(self):
        old = h.checked_history(row(), "sz002815", DATES, "FORMAL_FROZEN_ADMISSION")
        with patch.object(h,"fetch_completed_history",side_effect=OSError("failed")):
            self.assertEqual(h.resolve_history("sz002815",DATES,"2026-11-09",{"sz002815":old},{}),old)
            with self.assertRaisesRegex(ValueError,"HISTORY_SOURCE_UNAVAILABLE"):
                h.resolve_history("sh600105",DATES,"2026-11-09",{},{})

    def test_complete_frozen_avoids_network(self):
        dates = [(dt.date(2026,10,1)+dt.timedelta(days=i)).isoformat() for i in range(20)]
        old = h.checked_history(row(dates=dates),"sz002815",dates,"FORMAL_FROZEN_ADMISSION")
        with patch.object(h,"fetch_completed_history") as fetch:
            self.assertEqual(h.resolve_history("sz002815",dates,"2026-10-21",{"sz002815":old},{}),old)
            fetch.assert_not_called()

    def test_same_day_cache_only(self):
        old = h.checked_history(row(provider="eastmoney"),"sz002815",DATES,"COMPLETED_SESSION_FETCH")
        prev={"trade_date":"2026-11-09","expected_baseline_date":DATES[-1],"stocks":{"sz002815":{"historical_fund_flow":{"data":old}}}}
        self.assertIsNotNone(h.cached_history(prev,"sz002815",DATES,"2026-11-09"))
        self.assertIsNone(h.cached_history(prev,"sz002815",DATES,"2026-11-10"))

    def test_archive_keeps_legacy_and_only_public_valid_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/"research").mkdir()
            path=root/"research/intraday_crossday_archive.json"
            old={"schema_version":1,"result_kind":"a_share_intraday_crossday_archive","days":[
                {"trade_date":"2026-11-05","trends":{},"stocks":{"002815":{"price_behavior":"normal","scan_at":"old","holding_action":"hold"}}}]}
            path.write_text(json.dumps(old))
            previous={"trade_date":"2026-11-06","run_id":"run","slot":"2026-11-06T14:27:00+08:00","stocks":{
                "sz002815":{"core_gate":"CORE_VALID","components":{"tencent_quote":{"data":{
                    "quality":"LIVE","quote_at":"2026-11-06T14:27:30+08:00","price":10,"change_pct":1,"symbol":"sz002815"}}},
                    "metrics":{"same_time_volume_ratio":1.1},"cost":9,"position":100},
                "sh600105":{"core_gate":"QUOTE_UNAVAILABLE"}}}
            archive, context, status=h.archive_context(root,previous,"2026-11-09",["sz002815","sh600105"])
            self.assertEqual(status,"AVAILABLE")
            self.assertEqual(archive["days"][0],old["days"][0])
            self.assertEqual(len(context["sz002815"]),2)
            self.assertEqual(context["sh600105"],[])
            observation=archive["days"][1]["focus_stocks"]["002815"]
            self.assertEqual(observation["basis"],"LAST_VALID_FOCUS_SCAN_NOT_OFFICIAL_CLOSE")
            self.assertNotIn("cost",observation)
            self.assertNotIn("position",observation)
            self.assertNotIn("holding_action",context["sz002815"][0]["legacy_research"])
            self.assertEqual(json.loads(path.read_text()),old)

    def test_calendar_sessions_and_future_exclusion(self):
        days=tuple(dt.date.fromisoformat(d) for d in DATES+["2026-11-09"])
        self.assertEqual(h.session_dates(days,DATES[-1]),DATES)
        with self.assertRaises(ValueError):
            h.session_dates(days,"2026-11-07")


if __name__ == "__main__":
    unittest.main()
