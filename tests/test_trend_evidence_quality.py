import copy
import json
import pathlib
import unittest
from unittest.mock import patch

from scripts import trend_evidence_quality as quality
from scripts import trend_registry as engine
from scripts import validate_trend_publication_pair as pair
from tests.test_trend_registry import fixture


DAY = "2026-11-10"
URL = "https://example.org/verified-news"
CLAIM = "燃气生产和供应业价格同比上涨7.9%，但企业利润传导待核验。"
EXCERPT = "2026年10月，燃气生产和供应业价格同比上涨7.9%，采购成本另行核查。"
PAGE = (f'<html><head><meta property="article:published_time" '
        f'content="{DAY}T16:20:00+08:00"></head>'
        f'<body><article>{EXCERPT}</article></body></html>')


def review():
    return {
        "status": "VERIFIED", "source": URL,
        "published_at": DAY + "T16:20:00+08:00",
        "available_at": DAY + "T16:20:00+08:00",
        "excerpt": EXCERPT, "claim_anchor": "燃气生产和供应业价格同比上涨7.9%",
        "relevance_reason": "原文直接陈述该行业价格同比变化，但不证明企业利润改善。",
    }


class Response:
    status = 200
    headers = type("Headers", (), {"get_content_charset": lambda self: "utf-8"})()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return PAGE.encode()


