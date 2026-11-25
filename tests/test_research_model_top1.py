"""Contract tests for research-only TOP1 routing; no production fixtures changed."""
import copy
import json
import unittest
from unittest.mock import patch
from scripts import research_model_top1 as mod


class ModelTop1Test(unittest.TestCase):
    def setUp(self):
        self.codes = ["601288", "601328", "601939", "601658", "601398"]
        self.day = "2026-11-24"
        self.admission = {"trade_date": self.day, "prescreen_version": "CANONICAL",
                          "selected_company_count": 5,
                          "industries": [{"industry_code": "S480201", "selected_codes": self.codes}]}
        self.raw = json.dumps(self.admission).encode()
        self.research = {"trade_date": self.day, "schema_version": "trend_buy_research_v2",
                         "prescreen_version": "CANONICAL", "mode": "FORMAL",
                         "coverage_complete": True, "publication_audit": dict.fromkeys(mod.AUDIT, True),
                         "selected_company_count": 5,
                         "companies": [{"code": c, "industry_code": "S480201", "market_state": "趋势确认",
                                        "source_review": "synthetic test evidence", "transmission": "SUPPORTED",
                                        "theme_link_verified": True, "asof_price": 9.0}
                                       for c in self.codes]}
        self.structure = {"reference_trade_date": self.day,
                          "contract_id": "a-share-low-risk-price-structure",
                          "companies": {c: {"data_status": "verified", "data_date": self.day,
                                          "history_points": 65, "low_risk_eligible": True,
                                          "current_price": 9.0, "ma20": 9.1, "ma60": 9.2}
                                        for c in self.codes}}
        self.pick = {"industry_code": "S480201", "candidate_codes": list(self.codes),
                     "status": "COMPLETE", "top1_code": "601328", "reason": "synthetic decision",
                     "completion_gate": dict.fromkeys(mod.GATES, True),
                     "research_matrix": {c: {k: {"status": "VERIFIED_FACT", "sources": ["synthetic"]}
                                             for k in "ABCDE"} for c in self.codes},
                     "dynamic_comparison": {c: dict.fromkeys(mod.DIMENSIONS, "synthetic")
                                            for c in self.codes},
                     "comparison_reasons": {c: "synthetic" for c in self.codes if c != "601328"},
                     "strongest_counter": "synthetic", "falsifier": "synthetic"}
        self.selections = {"trade_date": self.day, "source_blob": mod.git_blob_sha(self.raw),
                           "prompt_version": mod.VERSION, "items": [self.pick]}

    def run_model(self):
        return mod.run(self.raw, self.research, self.structure, self.selections)

    def test_real_engine_wait_only_selected_no_replacement(self):
        original = mod.engine.evaluate_candidate
        with patch.object(mod.engine, "evaluate_candidate", wraps=original) as evaluate:
            result = self.run_model()
        self.assertEqual(evaluate.call_count, 1)
        self.assertEqual(evaluate.call_args.args[0]["code"], "601328")
        item = result["items"][0]
        self.assertEqual(item["candidate_codes"], self.codes)
        self.assertEqual(item["top1_code"], "601328")
        self.assertEqual(item["risk_status"], "WAIT")
        self.assertIsNone(item["conditional_plan"])
        self.assertFalse(result["production_eligible"])

    def test_no_selection_skips_engine(self):
        self.pick.update(status="INCOMPLETE", top1_code=None)
        with patch.object(mod.engine, "evaluate_candidate") as evaluate:
            result = self.run_model()
        evaluate.assert_not_called()
        self.assertEqual(result["risk_evaluated_count"], 0)

    def test_ready_plan_only_for_selected(self):
        row = {"code": "601328", "status": "READY", "entry_zone": [9.0, 9.1],
               "invalidation_price": 8.9, "wait_reason": None, "upside_to_resistance_R": 2}
        with patch.object(mod.engine, "evaluate_candidate", return_value=row) as evaluate:
            item = self.run_model()["items"][0]
        self.assertEqual(evaluate.call_count, 1)
        self.assertEqual(item["conditional_plan"]["entry_zone"], [9.0, 9.1])
        self.assertEqual(item["route"], "RESEARCH_CONDITIONAL_ONLY")

    def test_drop_and_uncertain_no_plan(self):
        for status in ("DROP", "UNCERTAIN"):
            with self.subTest(status=status), patch.object(
                mod.engine, "evaluate_candidate",
                return_value={"code": "601328", "status": status, "entry_zone": [9, 10]}) as evaluate:
                item = self.run_model()["items"][0]
                self.assertEqual(evaluate.call_count, 1)
                self.assertEqual(item["top1_code"], "601328")
                self.assertIsNone(item["conditional_plan"])
                self.assertEqual(item["route"], "NO_MONITOR")
                self.assertNotIn("entry_zone", item["risk_result"])

    def test_fail_closed_before_engine(self):
        mutations = [
            lambda: self.pick.update(candidate_codes=list(reversed(self.codes))),
            lambda: self.pick.update(top1_code="600000"),
            lambda: self.pick["completion_gate"].update(core_flow_verified=False),
            lambda: self.pick["research_matrix"]["601288"]["A"].update(status="UNKNOWN"),
            lambda: self.pick["dynamic_comparison"].pop("601288"),
            lambda: self.pick.update(entry_zone=[9, 10]),
            lambda: self.selections.update(source_blob="bad"),
            lambda: self.selections.update(trade_date="2026-11-25"),
            lambda: self.research["companies"].pop(),
            lambda: self.research["companies"][0].update(market_state="候选趋势"),
        ]
        state = copy.deepcopy((self.pick, self.selections, self.research))
        for mutate in mutations:
            self.pick, self.selections, self.research = copy.deepcopy(state)
            self.selections["items"] = [self.pick]
            with self.subTest(mutation=mutate), patch.object(mod.engine, "evaluate_candidate") as evaluate:
                mutate()
                with self.assertRaises(ValueError):
                    self.run_model()
                evaluate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
