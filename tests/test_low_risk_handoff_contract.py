"""Regression tests for canonical READY / WAIT + wait_reason handoff semantics."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_intraday_snapshot import validate_low_risk_handoff_items  # noqa: E402


class LowRiskHandoffContractTests(unittest.TestCase):
    def test_valid_wait_reasons_and_ready(self):
        rows = [
            {"code": "002074", "status": "WAIT", "wait_reason": "WAIT_PRICE"},
            {"code": "002463", "status": "WAIT", "wait_reason": "WAIT_MARGIN"},
            {"code": "002384", "status": "WAIT", "wait_reason": "WAIT_EXPECTATION"},
            {"code": "001389", "status": "WAIT", "wait_reason": "WAIT_CATALYST"},
            {"code": "600000", "status": "READY", "wait_reason": None},
        ]
        self.assertEqual(validate_low_risk_handoff_items({"status": "COMPLETE", "items": rows}), rows)

    def test_legacy_substatuses_cannot_be_main_status(self):
        for legacy in ("WAIT_PRICE", "WAIT_MARGIN", "WAIT_EXPECTATION", "WAIT_CATALYST"):
            with self.subTest(legacy=legacy), self.assertRaisesRegex(ValueError, "unknown_status"):
                validate_low_risk_handoff_items(
                    {"status": "COMPLETE", "items": [{"code": "002074", "status": legacy}]}
                )

    def test_missing_or_unknown_wait_reason_fails(self):
        for reason in (None, "waiting for dip", "WAIT"):
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, "invalid_wait_reason"):
                validate_low_risk_handoff_items(
                    {"status": "COMPLETE", "items": [
                        {"code": "002074", "status": "WAIT", "wait_reason": reason}
                    ]}
                )

    def test_invalid_ready_reason_or_duplicate_fails(self):
        with self.assertRaisesRegex(ValueError, "ready_has_wait_reason"):
            validate_low_risk_handoff_items({"status": "COMPLETE", "items": [
                {"code": "600000", "status": "READY", "wait_reason": "WAIT_PRICE"}
            ]})
        with self.assertRaisesRegex(ValueError, "duplicate_code"):
            validate_low_risk_handoff_items({"status": "COMPLETE", "items": [
                {"code": "002074", "status": "WAIT", "wait_reason": "WAIT_PRICE"},
                {"code": "002074", "status": "WAIT", "wait_reason": "WAIT_MARGIN"},
            ]})

    def test_real_handoff_matches_same_run_formal_result(self):
        handoff = json.loads((ROOT / "research/low_risk_handoff.json").read_text(encoding="utf-8"))
        items = validate_low_risk_handoff_items(handoff)
        formal = json.loads((ROOT / "research/latest_formal_result.json").read_text(encoding="utf-8"))
        if handoff.get("source_run_id") == formal.get("run_id"):
            self.assertEqual(handoff.get("trade_date"), formal.get("trade_date"))
            expected = sorted(formal.get("ready", []) + formal.get("wait", []), key=lambda x: x["rank"])
            self.assertEqual(
                [(x["rank"], x["code"], x["status"], x.get("wait_reason")) for x in items],
                [(x["rank"], x["code"], x["status"], x.get("wait_reason")) for x in expected],
            )


if __name__ == "__main__":
    unittest.main()
