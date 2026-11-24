"""Reproduce today's real formal close without re-discovering or changing winners."""
import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.sw3_same_day_cutover import build
from scripts.trend_registry import validate as validate_registry
from scripts.validate_trend_publication_pair import validate as validate_pair

ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-11-23"
FROZEN_CUTOVER_AT = "2026-11-23T19:20:19+08:00"


def load(name):
    return json.loads((ROOT / name).read_text("utf-8"))


def git_sha(path):
    raw = (ROOT / path).read_bytes()
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


class SameDaySw3CutoverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Historical replay must not become date-dependent on Nov 24 or later.
        cls.clock_patch = patch("scripts.sw3_same_day_cutover.datetime")
        cls.clock = cls.clock_patch.start()
        cls.clock.now.return_value = datetime.fromisoformat(FROZEN_CUTOVER_AT)
        cls.clock.fromisoformat.side_effect = datetime.fromisoformat
        # Before formal same-day publication, read today's original file.
        # After publication, the immutable archive remains the source.
        archive = ROOT / "validation/archive/2026-11-23/trend_registry.json"
        cls.rpath = ("validation/archive/2026-11-23/trend_registry.json"
                     if archive.exists() else "research/trend_registry.json")
        cls.hpath = ("validation/archive/2026-11-23/trend_handoff.json"
                     if archive.exists() else "research/trend_handoff.json")
        cls.original = load(cls.rpath)
        cls.original_handoff = load(cls.hpath)
        cls.sha = git_sha(cls.rpath)
        cls.hsha = git_sha(cls.hpath)

    @classmethod
    def tearDownClass(cls):
        cls.clock_patch.stop()

    def create(self):
        return build(self.original, self.original_handoff,
                     self.sha, self.hsha, FROZEN_CUTOVER_AT)

    def test_real_23_close_admits_exactly_published_14_sw3_with_theme_phase(self):
        proposed, handoff = self.create()
        self.assertEqual(validate_registry(self.original, proposed, self.sha), [])
        self.assertEqual(validate_pair(proposed, handoff), [])
        self.assertEqual(len(proposed["trends"]), 9)
        assessments = [row for t in proposed["trends"]
                       for row in t["industry_assessments"]]
        self.assertEqual(len(assessments), 14)
        self.assertEqual(sum(x["market_state"] == "趋势确认" for x in assessments), 4)
        self.assertEqual([s["trend_name"] for s in handoff["signals"]],
                         ["高端PCB", "电子化学品", "银行"])
        self.assertEqual([s["industry_codes"] for s in handoff["signals"]],
                         [["S270202"], ["S270601"], ["S480201"]])
        for prior, cur in zip(self.original["trends"], proposed["trends"]):
            self.assertEqual(prior["market_state"], cur["market_state"])
            self.assertEqual(prior["d123_decision"], cur["d123_decision"])
            self.assertEqual(prior["d123_stage"], cur["d123_stage"])
            for a, b in zip(prior["industry_assessments"], cur["industry_assessments"]):
                self.assertEqual(a["market_state"], b["market_state"])
                base = b["industry_lifecycle"]["cutover_baseline"]
                self.assertEqual(base["d123_stage"], prior["d123_stage"])
                self.assertEqual(base["phase_origin"], "LEGACY_THEME_D123")
                self.assertEqual(base["legacy_theme_d123"]["d123_decision"],
                                 prior["d123_decision"])
                self.assertEqual(base["state_history"], [])
                self.assertIsNone(base["d123_decision_trade_date"])
        white = next(t for t in proposed["trends"] if t["trend_name"] == "白色家电")
        by_code = {a["industry_code"]: a for a in white["industry_assessments"]}
        self.assertEqual(white["d123_stage"], "D3")
        self.assertEqual(
            by_code["S330102"]["industry_lifecycle"]["cutover_baseline"]["d123_decision"],
            "INHERITED_CONFIRMED")
        self.assertEqual(
            by_code["S330106"]["industry_lifecycle"]["cutover_baseline"]["d123_decision"],
            "INHERITED_UNCONFIRMED")

    def test_formal_snapshot_after_cutover_matches_reproducible_builder(self):
        actual = load("research/trend_registry.json")
        if actual.get("trade_date") != DAY:
            # Production has moved on; compare the original fixed-day rows instead.
            fixture = load("tests/fixtures/trend_industry_report_20261124.json")["previous"]
            exact, _ = self.create()
            self.assertEqual([t["industry_assessments"] for t in exact["trends"]],
                             [t["industry_assessments"] for t in fixture["trends"]])
            return
        if (actual.get("scan_audit") or {}).get("sw3_lifecycle_contract") != "SW3_V1":
            self.skipTest("pre-cutover formal source still under legacy contract")
        handoff = load("research/trend_handoff.json")
        exact, exact_handoff = build(
            self.original, self.original_handoff, self.sha, self.hsha,
            actual["generated_at"]
        )
        self.assertEqual(actual, exact)
        self.assertEqual(handoff, exact_handoff)
        self.assertEqual(validate_registry(self.original, actual, self.sha), [])
        self.assertEqual(validate_pair(actual, handoff), [])

    def test_no_market_or_phase_changes_and_fake_history_blocked(self):
        new, handoff = self.create()
        tampered = copy.deepcopy(new)
        tampered["trends"][0]["industry_assessments"][0]["market_state"] = "观察"
        self.assertTrue(any("industry_state_rewritten" in e for e in
                            validate_registry(self.original, tampered, self.sha)))
        tampered = copy.deepcopy(new)
        row = tampered["trends"][4]["industry_assessments"][1]
        row["industry_lifecycle"]["cutover_baseline"]["d123_decision"] = "INHERITED_CONFIRMED"
        self.assertTrue(any("legacy_cutover_not_a_child_verdict" in e for e in
                            validate_registry(self.original, tampered, self.sha)))
        tampered = copy.deepcopy(new)
        row = tampered["trends"][4]["industry_assessments"][1]
        row["industry_lifecycle"]["cutover_baseline"]["state_history"] = [{
            "trade_date": DAY, "from": "观察", "to": "观察"}]
        self.assertTrue(any("fabricated_same_day_history" in e for e in
                            validate_registry(self.original, tampered, self.sha)))
        tampered = copy.deepcopy(new)
        tampered["trends"][3]["d123_stage"] = "D3"
        self.assertTrue(any("theme_rewritten" in e for e in
                            validate_registry(self.original, tampered, self.sha)))
        self.assertTrue(any("provenance" in e or "initial" in e for e in
                            validate_registry(self.original, new, "b" * 40)))

    def test_route_membership_is_not_re_ranked_and_frozen_scan_not_mutated(self):
        new, handoff = self.create()
        bad = copy.deepcopy(handoff)
        bad["signals"].append({"rank": 4, "trend_name": "白色家电",
                                "market_state": "趋势确认"})
        self.assertNotEqual(validate_pair(new, bad), [])
        bad = copy.deepcopy(new)
        bad["scan_audit"]["independent_discovery_count"] = 900
        self.assertIn("sw3_cutover_frozen_scan_rewritten",
                      validate_registry(self.original, bad, self.sha))


if __name__ == "__main__":
    unittest.main()
