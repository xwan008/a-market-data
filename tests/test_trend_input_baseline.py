import copy
import json
import unittest
from unittest.mock import patch

from scripts import validate_trend_input_baseline as baseline
from scripts import validate_trend_publication_pair as publication


def fixture():
    names = ["A", "B", "C", "D", "E"]
    registry = {
        "schema_version": 2,
        "result_kind": "a_share_trend_registry",
        "status": "COMPLETE",
        "trade_date": "2026-10-16",
        "scan_audit": {
            "mode": "initial_active_baseline",
            "trade_date": "2026-10-16",
            "tracked_count": 5,
            "state_migration_gate": {
                "mode": "initial_active_baseline",
                "current_trade_date": "2026-10-16",
                "reviews": []
            }
        },
        "trends": [{
            "trend_name": n,
            "episode_id": n + "#2026-10-16",
            "market_state": "候选趋势",
            "lifecycle_status": "有效",
            "trend_state": "T1",
            "in_new_position_priority": i == 0,
            "industry_codes": ["S630601"],
            "industry_names": ["风电整机"]
        } for i, n in enumerate(names)]
    }
    handoff = {
        "schema_version": 1,
        "result_kind": "a_share_trend_handoff",
        "trade_date": "2026-10-16",
        "signals": [{
            "rank": 1, "trend_name": "A",
            "trend_state": "T1", "market_state": "候选趋势",
            "industry_codes": ["S630601"],
            "industry_names": ["风电整机"]
        }]
    }
    return registry, handoff


def sha(obj):
    return baseline.git_blob_sha(json.dumps(obj, ensure_ascii=False).encode())


class PriorBaselineTests(unittest.TestCase):
    def test_git_blob_hash_matches_git(self):
        self.assertEqual(baseline.git_blob_sha(b"hello\n"),
                         "ce013625030ba8dba906f756967f9e9ca394464a")

    def test_exact_initial_pair_can_be_read_only(self):
        reg, hand = fixture()
        with patch.object(baseline, "BOOTSTRAP_REGISTRY_BLOB_SHA", sha(reg)), patch.object(
                baseline, "BOOTSTRAP_HANDOFF_BLOB_SHA", sha(hand)):
            self.assertEqual(baseline.validate_prior(reg, hand, sha(reg), sha(hand)),
                             ([], "INITIAL_READ_ONLY"))
        self.assertEqual(publication.validate(reg, hand),
                         ["full_market_scan_incomplete", "migration_gate_missing"])

    def test_unapproved_or_changed_baseline_is_blocked(self):
        reg, hand = fixture()
        errors, mode = baseline.validate_prior(reg, hand, sha(reg), sha(hand))
        self.assertIn("initial_baseline_not_allowlisted", errors)
        self.assertEqual(mode, "BLOCKED")
        with patch.object(baseline, "BOOTSTRAP_REGISTRY_BLOB_SHA", sha(reg)), patch.object(
                baseline, "BOOTSTRAP_HANDOFF_BLOB_SHA", sha(hand)):
            changed = copy.deepcopy(reg)
            changed["trends"][1]["trend_state"] = "T2"
            err, _ = baseline.validate_prior(changed, hand, sha(changed), sha(hand))
            self.assertIn("initial_baseline_not_allowlisted", err)

    def test_wrong_date_or_pair_mismatch_blocks(self):
        reg, hand = fixture()
        with patch.object(baseline, "BOOTSTRAP_REGISTRY_BLOB_SHA", sha(reg)), patch.object(
                baseline, "BOOTSTRAP_HANDOFF_BLOB_SHA", sha(hand)):
            bad = copy.deepcopy(reg)
            bad["trade_date"] = "2026-10-19"
            err, _ = baseline.validate_prior(bad, hand, sha(reg), sha(hand))
            self.assertIn("initial_baseline_not_allowlisted", err)
            wrong = copy.deepcopy(hand)
            wrong["signals"][0]["industry_codes"] = ["S999999"]
            err, _ = baseline.validate_prior(reg, wrong, sha(reg), sha(hand))
            self.assertIn("A:industry_codes_mismatch", err)

    def test_normal_full_close_remains_strict(self):
        reg, hand = fixture()
        reg["trade_date"] = hand["trade_date"] = "2026-10-19"
        reg["scan_audit"] = {
            "full_market_scan_completed": True,
            "state_migration_gate": {
                "mode": "full_close", "current_trade_date": "2026-10-19"
            }
        }
        self.assertEqual(baseline.validate_prior(reg, hand, sha(reg), sha(hand)),
                         ([], "FULL_CLOSE"))
        reg["scan_audit"]["full_market_scan_completed"] = False
        err, _ = baseline.validate_prior(reg, hand, sha(reg), sha(hand))
        self.assertIn("full_market_scan_incomplete", err)


if __name__ == "__main__":
    unittest.main()