class EvidenceQualityTests(unittest.TestCase):
    @patch.object(quality, "urlopen", return_value=Response())
    def test_page_excerpt_and_real_publication_time_are_checked(self, fetch):
        self.assertEqual(quality.source_review_errors(review(), URL, CLAIM, DAY), [])
        self.assertEqual(fetch.call_count, 1)
        wrong = review()
        wrong["excerpt"] = "证券交易额出现连续三日上涨，与燃气价格内容无关。"
        self.assertIn("source_claim_mismatch",
                      quality.source_review_errors(wrong, URL, CLAIM, DAY))
        wrong = review()
        wrong["excerpt"] = "燃气生产和供应业价格同比上涨7.9%，但这是网页并不存在的附加内容。"
        self.assertIn("source_excerpt_not_on_page",
                      quality.source_review_errors(wrong, URL, CLAIM, DAY))
        wrong = review()
        wrong["published_at"] = DAY + "T15:00:00+08:00"
        wrong["available_at"] = wrong["published_at"]
        self.assertIn("source_publication_time_mismatch",
                      quality.source_review_errors(wrong, URL, CLAIM, DAY))

    def test_cutoff_unverified_and_mismatched_url_fail_closed(self):
        late = review()
        late["available_at"] = DAY + "T18:31:00+08:00"
        self.assertIn("source_after_cutoff_or_date_unverified",
                      quality.source_review_errors(late, URL, CLAIM, DAY))
        unverified = review()
        unverified["status"] = "UNVERIFIED"
        self.assertEqual(quality.source_review_errors(unverified, URL, CLAIM, DAY),
                         ["source_unverified"])
        self.assertEqual(quality.source_review_errors(review(), URL + "/other", CLAIM, DAY),
                         ["source_review_url_mismatch"])
        self.assertEqual(quality.source_review_errors(review(), "http://127.0.0.1/news",
                                                       CLAIM, DAY),
                         ["source_review_url_mismatch"])
        with patch.object(quality, "_read_page", return_value=(quality._compact(EXCERPT), [])):
            self.assertEqual(quality.source_review_errors(review(), URL, CLAIM, DAY),
                             ["source_publication_time_mismatch"])

    def test_only_observed_adverse_fact_is_counter(self):
        base = {"direction": "COUNTER", "counter_fact_status": "VERIFIED_ADVERSE_FACT",
                "adverse_fact": "核心行业三日相对收益为负且当日广度明显收缩",
                "finding": "核心行业三日相对收益为负且当日广度明显收缩"}
        self.assertEqual(quality.counter_errors(base), [])
        pseudo = copy.deepcopy(base)
        pseudo["adverse_fact"] = "订单尚未兑现，利润改善仍待核验"
        self.assertEqual(quality.counter_errors(pseudo),
                         ["counter_not_verified_adverse_fact"])
        pseudo["adverse_fact"] = base["adverse_fact"]
        pseudo["finding"] = "覆盖全行业的订单和利润尚未形成闭环"
        self.assertEqual(quality.counter_errors(pseudo),
                         ["counter_not_verified_adverse_fact"])

    def test_aerospace_and_gas_business_logic_are_separate(self):
        def row(name):
            return {
                "episode_id": name + "#2026-11-10", "trend_name": name,
                "market_state": "观察", "in_new_position_priority": False,
                "evidence_gaps": ["上市公司实际受益及后续收盘承接尚待独立核验"],
                "contrary_evidence": [], "supporting_evidence": [],
                "confirmation_audit": {
                    "strongest_counter_status": "NONE_VERIFIED",
                    "strongest_counter": "尚无已核实反证；后续观察价格结构与收益传导。",
                    "catalyst_kind": "UNVERIFIED", "catalyst_source": URL,
                    "catalyst_fact": CLAIM,
                    "catalyst_source_review": {"status": "UNVERIFIED", "source": URL},
                },
            }
        space = row("航天军工")
        space["industry_logic"] = {
            "profile": "AEROSPACE", "leading_indicator": "卫星发射与组网",
            "transmission_reason": "组网进展与上市公司的真实销售合同必须分别确认。",
            "launch_or_network_status": "UNVERIFIED",
            "listed_company_benefit_status": "UNVERIFIED",
            "benefit_reason": "卫星发射事实与上市公司订单、收入和利润须分别核实。",
        }
        gas = row("燃气")
        gas["industry_codes"] = ["S220301", "S410301"]
        gas["industry_assessments"] = [
            {"industry_code": "S410301", "market_state": "趋势确认",
             "benefit_level": "CORE"}]
        gas["industry_logic"] = {
            "profile": "GAS", "leading_indicator": "气价与采购成本",
            "transmission_reason": "上游售价和城燃终端顺价由不同企业承担，分别核实。",
            "business_models": [
                {"type": "UPSTREAM_PRODUCER", "industry_codes": ["S220301"],
                 "price_cost_transmission": "VERIFIED",
                 "reason": "上游生产企业的售价与开采成本需按主营独立核对。",
                 "source": URL, "fact": CLAIM, "source_review": review()},
                {"type": "CITY_GAS_OPERATOR", "industry_codes": ["S410301"],
                 "price_cost_transmission": "UNVERIFIED",
                 "reason": "城燃采购成本与居民终端顺价存在时差，尚待核验。"},
            ],
        }
        proposed = {"scan_audit": {"state_migration_gate": {}}, "trends": [space, gas]}
        with patch.object(quality, "_read_page",
                          return_value=(quality._compact(EXCERPT), [DAY + "T16:20:00+08:00"])):
            self.assertEqual(engine._quality_gate_errors(proposed, DAY), [])
        space["in_new_position_priority"] = True
        gas["in_new_position_priority"] = True
        with patch.object(quality, "_read_page",
                          return_value=(quality._compact(EXCERPT), [DAY + "T16:20:00+08:00"])):
            errors = engine._quality_gate_errors(proposed, DAY)
        self.assertIn("航天军工#2026-11-10:aerospace_benefit_unverified_for_handoff", errors)
        self.assertIn("燃气#2026-11-10:gas_transmission_unverified_for_handoff", errors)
        gas["industry_assessments"][0]["industry_code"] = "S220301"
        with patch.object(quality, "_read_page",
                          return_value=(quality._compact(EXCERPT), [DAY + "T16:20:00+08:00"])):
            errors = engine._quality_gate_errors(proposed, DAY)
        self.assertNotIn("燃气#2026-11-10:gas_transmission_unverified_for_handoff", errors)

    def test_removing_pseudo_counter_cannot_upgrade_market_state(self):
        previous, proposed = fixture()
        previous["trade_date"] = "2026-11-09"
        proposed["trade_date"] = DAY
        gate = proposed["scan_audit"]["state_migration_gate"]
        gate["previous_registry_trade_date"] = "2026-11-09"
        gate["current_trade_date"] = DAY
        proposed["trends"][0]["market_state"] = "趋势确认"
        proposed["trends"][0]["state_history"].append({
            "trade_date": DAY, "from": "候选趋势", "to": "趋势确认"})
        gate["reviews"][0].update(
            decision="CHANGE", previous_market_state="候选趋势",
            proposed_market_state="趋势确认")
        errors = engine.validate(previous, proposed, "a" * 40)
        self.assertIn("A#2026-10-16:market_change_without_independent_evidence", errors)

    def test_url_shape_does_not_pass_publication_quality_gate(self):
        episode = "燃气#2026-11-10"
        row = {
            "episode_id": episode, "trend_name": "燃气", "market_state": "观察",
            "in_new_position_priority": False,
            "evidence_gaps": ["城燃采购成本和顺价机制尚待核验"],
            "contrary_evidence": [{
                "direction": "COUNTER", "dimension": "INDUSTRY_FUNDAMENTALS",
                "source": URL, "finding": "订单尚未兑现，仍需验证利润传导",
            }],
            "confirmation_audit": {
                "strongest_counter_status": "VERIFIED_ADVERSE_FACT",
                "strongest_counter": "订单尚未兑现，仍需验证利润传导",
                "catalyst_kind": "EVENT", "catalyst_fact": CLAIM,
                "catalyst_source": URL,
            },
            "industry_logic": {
                "profile": "GAS", "leading_indicator": "气价与采购成本",
                "transmission_reason": "采购成本与终端售价的顺价关系需按企业分别核实。",
                "business_models": [{
                    "type": "CITY_GAS_OPERATOR", "industry_codes": ["S410301"],
                    "price_cost_transmission": "UNVERIFIED",
                    "reason": "采购成本与终端售价的顺价关系尚待核验。"}],
            },
            "industry_codes": ["S410301"],
        }
        proposed = {"scan_audit": {"state_migration_gate": {}}, "trends": [row]}
        errors = engine._quality_gate_errors(proposed, DAY)
        self.assertIn(episode + ":catalyst_source_review_missing", errors)
        self.assertIn(episode + ":counter_not_verified_adverse_fact", errors)
        self.assertIn(episode + ":counter_status_conflicts_with_evidence", errors)

    def test_frozen_november_nine_pair_still_valid(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        registry = json.loads((root / "research/trend_registry.json").read_text())
        handoff = json.loads((root / "research/trend_handoff.json").read_text())
        self.assertEqual(pair.validate(registry, handoff), [])


if __name__ == "__main__":
    unittest.main()
