import copy
import importlib.util
import pathlib
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "validate_trend_discovery_checkpoint.py"
spec = importlib.util.spec_from_file_location("firstpass", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def sample():
    return {"schema_version": 1, "result_kind": "a_share_firstpass_checkpoint",
            "trade_date": "2026-10-14", "phase": "PRE_HISTORY_PRE_PYTHON",
            "data_cutoff": "2026-10-14T15:00:00+08:00",
            "read_previous_registry": False, "read_python_candidates": False,
            "market_coverage": {"scope": "all available industries", "gaps": []},
            "industry_fact_coverage": {"scope": "broad primary research", "gaps": []},
            "inputs": [{"source": "data/latest.json"}],
            "candidates": [{"direction": "样本趋势", "evidence": [
                {"source": "https://example.org/report", "trade_date": "2026-10-14"}]}]}


class FirstpassCheckpointTests(unittest.TestCase):
    def test_structured_freeze(self):
        self.assertEqual(mod.validate(sample()), [])

    def test_prior_registry_is_forbidden_as_input(self):
        item = sample()
        item["inputs"].append({"source": "research/trend_registry.json"})
        self.assertIn("biased_input_in_firstpass", mod.validate(item))

    def test_python_candidates_forbidden_as_input(self):
        item = sample()
        item["read_python_candidates"] = True
        self.assertIn("isolation_claim_not_explicit", mod.validate(item))

    def test_missing_coverage_is_reported(self):
        item = sample()
        del item["industry_fact_coverage"]
        self.assertIn("industry_fact_coverage_not_audited", mod.validate(item))

    def test_zero_candidates_accepted(self):
        item = sample()
        item["candidates"] = []
        self.assertEqual(mod.validate(item), [])


if __name__ == "__main__":
    unittest.main()
