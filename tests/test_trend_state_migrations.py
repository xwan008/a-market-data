import copy
import importlib.util
import pathlib
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "validate_trend_state_migrations.py"
spec = importlib.util.spec_from_file_location("migration_gate", SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
SHA = "a" * 40


def fixture():
    old = {"schema_version": 1, "result_kind": "a_share_trend_registry",
           "status": "COMPLETE", "trade_date": "2026-10-12",
           "trends": [{"trend_name": "银行", "first_seen_trade_date": "2026-10-12",
                       "market_state": "趋势确认", "trend_state": "T1",
                       "lifecycle_status": "有效",
                       "state_history": [{"trade_date": "2026-10-12", "from": None, "to": "趋势确认"}]}]}
    new = copy.deepcopy(old)
    new["trade_date"] = "2026-10-13"
    new["invalidated_history"] = []
    new["scan_audit"] = {
        "state_migration_gate": {
            "previous_registry_blob_sha": SHA,
            "previous_registry_trade_date": "2026-10-12",
            "current_trade_date": "2026-10-13",
            "mode": "full_close",
            "reviews": [{
                "trend_name": "银行", "decision": "HOLD",
                "previous_market_state": "趋势确认",
                "proposed_market_state": "趋势确认",
                "previous_trend_state": "T1",
                "proposed_trend_state": "T1",
                "reason": "多日趋势结构仍完整，单日波动记录为风险线索",
                "evidence": []
            }]
        }
    }
    return old, new


def e(dim, impact="NORMAL", window=1):
    return {"dimension": dim, "direction": "COUNTER", "impact": impact,
            "trade_date": "2026-10-13", "source": "https://example.org/report",
            "finding": "当日相关证据已按历史结构核对",
            "window_trading_days": window}


def downgrade(new):
    new["trends"][0]["market_state"] = "候选趋势"
    new["trends"][0]["state_history"].append(
        {"trade_date": "2026-10-13", "from": "趋势确认", "to": "候选趋势"})
    r = new["scan_audit"]["state_migration_gate"]["reviews"][0]
    r["decision"] = "CHANGE"
    r["proposed_market_state"] = "候选趋势"
    return r


class MigrationGateTests(unittest.TestCase):
    def test_hold_short_divergence_passes(self):
        old, new = fixture()
        self.assertEqual(m.validate(old, new, SHA), [])

    def test_bank_single_day_breadth_cannot_downgrade(self):
        old, new = fixture()
        downgrade(new)["evidence"] = [e("MARKET_BREADTH")]
        self.assertIn("银行:market_change_without_independent_evidence",
                      m.validate(old, new, SHA))

    def test_same_day_structural_counterevidence_allows_downgrade(self):
        old, new = fixture()
        downgrade(new)["evidence"] = [
            e("MARKET_STRUCTURE", "STRUCTURAL", 1), e("MARKET_BREADTH")]
        self.assertEqual(m.validate(old, new, SHA), [])

    def test_industry_headline_alone_cannot_downgrade_market(self):
        old, new = fixture()
        downgrade(new)["evidence"] = [e("INDUSTRY_FUNDAMENTALS", "CRITICAL")]
        self.assertIn("银行:market_change_without_independent_evidence",
                      m.validate(old, new, SHA))

    def test_history_mutation_blocked(self):
        old, new = fixture()
        new["trends"][0]["state_history"] = []
        self.assertIn("银行:history_rewritten", m.validate(old, new, SHA))

    def test_silent_deletion_blocked(self):
        old, new = fixture()
        new["trends"] = []
        self.assertIn("银行:silently_removed", m.validate(old, new, SHA))

    def test_sha_mismatch_blocked(self):
        old, new = fixture()
        self.assertIn("baseline_sha_or_date_not_frozen",
                      m.validate(old, new, "b" * 40))

    def test_future_evidence_blocked(self):
        old, new = fixture()
        r = downgrade(new)
        v = e("MARKET_STRUCTURE", "CRITICAL")
        v["trade_date"] = "2026-10-14"
        r["evidence"] = [v]
        self.assertIn("银行:unverifiable_evidence_metadata",
                      m.validate(old, new, SHA))

    def test_gold_single_day_rebound_cannot_restore_candidate(self):
        old, new = fixture()
        old["trends"][0]["market_state"] = "观察"
        new["trends"][0]["market_state"] = "候选趋势"
        new["trends"][0]["state_history"].append(
            {"trade_date": "2026-10-13", "from": "观察", "to": "候选趋势"})
        review = new["scan_audit"]["state_migration_gate"]["reviews"][0]
        review["previous_market_state"] = "观察"
        review["proposed_market_state"] = "候选趋势"
        review["decision"] = "CHANGE"
        rebound = e("MARKET_BREADTH")
        rebound["direction"] = "SUPPORT"
        review["evidence"] = [rebound]
        self.assertIn("银行:market_change_without_independent_evidence",
                      m.validate(old, new, SHA))

    def test_unresearched_new_theme_blocked(self):
        old, new = fixture()
        new["trends"].append({
            "trend_name": "没有证据的新增主题",
            "first_seen_trade_date": "2026-10-13",
            "market_state": "新异动", "trend_state": "T0",
            "lifecycle_status": "有效",
            "state_history": [{"trade_date": "2026-10-13", "from": None, "to": "新异动"}]})
        self.assertIn("没有证据的新增主题:new_trend_without_research_evidence",
                      m.validate(old, new, SHA))

    def setup_confirm(self):
        old, new = fixture()
        old["trends"][0]["market_state"] = "候选趋势"
        old["trends"][0]["state_history"][0]["to"] = "候选趋势"
        new["trends"][0]["state_history"][0]["to"] = "候选趋势"
        new["trends"][0]["state_history"].append(
            {"trade_date": "2026-10-13", "from": "候选趋势", "to": "趋势确认"})
        r = new["scan_audit"]["state_migration_gate"]["reviews"][0]
        r.update(decision="CHANGE", previous_market_state="候选趋势")
        r["evidence"] = [dict(e(d, impact), direction="SUPPORT") for d, impact in [
            ("MARKET_STRUCTURE", "STRUCTURAL"), ("MARKET_BREADTH", "NORMAL"),
            ("RELATIVE_STRENGTH", "NORMAL")]]
        return old, new, r

    def test_single_day_full_market_evidence_can_confirm(self):
        old, new, review = self.setup_confirm()
        self.assertEqual(m.validate(old, new, SHA), [])

    def test_elapsed_window_one_or_five_makes_no_gate_difference(self):
        old, new, review = self.setup_confirm()
        for days in (1, 5, 10):
            for fact in review["evidence"]:
                fact["window_trading_days"] = days
            self.assertEqual(m.validate(old, new, SHA), [])

    def test_confirm_requires_three_distinct_market_dimensions(self):
        old, new, review = self.setup_confirm()
        review["evidence"].pop()
        self.assertIn("银行:market_change_without_independent_evidence", m.validate(old, new, SHA))
        review["evidence"].append(dict(e("INDUSTRY_FUNDAMENTALS", "CRITICAL"),
                                      direction="SUPPORT"))
        self.assertIn("银行:market_change_without_independent_evidence", m.validate(old, new, SHA))

    def test_ordinary_market_improvement_needs_structural_and_independent_support(self):
        old, new, review = self.setup_confirm()
        old["trends"][0]["market_state"] = "观察"
        new["trends"][0]["market_state"] = "候选趋势"
        old["trends"][0]["state_history"][0]["to"] = "观察"
        new["trends"][0]["state_history"][0]["to"] = "观察"
        new["trends"][0]["state_history"][-1].update({"from": "观察", "to": "候选趋势"})
        review.update(previous_market_state="观察", proposed_market_state="候选趋势")
        review["evidence"] = review["evidence"][:2]
        self.assertEqual(m.validate(old, new, SHA), [])
        review["evidence"] = review["evidence"][1:]
        self.assertIn("银行:market_change_without_independent_evidence", m.validate(old, new, SHA))

    def test_current_market_data_required_not_old_news(self):
        old, new, review = self.setup_confirm()
        for fact in review["evidence"]:
            fact["trade_date"] = "2026-10-12"
        review["evidence"].append(dict(e("SUPPLY_DEMAND", "CRITICAL"), direction="SUPPORT"))
        self.assertIn("银行:market_change_without_independent_evidence", m.validate(old, new, SHA))

    def test_industry_driver_previously_verified_need_not_be_renews(self):
        old, new, review = self.setup_confirm()
        old["trends"][0]["supporting_evidence"] = [{
            "description": "已核验的历史订单，仍有效",
            "source": "https://example.org/orders", "trade_date": "2026-10-10"}]
        new["trends"][0]["supporting_evidence"] = copy.deepcopy(
            old["trends"][0]["supporting_evidence"])
        self.assertEqual(m.validate(old, new, SHA), [])

    def test_industry_t_grade_and_market_state_stay_independent(self):
        old, new, review = self.setup_confirm()
        old["trends"][0]["trend_state"] = "T0"
        new["trends"][0]["trend_state"] = "T0"
        review.update(previous_trend_state="T0", proposed_trend_state="T0")
        self.assertEqual(m.validate(old, new, SHA), [])

    def test_collective_retreat_uses_normal_single_day_market_evidence(self):
        old, new = fixture()
        review = downgrade(new)
        review["evidence"] = [e("MARKET_STRUCTURE", "STRUCTURAL"),
                              e("MARKET_BREADTH")]
        self.assertEqual(m.validate(old, new, SHA), [])

    def test_industry_only_downgrade_requires_primary_driver_counterevidence(self):
        old, new = fixture()
        new["trends"][0]["trend_state"] = "T0"
        new["trends"][0]["state_history"].append({
            "trade_date": "2026-10-13", "from": "T1", "to": "T0"})
        review = new["scan_audit"]["state_migration_gate"]["reviews"][0]
        review.update(decision="CHANGE", proposed_trend_state="T0")
        review["evidence"] = [e("MARKET_STRUCTURE", "STRUCTURAL"),
                              e("MARKET_BREADTH")]
        expected = "银行:industry_or_lifecycle_downgrade_without_primary_counterevidence"
        self.assertIn(expected, m.validate(old, new, SHA))
        review["evidence"] = [e("SUPPLY_DEMAND", "STRUCTURAL")]
        self.assertEqual(m.validate(old, new, SHA), [])

    def test_concurrent_industry_and_market_changes_need_both_evidence_sets(self):
        old, new = fixture()
        review = downgrade(new)
        new["trends"][0]["trend_state"] = "T0"
        new["trends"][0]["state_history"].append({
            "trade_date": "2026-10-13", "from": "T1", "to": "T0"})
        review["proposed_trend_state"] = "T0"
        review["evidence"] = [e("SUPPLY_DEMAND", "STRUCTURAL")]
        self.assertIn("银行:market_change_without_independent_evidence", m.validate(old, new, SHA))
        review["evidence"].extend([e("MARKET_STRUCTURE", "STRUCTURAL"),
                                   e("MARKET_BREADTH")])
        self.assertEqual(m.validate(old, new, SHA), [])

    def test_optional_sector_audit_has_metadata_gate_not_breadth_threshold(self):
        old, new, review = self.setup_confirm()
        sector = {"trade_date": "2026-10-13", "industry_count": 1,
                  "sectors": [{"id": "industry:S480201", "member_count": 6,
                               "usable_count": 4, "advance_ratio": .3,
                               "median_volume_ratio_vs_20d": .8}]}
        self.assertEqual(m.validate(old, new, SHA, sector_audit=sector), [])
        sector["trade_date"] = "2026-10-12"
        self.assertIn("sector_audit_metadata_invalid",
                      m.validate(old, new, SHA, sector_audit=sector))

    def test_first_seen_confirmed_uses_same_market_evidence_requirements(self):
        old, new, review = self.setup_confirm()
        entry = {"trend_name": "新主题", "first_seen_trade_date": "2026-10-13",
                 "market_state": "趋势确认", "trend_state": "T1",
                 "lifecycle_status": "有效",
                 "state_history": [{"trade_date": "2026-10-13", "from": None,
                                    "to": "趋势确认"}],
                 "supporting_evidence": [{"description": "前期已核验的订单事实",
                                          "trade_date": "2026-10-10"}]}
        new["trends"].append(entry)
        self.assertIn("新主题:new_confirmation_without_evidence_review",
                      m.validate(old, new, SHA))
        copied = copy.deepcopy(review)
        copied["trend_name"] = "新主题"
        new["scan_audit"]["state_migration_gate"]["reviews"].append(copied)
        self.assertEqual(m.validate(old, new, SHA), [])
        copied["evidence"] = copied["evidence"][:2]
        self.assertIn("新主题:new_confirmation_without_independent_market_evidence",
                      m.validate(old, new, SHA))

    def test_unverifiable_evidence_cannot_pass_confirmation(self):
        old, new, review = self.setup_confirm()
        review["evidence"][2]["source"] = "untrusted-placeholder"
        self.assertIn("银行:unverifiable_evidence_metadata",
                      m.validate(old, new, SHA))
        self.assertIn("银行:market_change_without_independent_evidence",
                      m.validate(old, new, SHA))


if __name__ == "__main__":
    unittest.main()
