"""Read-only as-of replay of the *published* November SW3 assessments.

No backfilled D1/D2/D3 decisions, no post-hoc discovery, no new trading signals.
Use only each day's immutable official registry + handoff pair.
"""
from pathlib import Path
import json
import unittest

from scripts.validate_trend_publication_pair import validate as validate_pair

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "validation" / "archive"
DATES = ["2026-11-16", "2026-11-17", "2026-11-18",
         "2026-11-19", "2026-11-20"]


def asof(day):
    base = ARCHIVE / day
    return (json.loads((base / "trend_registry.json").read_text("utf-8")),
            json.loads((base / "trend_handoff.json").read_text("utf-8")))


def independently_confirmed(registry, theme):
    return [row for row in theme.get("industry_assessments", [])
            if row.get("benefit_level") in {"CORE", "DIRECT"}
            and row.get("market_state") == "趋势确认"]


class PublishedSw3ReplayTests(unittest.TestCase):
    def test_each_snapshot_is_a_valid_read_only_legacy_pair(self):
        for day in DATES:
            registry, handoff = asof(day)
            with self.subTest(day=day):
                self.assertEqual(registry["trade_date"], day)
                self.assertEqual(handoff["trade_date"], day)
                self.assertEqual(validate_pair(registry, handoff), [])
                # These records have independent industry market_state, but
                # NO historical industry-level D1-D3 lifecycle yet.
                for theme in registry["trends"]:
                    for row in theme.get("industry_assessments", []):
                        self.assertNotIn("industry_lifecycle", row)
                        self.assertEqual(row.get("evidence_trade_date"), day)

    def test_handoff_codes_are_subset_of_asof_confirmed_beneficiaries(self):
        for day in DATES:
            registry, handoff = asof(day)
            by_name = {t["trend_name"]: t for t in registry["trends"]}
            with self.subTest(day=day):
                for signal in handoff["signals"]:
                    theme = by_name[signal["trend_name"]]
                    confirmed = {x["industry_code"]
                                 for x in independently_confirmed(registry, theme)}
                    self.assertTrue(set(signal["industry_codes"]).issubset(confirmed))

    def test_whitegoods_confirmed_aircon_is_blocked_only_by_parent_on_nov20(self):
        registry, handoff = asof("2026-11-20")
        t = next(x for x in registry["trends"] if x["trend_name"] == "白色家电")
        self.assertEqual(t["market_state"], "候选趋势")
        self.assertFalse(t["in_new_position_priority"])
        self.assertEqual([x["industry_code"] for x
                          in independently_confirmed(registry, t)], ["S330102"])
        self.assertNotIn("白色家电", [s["trend_name"] for s in handoff["signals"]])
        # Eligible under SW3 routing != mandatory selection by the 0-3 model.

    def test_nuclear_confirmed_does_not_mean_auto_select(self):
        registry, handoff = asof("2026-11-18")
        nuclear = next(x for x in registry["trends"] if x["trend_name"] == "核电运营")
        self.assertEqual(nuclear["market_state"], "趋势确认")
        self.assertEqual([x["industry_code"] for x in
                          independently_confirmed(registry, nuclear)], ["S410108"])
        self.assertFalse(nuclear["in_new_position_priority"])
        self.assertNotIn("核电运营", [s["trend_name"] for s in handoff["signals"]])

    def test_banking_differentiation_and_pharmacy_downgrade(self):
        r16, _ = asof("2026-11-16")
        r17, _ = asof("2026-11-17")
        r20, h20 = asof("2026-11-20")
        bank = next(x for x in r20["trends"] if x["trend_name"] == "银行")
        self.assertEqual([x["industry_code"] for x
                          in independently_confirmed(r20, bank)], ["S480201"])
        self.assertEqual(next(x for x in h20["signals"]
                              if x["trend_name"] == "银行")["industry_codes"],
                         ["S480201"])
        def pharmacy(registry):
            return next(x for x in registry["trends"]
                        if x["trend_name"] == "线下药店")
        self.assertEqual(pharmacy(r16)["market_state"], "候选趋势")
        self.assertEqual(pharmacy(r17)["market_state"], "趋势确认")
        self.assertEqual(pharmacy(r20)["market_state"], "观察")
        self.assertFalse(independently_confirmed(r20, pharmacy(r20)))


if __name__ == "__main__":
    unittest.main()
