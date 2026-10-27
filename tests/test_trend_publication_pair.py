import copy
import importlib.util
import pathlib
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "validate_trend_publication_pair.py"
spec = importlib.util.spec_from_file_location("publish_pair", SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture():
    registry = {
        "schema_version": 2, "result_kind": "a_share_trend_registry",
        "status": "COMPLETE", "trade_date": "2026-10-13",
        "scan_audit": {"full_market_scan_completed": True, "state_migration_gate": {
            "mode": "full_close", "current_trade_date": "2026-10-13"}},
        "trends": [
            {"trend_name": "黄金", "episode_id": "黄金#2026-10-13", "in_new_position_priority": True,
             "market_state": "候选趋势", "trend_state": "T1",
             "lifecycle_status": "有效",
             "industry_codes": ["S240401"], "industry_names": ["黄金"]},
            {"trend_name": "其他", "episode_id": "其他#2026-10-13", "in_new_position_priority": False,
             "market_state": "候选趋势", "trend_state": "T1",
             "lifecycle_status": "有效",
             "industry_codes": ["S000000"], "industry_names": ["示例"]}
        ]
    }
    handoff = {
        "schema_version": 1, "result_kind": "a_share_trend_handoff",
        "trade_date": "2026-10-13",
        "signals": [
            {"rank": 1, "trend_name": "黄金", "market_state": "候选趋势",
             "trend_state": "T1", "industry_codes": ["S240401"],
             "industry_names": ["黄金"]}
        ]
    }
    return registry, handoff


class PublicationPairTests(unittest.TestCase):
    def test_valid_pair(self):
        self.assertEqual(m.validate(*fixture()), [])

    def test_cutover_is_not_a_production_mode(self):
        r, h = fixture()
        r["scan_audit"]["state_migration_gate"]["mode"] = "v2_cutover"
        self.assertIn("migration_gate_missing", m.validate(r, h))

    def test_observation_persisted_without_priority(self):
        r, h = fixture()
        r["trends"][1]["market_state"] = "观察"
        self.assertEqual(m.validate(r, h), [])
        r["trends"][1]["in_new_position_priority"] = True
        self.assertIn("observation_in_priority", m.validate(r, h))

    def test_incomplete_scan_rejected(self):
        r, h = fixture()
        r["scan_audit"]["full_market_scan_completed"] = False
        self.assertIn("full_market_scan_incomplete", m.validate(r, h))

    def test_no_confirmed_industry_means_valid_empty_handoff(self):
        r, h = fixture()
        r["trade_date"] = h["trade_date"] = "2026-10-27"
        r["scan_audit"]["state_migration_gate"]["current_trade_date"] = "2026-10-27"
        r["trends"][0]["in_new_position_priority"] = False
        h["signals"] = []
        self.assertEqual(m.validate(r, h), [])
        # Empty handoff is valid only when no industry was eligible.
        r["trends"][0]["in_new_position_priority"] = True
        self.assertIn("only_confirmed_in_priority", m.validate(r, h))
        self.assertIn("priority_names_or_order_mismatch", m.validate(r, h))

    def test_old_handoff_is_rejected(self):
        r, h = fixture()
        h["trade_date"] = "2026-10-12"
        self.assertIn("trade_date_mismatch", m.validate(r, h))

    def test_ranking_and_route_are_consistent(self):
        r, h = fixture()
        h["signals"][0]["industry_codes"] = ["S999999"]
        self.assertIn("黄金:industry_codes_mismatch", m.validate(r, h))
        h["signals"][0]["rank"] = 2
        self.assertIn("黄金:nonsequential_rank", m.validate(r, h))

    def test_priority_inclusion_and_order(self):
        r, h = fixture()
        r["trends"][0]["in_new_position_priority"] = False
        self.assertIn("priority_names_or_order_mismatch", m.validate(r, h))

    def test_invalidated_industry_never_handed_off(self):
        r, h = fixture()
        r["trends"][0]["lifecycle_status"] = "已失效"
        self.assertIn("黄金:invalidated_theme_handed_off", m.validate(r, h))

    def test_prospective_handoff_requires_confirmation_and_verified_core_route(self):
        r, h = fixture()
        r["trade_date"] = h["trade_date"] = "2026-10-27"
        r["scan_audit"]["state_migration_gate"]["current_trade_date"] = "2026-10-27"
        self.assertIn("only_confirmed_in_priority", m.validate(r, h))
        r["trends"][0]["market_state"] = "趋势确认"
        h["signals"][0]["market_state"] = "趋势确认"
        r["trends"][0]["industry_codes"] = ["S240401", "S240402"]
        r["trends"][0]["industry_names"] = ["黄金", "其他贵金属"]
        r["trends"][0]["industry_assessments"] = [
            {"industry_code": "S240401", "industry_name": "黄金",
             "market_state": "趋势确认", "benefit_level": "DIRECT"},
            {"industry_code": "S240402", "industry_name": "其他贵金属",
             "market_state": "观察", "benefit_level": "RELATED"},
        ]
        self.assertEqual(m.validate(r, h), [])
        h["signals"][0]["industry_codes"] = ["S240401", "S240402"]
        h["signals"][0]["industry_names"] = ["黄金", "其他贵金属"]
        self.assertIn("黄金:unconfirmed_industry_route", m.validate(r, h))
        h["signals"][0]["industry_codes"] = ["S240401"]
        h["signals"][0]["industry_names"] = ["黄金"]
        r["trends"][0]["industry_assessments"][1].update(
            market_state="趋势确认", benefit_level="DIRECT")
        self.assertIn("黄金:confirmed_route_incomplete", m.validate(r, h))

    def test_commodity_confirmation_without_confirmed_equity_must_not_handoff(self):
        r, h = fixture()
        r["trade_date"] = h["trade_date"] = "2026-10-27"
        r["scan_audit"]["state_migration_gate"]["current_trade_date"] = "2026-10-27"
        r["trends"][0]["trend_basis"] = "COMMODITY"
        r["trends"][0]["market_state"] = "趋势确认"
        h["signals"][0]["market_state"] = "趋势确认"
        r["trends"][0]["industry_assessments"] = [{
            "industry_code": "S240401", "industry_name": "黄金",
            "market_state": "观察", "benefit_level": "DIRECT"
        }]
        self.assertIn("黄金:unconfirmed_industry_route", m.validate(r, h))
        r["trends"][0]["in_new_position_priority"] = False
        h["signals"] = []
        self.assertEqual(m.validate(r, h), [])

    def test_prepublication_migration_gate_required(self):
        r, h = fixture()
        del r["scan_audit"]["state_migration_gate"]
        self.assertIn("migration_gate_missing", m.validate(r, h))
        r["schema_version"] = 1
        self.assertIn("schema_version_mismatch", m.validate(r, h))


if __name__ == "__main__":
    unittest.main()
