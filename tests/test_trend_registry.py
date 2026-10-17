import copy
import unittest

from scripts import trend_registry as engine
from scripts import validate_trend_state_migrations as gate
from scripts import validate_trend_publication_pair as pair

SHA = "a" * 40
DAY0 = "2026-10-16"
DAY1 = "2026-10-19"


def entry(name, state, day=DAY0):
    return {
        "trend_name": name, "first_seen_trade_date": day,
        "trend_state": "T1", "market_state": state, "lifecycle_status": "有效",
        "industry_codes": ["S630601"], "industry_names": ["风电整机"],
        "in_new_position_priority": False,
        "supporting_evidence": [{"finding": "当期产业及市场证据", "source": "https://example.org"}],
        "state_history": [{"trade_date": day, "from": None, "to": state}],
    }


def fixture():
    old = {"schema_version": 2, "result_kind": "a_share_trend_registry",
           "status": "COMPLETE", "trade_date": DAY0, "trends": [
               dict(entry("A", "候选趋势"), episode_id="A#" + DAY0)]}
    return old, copy.deepcopy(old)


def later(previous):
    proposed = copy.deepcopy(previous)
    proposed["trade_date"] = DAY1
    proposed["trends"] = [copy.deepcopy(t) for t in previous["trends"] if engine.tracking(t)]
    proposed["scan_audit"]["state_migration_gate"] = {
        "mode": "full_close", "current_trade_date": DAY1,
        "previous_registry_trade_date": DAY0, "previous_registry_blob_sha": SHA,
        "archived_count": 0,
        "reviews": [{
            "episode_id": "A#" + DAY0, "decision": "HOLD",
            "previous_market_state": "候选趋势", "proposed_market_state": "候选趋势",
            "previous_trend_state": "T1", "proposed_trend_state": "T1",
            "reason": "核验结构仍有效，未发现充分的新反证",
            "evidence": [],
        }],
    }
    return proposed


class TrendRegistryTests(unittest.TestCase):
    def test_previous_schema_not_accepted(self):
        old, now = fixture()
        now = later(old)
        old["schema_version"] = 1
        self.assertIn("schema_version_mismatch", gate.validate(old, now, SHA))

    def test_normal_close_only(self):
        old, now = fixture()
        now = later(old)
        now["scan_audit"]["state_migration_gate"]["mode"] = "v2_cutover"
        self.assertIn("invalid_close_mode", gate.validate(old, now, SHA))

    def test_active_continuity_only(self):
        old, _ = fixture()
        now = later(old)
        self.assertEqual(gate.validate(old, now, SHA), [])
        now["trends"] = []
        self.assertIn("A#" + DAY0 + ":active_silently_removed",
                      gate.validate(old, now, SHA))

    def test_observation_retired_and_same_name_new_cycle(self):
        _, old = fixture()
        obs = entry("B", "观察")
        obs["episode_id"] = "B#" + DAY0
        old["trends"].append(obs)
        now = later(old)
        now["scan_audit"]["state_migration_gate"]["archived_count"] = 1
        arch = engine.exit_archive(old, now, SHA)
        self.assertEqual(gate.validate(old, now, SHA, archive=arch), [])
        self.assertIn("missing_or_inexact_exit_archive", gate.validate(old, now, SHA))
        new_obs = entry("B", "观察", DAY1)
        new_obs["episode_id"] = "B#" + DAY1
        now["trends"].append(new_obs)
        self.assertEqual(gate.validate(old, now, SHA, archive=arch), [])
        now["trends"][-1]["episode_id"] = "B#" + DAY0
        self.assertIn("B#" + DAY0 + ":old_nontracking_episode_reused", gate.validate(old, now, SHA, archive=arch))

    def test_downgrade_requires_real_market_evidence(self):
        old, _ = fixture()
        now = later(old)
        now["trends"][0]["market_state"] = "观察"
        now["trends"][0]["state_history"].append(
            {"trade_date": DAY1, "from": "候选趋势", "to": "观察"})
        r = now["scan_audit"]["state_migration_gate"]["reviews"][0]
        r.update(decision="CHANGE", proposed_market_state="观察")
        self.assertIn("A#" + DAY0 + ":market_change_without_independent_evidence",
                      gate.validate(old, now, SHA))

    def test_handoff_unchanged_contract(self):
        reg, _ = fixture()
        reg["scan_audit"]={"state_migration_gate":{"mode":"full_close","current_trade_date":DAY0}}
        reg["trends"][0]["in_new_position_priority"] = True
        handoff = {
            "schema_version": 1, "result_kind": "a_share_trend_handoff",
            "trade_date": DAY0, "signals": [{
                "rank": 1, "trend_name": "A", "market_state": "候选趋势",
                "trend_state": "T1", "industry_codes": ["S630601"],
                "industry_names": ["风电整机"],
            }],
        }
        self.assertEqual(pair.validate(reg, handoff), [])
        reg["trends"][0]["market_state"] = "失效"
        self.assertIn("A:ineligible_priority_state", pair.validate(reg, handoff))


if __name__ == "__main__":
    unittest.main()
