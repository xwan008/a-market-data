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
        self.assertIn("银行:downgrade_without_structural_or_critical_counterevidence",
                      m.validate(old, new, SHA))

    def test_multiday_structural_counterevidence_allows_downgrade(self):
        old, new = fixture()
        downgrade(new)["evidence"] = [
            e("MARKET_STRUCTURE", "STRUCTURAL", 5), e("MARKET_BREADTH")]
        self.assertEqual(m.validate(old, new, SHA), [])

    def test_major_driver_invalidation_allows_fast_downgrade(self):
        old, new = fixture()
        downgrade(new)["evidence"] = [e("INDUSTRY_FUNDAMENTALS", "CRITICAL")]
        self.assertEqual(m.validate(old, new, SHA), [])

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
        self.assertIn("银行:reclassification_without_multiday_or_critical_support",
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

    def setup_same_day_collapse(self):
        old, new = fixture()
        codes = ["S480201", "S480301"]
        for registry in (old, new):
            registry["trends"][0]["industry_codes"] = codes
        review = downgrade(new)
        review["evidence"] = [
            e("MARKET_STRUCTURE", "CRITICAL", 1),
            e("MARKET_BREADTH", "STRUCTURAL", 1),
            e("RELATIVE_STRENGTH", "STRUCTURAL", 1)]
        review["same_day_collective_breakdown"] = {
            "trade_date": "2026-10-13",
            "support_breaks": [
                {"industry_code": code, "reference_trade_date": "2026-10-12",
                 "support_level": 100, "observed_close": 94,
                 "source": "https://example.org/pricehistory"} for code in codes]}
        sectors = [
            {"id": "industry:" + code, "member_count": 6, "usable_count": 6,
             "advance_ratio": 0.1, "median_1d_pct": -3.0,
             "relative_1d_vs_market_median_pct": -1.4} for code in codes]
        sectors.extend({"id": f"industry:S{i:06d}", "member_count": 3,
                        "usable_count": 3, "advance_ratio": .5, "median_1d_pct": 0,
                        "relative_1d_vs_market_median_pct": 0} for i in range(329))
        audit = {"trade_date": "2026-10-13", "industry_count": 331,
                 "sectors": sectors}
        return old, new, audit

    def test_same_day_collective_breakdown_accepted(self):
        old, new, audit = self.setup_same_day_collapse()
        self.assertEqual(m.validate(old, new, SHA, sector_audit=audit), [])

    def test_sector_universe_can_change_without_blocking_valid_collapse(self):
        old, new, audit = self.setup_same_day_collapse()
        audit["sectors"].pop()
        audit["industry_count"] = len(audit["sectors"])
        self.assertEqual(m.validate(old, new, SHA, sector_audit=audit), [])
        audit["industry_count"] += 1
        self.assertIn("银行:downgrade_without_structural_or_critical_counterevidence",
                      m.validate(old, new, SHA, sector_audit=audit))

    def test_collective_breakdown_requires_frozen_sector_audit(self):
        old, new, audit = self.setup_same_day_collapse()
        self.assertIn("银行:downgrade_without_structural_or_critical_counterevidence",
                      m.validate(old, new, SHA))
        audit["trade_date"] = "2026-10-12"
        self.assertIn("银行:downgrade_without_structural_or_critical_counterevidence",
                      m.validate(old, new, SHA, sector_audit=audit))

    def test_single_sector_or_normal_breadth_is_not_collective_collapse(self):
        old, new, audit = self.setup_same_day_collapse()
        audit["sectors"][0]["advance_ratio"] = .6
        self.assertIn("银行:downgrade_without_structural_or_critical_counterevidence",
                      m.validate(old, new, SHA, sector_audit=audit))
        audit["sectors"][0]["advance_ratio"] = .1
        audit["sectors"][1]["median_1d_pct"] = -0.2
        self.assertIn("银行:downgrade_without_structural_or_critical_counterevidence",
                      m.validate(old, new, SHA, sector_audit=audit))

    def test_absolute_break_even_if_market_drops_faster(self):
        old, new, audit = self.setup_same_day_collapse()
        for item in audit["sectors"][:2]:
            item["relative_1d_vs_market_median_pct"] = 1.0
        review = new["scan_audit"]["state_migration_gate"]["reviews"][0]
        for item in review["evidence"]:
            if item["dimension"] == "RELATIVE_STRENGTH":
                item["direction"] = "SUPPORT"
        self.assertEqual(m.validate(old, new, SHA, sector_audit=audit), [])

    def test_relative_evidence_direction_cannot_contradict_market_data(self):
        old, new, audit = self.setup_same_day_collapse()
        for item in audit["sectors"][:2]:
            item["relative_1d_vs_market_median_pct"] = 1.0
        self.assertIn("银行:downgrade_without_structural_or_critical_counterevidence",
                      m.validate(old, new, SHA, sector_audit=audit))

    def test_duplicate_sector_ids_cannot_pass_full_universe(self):
        old, new, audit = self.setup_same_day_collapse()
        audit["sectors"][-1] = dict(audit["sectors"][0])
        self.assertIn("银行:downgrade_without_structural_or_critical_counterevidence",
                      m.validate(old, new, SHA, sector_audit=audit))

    def test_collective_breakdown_requires_confirmed_prior_support(self):
        old, new, audit = self.setup_same_day_collapse()
        b = new["scan_audit"]["state_migration_gate"]["reviews"][0]["same_day_collective_breakdown"]
        b["support_breaks"][0]["observed_close"] = 101
        b["support_breaks"][1]["observed_close"] = 101
        self.assertIn("银行:downgrade_without_structural_or_critical_counterevidence",
                      m.validate(old, new, SHA, sector_audit=audit))

    def test_market_collapse_cannot_invalidate_industry_without_primary_evidence(self):
        old, new, audit = self.setup_same_day_collapse()
        new["trends"][0]["trend_state"] = "T0"
        new["trends"][0]["state_history"].append(
            {"trade_date": "2026-10-13", "from": "T1", "to": "T0"})
        review = new["scan_audit"]["state_migration_gate"]["reviews"][0]
        review["proposed_trend_state"] = "T0"
        self.assertIn("银行:industry_or_lifecycle_downgrade_without_primary_counterevidence",
                      m.validate(old, new, SHA, sector_audit=audit))

    def test_market_collapse_cannot_invalidate_lifecycle_without_primary_evidence(self):
        old, new, audit = self.setup_same_day_collapse()
        new["trends"][0]["lifecycle_status"] = "已失效"
        new["trends"][0]["state_history"].append(
            {"trade_date": "2026-10-13", "from": "有效", "to": "已失效"})
        self.assertIn("银行:industry_or_lifecycle_downgrade_without_primary_counterevidence",
                      m.validate(old, new, SHA, sector_audit=audit))

    def test_collective_market_break_does_not_erase_industry_trend(self):
        old, new, audit = self.setup_same_day_collapse()
        self.assertEqual(new["trends"][0]["trend_state"], "T1")
        self.assertEqual(m.validate(old, new, SHA, sector_audit=audit), [])

    def test_mapping_is_not_transition_evidence(self):
        old, new = fixture()
        r = downgrade(new)
        r["evidence"] = [dict(e("MARKET_BREADTH"), finding="A股映射不足导致部分股票未覆盖")]
        self.assertIn("银行:downgrade_without_structural_or_critical_counterevidence",
                      m.validate(old, new, SHA))


if __name__ == "__main__":
    unittest.main()
