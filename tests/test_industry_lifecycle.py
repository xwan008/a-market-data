import copy
import unittest

from scripts.industry_lifecycle import validate_industry_lifecycle

DAY1 = "2026-11-16"
DAY2 = "2026-11-17"
DAY3 = "2026-11-18"
DAY4 = "2026-11-19"


def fact(day=DAY1):
    return {
        "dimension": "MARKET_STRUCTURE", "direction": "SUPPORT",
        "impact": "NORMAL", "trade_date": day,
        "source": "data/research/sector_discovery_audit.json",
        "finding": "行业自身的价格结构、广度与相对强度已经完成独立核验",
    }


def episode(code="S330102", stage="D1", decision="PENDING", state="观察"):
    return {
        "episode_id": f"{code}#{DAY1}", "trigger_trade_date": DAY1,
        "d123_stage": stage, "d123_decision": decision,
        "d123_decision_trade_date": None,
        "initial_discovery_basis": "CONTINUING_STRUCTURE",
        "trigger_evidence": fact(),
        "state_history": [{"trade_date": DAY1, "from": None, "to": state}],
        "backfill_audit": None,
    }


def assessment(code="S330102", state="观察", life=None):
    return {
        "industry_code": code, "industry_name": "空调", "benefit_level": "CORE",
        "market_state": state,
        "industry_lifecycle": {"episodes": [life or episode(code=code)]},
    }


class IndustryLifecycleTests(unittest.TestCase):
    def test_new_industry_starts_at_d1(self):
        row = assessment()
        self.assertEqual(validate_industry_lifecycle(row, None, DAY1), [])

    def test_d1_to_d2_confirmation_is_independent_of_later_state(self):
        old = assessment()
        new = copy.deepcopy(old)
        e = new["industry_lifecycle"]["episodes"][0]
        e["d123_stage"] = "D2"
        e["d123_decision"] = "CONFIRMED"
        e["d123_decision_trade_date"] = DAY2
        e["confirmation_evidence"] = [
            {**fact(DAY2), "industry_code": "S330102", "dimension": dimension,
             "impact": "STRUCTURAL" if dimension == "MARKET_STRUCTURE" else "NORMAL"}
            for dimension in ["MARKET_STRUCTURE", "MARKET_BREADTH", "RELATIVE_STRENGTH"]
        ]
        e["state_history"].append(
            {"trade_date": DAY2, "from": "观察", "to": "趋势确认"}
        )
        new["market_state"] = "趋势确认"
        self.assertEqual(validate_industry_lifecycle(new, old, DAY2), [])
        later = copy.deepcopy(new)
        e = later["industry_lifecycle"]["episodes"][0]
        e["state_history"].append(
            {"trade_date": DAY3, "from": "趋势确认", "to": "观察"}
        )
        later["market_state"] = "观察"
        self.assertEqual(validate_industry_lifecycle(later, new, DAY3), [])

    def test_d3_must_have_terminal_verdict(self):
        row = assessment()
        e = row["industry_lifecycle"]["episodes"][0]
        e["d123_stage"] = "D3"
        e["d123_decision"] = "PENDING"
        e["state_history"].extend([
            {"trade_date": DAY2, "from": "观察", "to": "观察"},
            {"trade_date": DAY3, "from": "观察", "to": "观察"},
        ])
        self.assertIn(
            "S330102:S330102#2026-11-16:industry_d3_pending_invalid",
            validate_industry_lifecycle(row, None, DAY3),
        )

    def test_new_episode_requires_prior_final_verdict(self):
        old = assessment()
        old["industry_lifecycle"]["episodes"][0]["d123_decision"] = "PENDING"
        new = copy.deepcopy(old)
        second = episode(code="S330102")
        second["episode_id"] = f"S330102#{DAY2}"
        second["trigger_trade_date"] = DAY2
        second["trigger_evidence"] = fact(DAY2)
        second["state_history"] = [
            {"trade_date": DAY2, "from": None, "to": "候选趋势"}
        ]
        new["industry_lifecycle"]["episodes"].append(second)
        new["market_state"] = "候选趋势"
        self.assertIn(
            "S330102:industry_new_episode_before_prior_verdict",
            validate_industry_lifecycle(new, old, DAY2),
        )

    def test_closed_episode_can_be_followed_by_a_new_d1(self):
        old = assessment()
        first = old["industry_lifecycle"]["episodes"][0]
        first["d123_stage"] = "D3"
        first["d123_decision"] = "NOT_CONFIRMED"
        first["d123_decision_trade_date"] = DAY3
        first["state_history"].extend([
            {"trade_date": DAY2, "from": "观察", "to": "观察"},
            {"trade_date": DAY3, "from": "观察", "to": "观察"},
        ])
        new = copy.deepcopy(old)
        second = episode()
        second["episode_id"] = f"S330102#{DAY4}"
        second["trigger_trade_date"] = DAY4
        second["trigger_evidence"] = fact(DAY4)
        second["state_history"] = [
            {"trade_date": DAY4, "from": None, "to": "候选趋势"}
        ]
        new["industry_lifecycle"]["episodes"].append(second)
        new["market_state"] = "候选趋势"
        self.assertEqual(validate_industry_lifecycle(new, old, DAY4), [])

    def test_same_day_revision_is_explicit(self):
        old = assessment()
        new = copy.deepcopy(old)
        e = new["industry_lifecycle"]["episodes"][0]
        e["state_history"].append({
            "trade_date": DAY1, "from": "观察", "to": "候选趋势",
            "event": "same_day_revision",
        })
        new["market_state"] = "候选趋势"
        self.assertEqual(
            validate_industry_lifecycle(new, old, DAY1, same_day=True), []
        )
    
    def test_no_fake_confirmation_during_d1(self):
        row = assessment(state="趋势确认")
        e = row["industry_lifecycle"]["episodes"][0]
        e["state_history"][0]["to"] = "趋势确认"
        e["d123_decision"] = "CONFIRMED"
        e["d123_decision_trade_date"] = DAY1
        self.assertIn(
            "S330102:S330102#2026-11-16:industry_confirmation_evidence_incomplete",
            validate_industry_lifecycle(row, None, DAY1),
        )


if __name__ == "__main__":
    unittest.main()
