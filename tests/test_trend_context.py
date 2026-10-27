import copy
import json
import unittest
from pathlib import Path
from scripts.validate_trend_context import validate

URL = "https://example.org/verified-2026-10-26"
OLD = "2026-10-26"
NEW = "2026-10-27"


def evidence(day=OLD):
    return [{"trade_date": day, "source": URL,
             "description": "来自独立可复核的真实市场行情及产业证据，待模型进一步验证"}]


def registry(day=NEW, trends=None):
    return {"schema_version": 2, "result_kind": "a_share_trend_registry",
            "status": "COMPLETE", "trade_date": day, "trends": trends or []}


def observation():
    return {"trend_name": "银行", "episode_id": "银行#" + OLD, "first_seen_trade_date": OLD,
            "last_verified_trade_date": OLD, "market_state": "观察",
            "industry_codes": ["S480201"], "industry_names": ["国有大型银行Ⅲ"],
            "evidence": evidence(), "next_check": "核对价格结构与后续基本面"}


def commodity():
    return {"commodity_id": "BRENT_CRUDE", "commodity_name": "布伦特原油",
            "first_seen_trade_date": OLD, "last_verified_trade_date": OLD,
            "market_state": "趋势确认",
            "price_anchor": {"instrument": "Brent", "contract": "front-month",
                             "trade_date": OLD, "value": 115.2, "unit": "USD/bbl",
                             "price_basis": "settle", "source": URL},
            "evidence": evidence(),
            "a_share_industries": [{"industry_code": "S750101", "industry_name": "油气开采Ⅲ"}],
            "next_check": "核对最新报价、期现口径及库存"}


def context(day=NEW):
    obs, oil = observation(), commodity()
    if day == NEW:
        obs["last_verified_trade_date"] = NEW
        oil["last_verified_trade_date"] = NEW
    return {"schema_version": 1, "result_kind": "a_share_trend_context",
            "status": "COMPLETE", "trade_date": day,
            "observations": [obs], "commodity_trends": [oil], "transitions": []}


class TrendContextTests(unittest.TestCase):
    def test_live_context_passes_with_previous(self):
        self.assertEqual(validate(registry(), context(), context(OLD)), [])

    def test_repository_context_pairs_with_existing_formal_registry(self):
        root = Path(__file__).resolve().parents[1]
        active = json.loads((root / "research/trend_registry.json").read_text(encoding="utf-8"))
        companion = json.loads((root / "research/trend_context.json").read_text(encoding="utf-8"))
        self.assertEqual(validate(active, companion), [])
        self.assertTrue(companion["commodity_trends"])
        self.assertTrue(companion["observations"])

    def test_observation_never_masquerades_as_tradable(self):
        current = context()
        self.assertIn("银行:observation_also_in_active_trends",
                      validate(registry(trends=[{"trend_name": "银行"}]), current))

    def test_observation_cannot_silently_disappear(self):
        current = context()
        current["observations"] = []
        self.assertIn("银行#" + OLD + ":silently_removed",
                      validate(registry(), current, context(OLD)))

    def test_commodity_cannot_silently_disappear(self):
        current = context()
        current["commodity_trends"] = []
        self.assertIn("BRENT_CRUDE:silently_removed",
                      validate(registry(), current, context(OLD)))

    def test_observation_promotion_requires_link_and_evidence(self):
        current = context()
        current["observations"] = []
        current["transitions"] = [{
            "kind": "observation", "id": "银行#" + OLD, "action": "PROMOTED",
            "reason": "重新确认三级行业市场结构形成持续趋势", "evidence": evidence(NEW)
        }]
        candidate = {"trend_name": "银行", "market_state": "候选趋势",
                     "source_observation_episode_id": "银行#" + OLD}
        self.assertEqual(validate(registry(trends=[candidate]), current, context(OLD)), [])
        del candidate["source_observation_episode_id"]
        self.assertIn("银行#" + OLD + ":promotion_link_missing",
                      validate(registry(trends=[candidate]), current, context(OLD)))

    def test_commodity_does_not_require_a_share_mapping(self):
        current = context()
        current["commodity_trends"][0]["a_share_industries"] = []
        self.assertEqual(validate(registry(), current, context(OLD)), [])

    def test_future_dated_quote_is_rejected(self):
        current = context()
        current["commodity_trends"][0]["price_anchor"]["trade_date"] = "2026-10-28"
        self.assertIn("BRENT_CRUDE:price_anchor_invalid", validate(registry(), current))

    def test_context_must_match_registry_date(self):
        self.assertIn("context_registry_trade_date_mismatch",
                      validate(registry(), context(OLD)))

    def test_commodity_price_still_independent_when_a_share_is_candidate(self):
        current = context()
        a_share = {"trend_name": "油气开采/油服工程", "market_state": "候选趋势"}
        self.assertEqual(validate(registry(trends=[a_share]), current, context(OLD)), [])


if __name__ == "__main__":
    unittest.main()
