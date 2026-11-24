"""Use frozen real industry rows, never today's moving production files."""
import copy
import json
from pathlib import Path
import unittest

from scripts.industry_lifecycle import (
    industry_review_phase, industry_tracking_active, industry_route_confirmed,
    validate_industry_lifecycle,
)
from scripts.render_trend_report import render, research_input
from scripts.industry_lifecycle import industry_review_records
from scripts.trend_registry import validate as migration_gate
from scripts.validate_trend_publication_pair import validate as pair_gate
from datetime import datetime
from unittest.mock import patch

DATA = json.loads((Path(__file__).parent / "fixtures/trend_industry_report_20261124.json").read_text("utf-8"))


def rows(registry):
    return {r["industry_code"]: r for t in registry["trends"]
            for r in t["industry_assessments"]}


class TrendReportTests(unittest.TestCase):
    def test_real_close_continuity(self):
        before, after = rows(DATA["previous"]), rows(DATA["registry"])
        for code in before.keys() & after.keys():
            self.assertEqual(validate_industry_lifecycle(
                after[code], before[code], "2026-11-24"), [], code)
        self.assertEqual(industry_review_phase(after["S480301"]), ("D2", "PENDING", None))
        self.assertEqual(industry_review_phase(after["S410108"]), ("D3", "NOT_CONFIRMED", "2026-11-24"))
        self.assertFalse(industry_tracking_active(after["S330106"]))
        self.assertTrue(industry_tracking_active(after["S330102"]))
        self.assertEqual(industry_review_phase(after["S330102"]), ("D3", "INHERITED_CONFIRMED", None))
        self.assertTrue(industry_route_confirmed(after["S480201"]))
        self.assertEqual(industry_review_phase(after["S640701"]), ("D1", "PENDING", None))

    def test_actual_rendered_report_not_prompt_text(self):
        result = render(DATA["registry"], DATA["handoff"])
        active, exits = result.split("### 验证期限退出", 1)
        self.assertIn("银行－股份制银行Ⅲ | 候选趋势 | D2验证中", active)
        self.assertIn("银行－国有大型银行Ⅲ | 趋势确认 | D1历史确认", active)
        self.assertIn("白色家电－空调 | 观察 | D3历史确认", active)
        self.assertNotIn("核电运营－核力发电", active)
        self.assertIn("核电运营－核力发电 | D3未确认", exits)
        self.assertIn("白色家电－冰洗 | D3未确认", exits)
        self.assertNotIn("SW3_V1", result)
        self.assertNotIn("Git SHA", result)
        self.assertIn("高端PCB - 印制电路板", result)

    def test_same_day_does_not_advance_clock_twice(self):
        row = copy.deepcopy(rows(DATA["registry"])["S480301"])
        history = row["industry_lifecycle"]["cutover_baseline"]["state_history"]
        history.append({"trade_date": "2026-11-24", "event": "same_day_revision",
                        "from": "候选趋势", "to": "候选趋势"})
        self.assertEqual(industry_review_phase(row), ("D2", "PENDING", None))
        history.append({"trade_date": "2026-11-25", "from": "候选趋势", "to": "候选趋势"})
        self.assertEqual(industry_review_phase(row), ("D3", "NOT_CONFIRMED", "2026-11-25"))
        history.append({"trade_date": "2026-11-26", "from": "候选趋势", "to": "候选趋势"})
        self.assertEqual(industry_review_phase(row), ("D3", "NOT_CONFIRMED", "2026-11-25"))

    def test_expired_rows_are_not_next_session_research_input(self):
        view = research_input(DATA["registry"], DATA["handoff"])
        codes = {x["assessment"]["industry_code"] for x in view["active_industries"]}
        self.assertEqual(len(codes), 10)
        self.assertNotIn("S410108", codes)
        self.assertNotIn("S330106", codes)
        self.assertNotIn("S421001", codes)
        self.assertNotIn("S421002", codes)
        prior = rows(DATA["registry"])["S410108"]
        self.assertEqual(validate_industry_lifecycle(prior, prior, "2026-11-25"), [])
        wrong = copy.deepcopy(prior)
        wrong["evidence_trade_date"] = "2026-11-25"
        self.assertIn("S410108:expired_industry_requires_new_episode",
                      validate_industry_lifecycle(wrong, prior, "2026-11-25"))

    def test_deterministic_same_day_revision_audited_and_pair_checked(self):
        previous = copy.deepcopy(DATA["registry"])
        previous["generated_at"] = "2026-11-24T18:30:00+08:00"
        proposed = copy.deepcopy(previous)
        handoff = copy.deepcopy(DATA["handoff"])
        stamp = "2026-11-24T19:15:00+08:00"
        sha = DATA["source_blobs"]["registry"]
        proposed["generated_at"] = handoff["generated_at"] = stamp
        revision = {"previous_registry_blob_sha": sha,
                    "previous_generated_at": previous["generated_at"],
                    "revised_at": stamp,
                    "reason": "依据已核验的实际复核记录修正行业验证阶段及到期退出，不改变市场判断",
                    "changes": [],
                    "industry_review_results": industry_review_records(previous)}
        proposed["scan_audit"]["same_day_revisions"] = [revision]
        with patch("scripts.trend_registry.datetime") as clock:
            clock.now.return_value = datetime.fromisoformat(stamp)
            clock.fromisoformat.side_effect = datetime.fromisoformat
            self.assertEqual(migration_gate(previous, proposed, sha), [])
            self.assertEqual(pair_gate(proposed, handoff), [])
            wrong = copy.deepcopy(proposed)
            wrong["scan_audit"]["same_day_revisions"][0]["industry_review_results"][0]["tracking_active"] = False
            self.assertIn("industry_review_revision_results_mismatch", migration_gate(previous, wrong, sha))
            self.assertIn("industry_review_revision_results_mismatch", pair_gate(wrong, handoff))
            wrong = copy.deepcopy(proposed)
            wrong["trends"][0]["market_state"] = "观察"
            self.assertIn("industry_review_revision_changed_original_research", migration_gate(previous, wrong, sha))

    def test_invalid_pair_blocks_render(self):
        handoff = copy.deepcopy(DATA["handoff"])
        handoff["signals"][0]["industry_display_names"] = ["错误"]
        with self.assertRaises(ValueError):
            render(DATA["registry"], handoff)


if __name__ == "__main__":
    unittest.main()
