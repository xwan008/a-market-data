"""Forward SW3 opt-in from the published Nov 23 close, without fabricated D1."""
import copy
import unittest

from scripts.industry_lifecycle import (
    industry_route_confirmed, cutover_route_lifecycle,
)
from scripts.validate_trend_publication_pair import validate as validate_pair

from scripts.sw3_same_day_cutover import validate_historical_forward_baseline as validate_industry_lifecycle

ASOF = "2026-11-23"
D1, D2, D3 = "2026-11-24", "2026-11-25", "2026-11-26"
SHA = "a" * 40
CODE = "S330102"


def original(state="趋势确认"):
    return {"industry_code": CODE, "industry_name": "空调",
            "benefit_level": "CORE", "market_state": state}


def migrated(prev, day=D1):
    row = copy.deepcopy(prev)
    state = prev["market_state"]
    inherited = state == "趋势确认"
    row["industry_lifecycle"] = {
        "episodes": [],
        "cutover_baseline": {
            "basis": "FORMAL_ASOF_SW3_CUTOVER",
            "asof_trade_date": ASOF,
            "source_registry_blob_sha": SHA,
            "industry_code": CODE,
            "initial_market_state": state,
            "state_history": [{"trade_date": day, "from": state, "to": state}],
            "d123_stage": None if inherited else "D1",
            "d123_decision": "INHERITED_CONFIRMED" if inherited else "PENDING",
            "d123_decision_trade_date": None,
        },
    }
    return row


def facts(day):
    return [{
        "dimension": dimension, "direction": "SUPPORT",
        "impact": "STRUCTURAL" if dimension == "MARKET_STRUCTURE" else "NORMAL",
        "trade_date": day, "industry_code": CODE,
        "source": "data/research/sector_discovery_audit.json",
        "finding": "独立核验空调的多日结构、广度与相对强度构成可靠确认依据",
    } for dimension in ("MARKET_STRUCTURE", "MARKET_BREADTH", "RELATIVE_STRENGTH")]


class Sw3ForwardCutoverTests(unittest.TestCase):
    def test_legacy_confirmation_is_inherited_without_forged_d1(self):
        prev = original()
        cur = migrated(prev)
        self.assertEqual(validate_industry_lifecycle(cur, prev, D1, source_sha=SHA), [])
        self.assertTrue(industry_route_confirmed(cur))
        route = cutover_route_lifecycle(cur)
        self.assertIsNone(route["episode_id"])
        self.assertIsNone(route["d123_stage"])
        self.assertIsNone(route["d123_decision_trade_date"])
        self.assertEqual(route["baseline_asof_trade_date"], ASOF)

    def test_cutover_must_reference_exact_previous_blob_and_state(self):
        prev = original()
        cur = migrated(prev)
        self.assertIn("S330102:cutover_provenance_mismatch",
                      validate_industry_lifecycle(cur, prev, D1, source_sha="b" * 40))
        cur["industry_lifecycle"]["cutover_baseline"]["initial_market_state"] = "观察"
        self.assertIn("S330102:cutover_provenance_mismatch",
                      validate_industry_lifecycle(cur, prev, D1, source_sha=SHA))

    def test_old_observation_uses_fresh_bounded_review_not_backdated_d1(self):
        prev = original("观察")
        d1 = migrated(prev)
        self.assertEqual(validate_industry_lifecycle(d1, prev, D1, source_sha=SHA), [])
        self.assertFalse(industry_route_confirmed(d1))
        d2 = copy.deepcopy(d1)
        baseline = d2["industry_lifecycle"]["cutover_baseline"]
        baseline["state_history"].append({"trade_date": D2, "from": "观察", "to": "观察"})
        baseline["d123_stage"] = "D2"
        self.assertEqual(validate_industry_lifecycle(d2, d1, D2, source_sha="b" * 40), [])
        d3 = copy.deepcopy(d2)
        baseline = d3["industry_lifecycle"]["cutover_baseline"]
        baseline["state_history"].append({"trade_date": D3, "from": "观察", "to": "观察"})
        baseline["d123_stage"] = "D3"
        self.assertIn("S330102:cutover_d3_requires_final_verdict",
                      validate_industry_lifecycle(d3, d2, D3))

    def test_cutover_confirmation_requires_three_current_industry_facts(self):
        prev = original("候选趋势")
        cur = migrated(prev)
        cur["market_state"] = "趋势确认"
        b = cur["industry_lifecycle"]["cutover_baseline"]
        b["state_history"][0]["to"] = "趋势确认"
        b.update(d123_decision="CONFIRMED", d123_decision_trade_date=D1)
        self.assertIn("S330102:cutover_new_confirmation_evidence_incomplete",
                      validate_industry_lifecycle(cur, prev, D1, source_sha=SHA))
        b["confirmation_evidence"] = facts(D1)
        self.assertEqual(validate_industry_lifecycle(cur, prev, D1, source_sha=SHA), [])
        self.assertTrue(industry_route_confirmed(cur))

    def test_baseline_cannot_rewrite_frozen_source_or_verdict(self):
        prev = original()
        first = migrated(prev)
        second = copy.deepcopy(first)
        b = second["industry_lifecycle"]["cutover_baseline"]
        b["source_registry_blob_sha"] = "b" * 40
        b["state_history"].append({"trade_date": D2, "from": "趋势确认", "to": "趋势确认"})
        self.assertIn("S330102:cutover_baseline_rewritten",
                      validate_industry_lifecycle(second, first, D2))
        b["source_registry_blob_sha"] = SHA
        b["d123_decision"] = "PENDING"
        self.assertIn("S330102:cutover_legacy_confirmation_must_remain_unstaged",
                      validate_industry_lifecycle(second, first, D2))

    def test_pair_accepts_audited_baseline_route_under_candidate_parent(self):
        cur = migrated(original())
        registry = {
            "schema_version": 2, "result_kind": "a_share_trend_registry",
            "status": "COMPLETE", "trade_date": D1,
            "scan_audit": {
                "full_market_scan_completed": True,
                "sw3_lifecycle_contract": "SW3_V1",
                "state_migration_gate": {"mode": "full_close", "current_trade_date": D1},
            },
            "trends": [{
                "trend_name": "白色家电", "episode_id": "白色家电#2026-10-30",
                "market_state": "候选趋势", "trend_state": "T0",
                "lifecycle_status": "有效", "in_new_position_priority": True,
                "industry_assessments": [cur],
            }]
        }
        route = cutover_route_lifecycle(cur)
        handoff = {
            "schema_version": 1, "result_kind": "a_share_trend_handoff",
            "trade_date": D1,
            "signals": [{
                "rank": 1, "trend_name": "白色家电", "market_state": "趋势确认",
                "trend_state": "T0", "theme_market_state": "候选趋势",
                "industry_codes": [CODE], "industry_names": ["空调"],
                "industry_display_names": ["白色家电 - 空调"],
                "industry_lifecycles": [route],
            }],
        }
        self.assertEqual(validate_pair(registry, handoff), [])
        handoff["signals"][0]["industry_lifecycles"][0]["baseline_source_registry_blob_sha"] = "b" * 40
        self.assertIn("白色家电:industry_lifecycle_handoff_mismatch",
                      validate_pair(registry, handoff))


if __name__ == "__main__":
    unittest.main()
