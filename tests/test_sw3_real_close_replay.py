"""Read-only real-data replay of the Nov 20 -> Nov 23 published close.

Replays both production gates on the *actual* published source files. It also
checks the SW3 forward-cutover route on a synthetic, unchanged next-session
fixture. The latter is ONLY structural compatibility, NOT a Nov 24 forecast,
not a genuine next-session research decision, and never published.
"""
import copy
import hashlib
import json
from pathlib import Path
import unittest

from scripts.trend_registry import validate as migration_gate
from scripts.validate_trend_publication_pair import validate as pair_gate
from scripts.industry_lifecycle import (
    cutover_route_lifecycle, industry_route_confirmed
)

from scripts.sw3_same_day_cutover import validate_historical_forward_baseline as validate_industry_lifecycle

ROOT = Path(__file__).resolve().parents[1]
CURRENT_DATE = "2026-11-23"
PRIOR_DATE = "2026-11-20"
SIMULATED_NEXT_DAY = "2026-11-24"


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def git_blob_sha(path):
    blob = (ROOT / path).read_bytes()
    return hashlib.sha1(b"blob " + str(len(blob)).encode() + b"\0" + blob).hexdigest()


class RealCloseReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prior_path = f"validation/archive/{PRIOR_DATE}/trend_registry.json"
        cls.prior = load(cls.prior_path)
        cls.prior_handoff = load(f"validation/archive/{PRIOR_DATE}/trend_handoff.json")
        # Today's original (legacy) close is immutable after an as-of cutover.
        archived = ROOT / "validation/archive/2026-11-23/trend_registry.json"
        cls.registry_path = ("validation/archive/2026-11-23/trend_registry.json"
                             if archived.exists() else "research/trend_registry.json")
        cls.current = load(cls.registry_path)
        cls.handoff = load("validation/archive/2026-11-23/trend_handoff.json"
                           if archived.exists() else "research/trend_handoff.json")
        cls.blob_sha = git_blob_sha(cls.registry_path)

    def test_real_published_full_close_passes_both_production_gates(self):
        self.assertEqual(self.prior["trade_date"], PRIOR_DATE)
        self.assertEqual(self.current["trade_date"], CURRENT_DATE)
        self.assertEqual(pair_gate(self.prior, self.prior_handoff), [])
        self.assertEqual(
            self.current["scan_audit"]["state_migration_gate"]["previous_registry_blob_sha"],
            git_blob_sha(self.prior_path),
        )
        self.assertEqual(
            migration_gate(self.prior, self.current, git_blob_sha(self.prior_path)), []
        )
        self.assertEqual(pair_gate(self.current, self.handoff), [])
        self.assertIsNone(self.current["scan_audit"].get("sw3_lifecycle_contract"))

    def test_real_published_sw3_inventory_and_legacy_routing(self):
        rows = [row for theme in self.current["trends"]
                for row in theme.get("industry_assessments", [])]
        self.assertEqual(len(rows), 14)
        self.assertTrue(all("industry_lifecycle" not in r for r in rows))
        confirmed = [row for row in rows if row["market_state"] == "趋势确认"]
        self.assertEqual(len(confirmed), 4)
        eligible_themes = {theme["trend_name"] for theme in self.current["trends"]
                           if any(row["market_state"] == "趋势确认"
                                  and row["benefit_level"] in {"CORE", "DIRECT"}
                                  for row in theme.get("industry_assessments", []))}
        self.assertEqual(eligible_themes, {"高端PCB", "电子化学品", "银行", "白色家电"})
        selected = [signal["trend_name"] for signal in self.handoff["signals"]]
        self.assertEqual(selected, ["高端PCB", "电子化学品", "银行"])
        self.assertNotIn("白色家电", selected)

    def test_cutover_compatibility_with_real_asof_state_is_structural_only(self):
        """No synthetic 24th session is represented as real market research."""
        simulated = copy.deepcopy(self.current)
        simulated["trade_date"] = SIMULATED_NEXT_DAY
        scan = simulated["scan_audit"]
        scan["sw3_lifecycle_contract"] = "SW3_V1"
        scan["state_migration_gate"]["current_trade_date"] = SIMULATED_NEXT_DAY
        for theme in simulated["trends"]:
            for row in theme.get("industry_assessments", []):
                inherited = row["market_state"] == "趋势确认"
                row["industry_lifecycle"] = {"episodes": [], "cutover_baseline": {
                    "basis": "FORMAL_ASOF_SW3_CUTOVER",
                    "asof_trade_date": CURRENT_DATE,
                    "source_registry_blob_sha": self.blob_sha,
                    "industry_code": row["industry_code"],
                    "initial_market_state": row["market_state"],
                    "state_history": [{
                        "trade_date": SIMULATED_NEXT_DAY,
                        "from": row["market_state"], "to": row["market_state"],
                    }],
                    "d123_stage": None if inherited else "D1",
                    "d123_decision": "INHERITED_CONFIRMED" if inherited else "PENDING",
                    "d123_decision_trade_date": None,
                }}
                original_theme = next(t for t in self.current["trends"]
                                      if t["trend_name"] == theme["trend_name"])
                original_row = next(old for old in original_theme["industry_assessments"]
                                    if old["industry_code"] == row["industry_code"])
                self.assertEqual(
                    validate_industry_lifecycle(
                        row, original_row, SIMULATED_NEXT_DAY, source_sha=self.blob_sha),
                    [],
                )
            if (theme["trend_name"] == "白色家电"):
                theme["priority_exclusion_reason"] = (
                    "行业具有继承确认资格，但原榜未选为优先研究，模拟数据不重新研究排序")
        preview_handoff = copy.deepcopy(self.handoff)
        preview_handoff["trade_date"] = SIMULATED_NEXT_DAY
        for signal in preview_handoff["signals"]:
            theme = next(t for t in simulated["trends"]
                         if t["trend_name"] == signal["trend_name"])
            allowed = [r for r in theme["industry_assessments"]
                       if industry_route_confirmed(r)]
            signal["market_state"] = "趋势确认"
            signal["theme_market_state"] = theme["market_state"]
            signal["industry_codes"] = [r["industry_code"] for r in allowed]
            signal["industry_names"] = [r["industry_name"] for r in allowed]
            signal["industry_display_names"] = [
                theme["trend_name"] + " - " + r["industry_name"] for r in allowed]
            signal["industry_lifecycles"] = [
                cutover_route_lifecycle(r) for r in allowed]
        self.assertEqual(pair_gate(simulated, preview_handoff), [])
        self.assertFalse(simulated is self.current)


if __name__ == "__main__":
    unittest.main()
