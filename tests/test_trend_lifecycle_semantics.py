import importlib.util
import pathlib
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "audit_trend_lifecycle_semantics.py"
spec = importlib.util.spec_from_file_location("lifecycle_audit", SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class HistoricalSemanticsTests(unittest.TestCase):
    def test_market_drop_without_primary_evidence_requires_review(self):
        data = {"trade_date": "2026-10-13", "trends": [{
            "trend_name": "样本", "market_state": "失效", "trend_state": "T2",
            "lifecycle_status": "已失效", "state_history": [
                {"trade_date": "2026-10-12", "to": "失效",
                 "event": "trend_invalidated"}]}]}
        report = m.audit(data, "a" * 40)
        self.assertEqual(report["requires_review"], 1)
        self.assertFalse(report["historical_data_mutated"])
        self.assertEqual(data["trends"][0]["lifecycle_status"], "已失效")

    def test_structured_primary_driver_evidence_is_distinguished(self):
        data = {"trade_date": "2026-10-13", "trends": [{
            "trend_name": "样本", "market_state": "失效", "trend_state": "T2",
            "lifecycle_status": "已失效", "state_history": []}],
            "scan_audit": {"state_migration_gate": {"reviews": [{
                "trend_name": "样本", "evidence": [
                    {"dimension": "SUPPLY_DEMAND", "direction": "COUNTER",
                     "impact": "STRUCTURAL"}]}]}}}
        self.assertEqual(m.audit(data, "a" * 40)["requires_review"], 0)


if __name__ == "__main__":
    unittest.main()
