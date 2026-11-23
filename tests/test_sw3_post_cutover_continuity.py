"""Regression of the *next real session* contract after the official 11/23 cutover.

These are simulated control-flow transitions based on real published SW3 rows.
They are NOT actual market research or 11/24 close signals.
"""
import copy
import json
from pathlib import Path
import unittest

from scripts.industry_lifecycle import validate_industry_lifecycle, industry_route_confirmed

ROOT = Path(__file__).resolve().parents[1]
D1, D2 = "2026-11-24", "2026-11-25"


def frozen_row(code):
    ledger = json.loads((ROOT / "research/trend_registry.json").read_text("utf-8"))
    return copy.deepcopy(next(row for theme in ledger["trends"]
                              for row in theme["industry_assessments"]
                              if row["industry_code"] == code))


def event(day, old_state, new_state=None):
    return {"trade_date": day, "from": old_state, "to": new_state or old_state}


def start_new_episode(old):
    code, state = old["industry_code"], old["market_state"]
    cur = copy.deepcopy(old)
    cur["industry_lifecycle"]["cutover_baseline"]["state_history"].append(
        event(D1, state))
    cur["industry_lifecycle"]["episodes"].append({
        "episode_id": f"{code}#{D1}",
        "trigger_trade_date": D1,
        "initial_discovery_basis": "CONTINUING_STRUCTURE",
        "trigger_evidence": {
            "trade_date": D1, "direction": "SUPPORT", "impact": "NORMAL",
            "dimension": "MARKET_STRUCTURE", "industry_code": code,
            "source": "data/research/sector_discovery_audit.json",
            "finding": "该三级行业市场走势重新出现可核验的独立观察触发"
        },
        "d123_stage": "D1", "d123_decision": "PENDING",
        "d123_decision_trade_date": None,
        "state_history": [{"trade_date": D1, "from": None, "to": state}],
        "backfill_audit": None,
    })
    return cur


class PostCutoverContinuityTests(unittest.TestCase):
    def test_hold_real_aircon_confirmation_without_restarting_d1(self):
        prior = frozen_row("S330102")
        hold = copy.deepcopy(prior)
        hold["industry_lifecycle"]["cutover_baseline"]["state_history"].append(
            event(D1, "趋势确认"))
        self.assertEqual(validate_industry_lifecycle(hold, prior, D1), [])
        self.assertTrue(industry_route_confirmed(hold))
        self.assertEqual(hold["industry_lifecycle"]["episodes"], [])

    def test_unconfirmed_ice_wash_stays_unconfirmed_then_new_d1(self):
        prior = frozen_row("S330106")
        d1 = start_new_episode(prior)
        self.assertEqual(validate_industry_lifecycle(d1, prior, D1), [])
        self.assertFalse(industry_route_confirmed(d1))
        self.assertEqual(d1["industry_lifecycle"]["cutover_baseline"]["d123_stage"], "D3")
        d2 = copy.deepcopy(d1)
        d2["industry_lifecycle"]["cutover_baseline"]["state_history"].append(
            event(D2, "观察"))
        ep = d2["industry_lifecycle"]["episodes"][0]
        ep["state_history"].append(event(D2, "观察"))
        ep["d123_stage"] = "D2"
        self.assertEqual(validate_industry_lifecycle(d2, d1, D2), [])

    def test_unconfirmed_child_cannot_reset_24_d1_to_25_d1(self):
        prior = frozen_row("S330106")
        d1 = start_new_episode(prior)
        d2 = copy.deepcopy(d1)
        d2["industry_lifecycle"]["cutover_baseline"]["state_history"].append(
            event(D2, "观察"))
        # Replace yesterday's episode with a fake new D1, keeping child
        # states unchanged; the previous implementation accepted this.
        ep = d2["industry_lifecycle"]["episodes"][0]
        ep["episode_id"] = "S330106#2026-11-25"
        ep["trigger_trade_date"] = D2
        ep["trigger_evidence"]["trade_date"] = D2
        ep["state_history"] = [{"trade_date": D2, "from": None, "to": "观察"}]
        errors = validate_industry_lifecycle(d2, d1, D2)
        self.assertIn("S330106:legacy_cutover_episode_identity_rewritten", errors)
        self.assertIn("S330106:legacy_cutover_episode_events_rewritten", errors)

    def test_pending_child_episode_cannot_open_second_d1(self):
        prior = frozen_row("S330106")
        d1 = start_new_episode(prior)
        d2 = copy.deepcopy(d1)
        d2["industry_lifecycle"]["cutover_baseline"]["state_history"].append(
            event(D2, "观察"))
        d2["industry_lifecycle"]["episodes"].append({
            **copy.deepcopy(d1["industry_lifecycle"]["episodes"][0]),
            "episode_id": "S330106#2026-11-25",
            "trigger_trade_date": D2,
            "trigger_evidence": {
                **d1["industry_lifecycle"]["episodes"][0]["trigger_evidence"],
                "trade_date": D2
            },
            "state_history": [{"trade_date": D2, "from": None, "to": "观察"}]
        })
        errors = validate_industry_lifecycle(d2, d1, D2)
        self.assertIn("S330106:legacy_cutover_new_d1_before_prior_verdict", errors)

    def test_old_cutover_context_and_frozen_confirmation_immutable(self):
        prior = frozen_row("S330102")
        hold = copy.deepcopy(prior)
        base = hold["industry_lifecycle"]["cutover_baseline"]
        base["state_history"].append(event(D1, "趋势确认"))
        base["legacy_theme_d123"]["d123_stage"] = "D1"
        errors = validate_industry_lifecycle(hold, prior, D1)
        self.assertIn("S330102:legacy_cutover_frozen_phase_rewritten", errors)


if __name__ == "__main__":
    unittest.main()
