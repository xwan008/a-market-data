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

    def test_mapping_is_not_transition_evidence(self):
        old, new = fixture()
        r = downgrade(new)
        r["evidence"] = [dict(e("MARKET_BREADTH"), finding="A股映射不足导致部分股票未覆盖")]
        self.assertIn("银行:downgrade_without_structural_or_critical_counterevidence",
                      m.validate(old, new, SHA))


if __name__ == "__main__":
    unittest.main()
