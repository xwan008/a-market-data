"""Strict-history mainboard identity replay tests; no fabricated archived concepts."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from backtest_hotspot_identity_asof import (
    digest, sector_identity, industry_quote_parity, routing_contract,
    replay_identity_layer)
from backtest_sector_discovery_asof import load_days


class IdentityReplayTest(unittest.TestCase):
    def test_identity_label_explicitly_excludes_model_discovery(self):
        row={"id":"industry:S640701","name":"机器人","kind":"industry"}
        identity=sector_identity("2026-09-14",[row])
        self.assertEqual(identity["identities"][0]["board_code"],"S640701")
        self.assertEqual(identity["identities"][0]["industry_codes"],["S640701"])
        self.assertIn("NOT_FROZEN_ORIGINAL_DRIVER",identity["proof_scope"])
        self.assertNotIn("market_state",identity["identities"][0])

    def test_market_metric_mismatch_is_detected_not_swallowed(self):
        old=[{"id":"industry:S640701","member_count":6,
              "usable_count":6,"coverage":1,
              "advance_ratio":.9,"median_1d_pct":1.5}]
        new=[{"hotspot_id":"industry:S640701","member_count":6,
              "usable_count":6,"quote_coverage":1,
              "r1_advance_ratio":.5,"r1_median_pct":1.5,
              "evaluation_status":"READY_FOR_INDEPENDENT_STATE_REVIEW"}]
        report=industry_quote_parity(old,new)
        self.assertEqual(report["mismatch_count"],1)
        self.assertEqual(report["mismatch_examples"][0]["field"],"advance_ratio")

    def test_contract_industry_only_no_stocks_or_state_changes(self):
        day="2026-10-09"
        ids=sector_identity(day,[{"id":"industry:S640701","name":"机器人"}])
        companies={"600001":{"mapping_status":"mapped","industry_code":"S640701"}}
        quotes={"trade_date":day,"market_status":"closed",
                "stocks":{"600001":{"name":"股票","confidence":"high","change_pct":-2}}}
        structure={"reference_trade_date":day,"companies":{"600001":{}}}
        result=routing_contract(day,{"companies":companies},quotes,structure,ids)
        self.assertEqual(result["result"],"CODE_ONLY_NO_NEW_MEMBERS_NO_STATE_CHANGE")

    def test_snapshot_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"2026-09-14"
            root.mkdir()
            (root/"latest.json").write_text(json.dumps({
                "trade_date":"2026-09-15","market_status":"closed","stocks":{}}))
            (root/"company_industry_index.json").write_text(json.dumps({
                "companies":{"600001":{"industry_code":"S640701"}}}))
            with self.assertRaisesRegex(ValueError,"ASOF_DATE_MISMATCH"):
                load_days(d,{"snapshots":[{
                    "trade_date":"2026-09-14","commit":"immutable"}]})

    def test_missing_historical_dataset_fails_instead_of_backdating_today(self):
        with tempfile.TemporaryDirectory() as d:
            manifest={"snapshots":[{"trade_date":"2026-09-14","commit":"not-a-file"}]}
            with self.assertRaises(FileNotFoundError):
                replay_identity_layer(d,manifest)


if __name__=="__main__":
    unittest.main()
