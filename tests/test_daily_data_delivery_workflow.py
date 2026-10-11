"""Regression tests for optional Python evidence publishing and readback guards."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/update-data.yml"


def embedded_python():
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    blocks = []
    for idx, line in enumerate(lines):
        if line.strip() != "python - <<'PY'":
            continue
        indent = len(line) - len(line.lstrip())
        code_lines = []
        for raw in lines[idx + 1:]:
            if raw.strip() == "PY" and len(raw) - len(raw.lstrip()) == indent:
                break
            code_lines.append(raw[indent:] if raw.startswith(" " * indent) else raw)
        else:
            raise AssertionError("unterminated Python heredoc")
        blocks.append("\n".join(code_lines))
    return blocks


class DailyEvidenceWorkflowTests(unittest.TestCase):
    def test_every_embedded_python_block_compiles(self):
        blocks = embedded_python()
        self.assertGreaterEqual(len(blocks), 5)
        for index, block in enumerate(blocks):
            with self.subTest(index=index):
                compile(block, f"daily-workflow-{index}.py", "exec")

    def test_momentum_and_git_readback_guards_present(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("MOMENTUM_SHARDS_VERIFIED", workflow)
        self.assertIn("DAILY_DATA_AND_AUXILIARY_READBACK_OK", workflow)
        self.assertIn("git add -A data", workflow)
        self.assertIn("git fetch origin main --quiet", workflow)
        self.assertNotIn("run: python scripts/build_full_market_price_structure.py", workflow)
        self.assertLess(workflow.index("python scripts/build_bridge.py"),
                        workflow.index("MOMENTUM_SHARDS_VERIFIED"))
        self.assertLess(workflow.index("rm -f data/research/sector_discovery_snapshot.json"),
                        workflow.index("python scripts/build_sector_discovery.py"))

    def test_auxiliary_contracts_and_missing_files_fail_closed(self):
        block = next(x for x in embedded_python() if "AUXILIARY_STATUS" in x)
        day = "2026-10-12"
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "data/research").mkdir(parents=True)
            (root / "data/latest.json").write_text(json.dumps({"trade_date": day}))
            sector = root / "data/research/sector_discovery_snapshot.json"
            audit = root / "data/research/sector_discovery_audit.json"
            theme = root / "data/research/theme_evidence_snapshot.json"
            sector.write_text(json.dumps({
                "schema_version": 1, "result_kind": "sector_discovery_snapshot",
                "trade_date": day, "no_trade_signal": True, "status": "INDUSTRY_ONLY_PARTIAL"}))
            audit.write_text(json.dumps({"schema_version": 1, "trade_date": day}))
            theme.write_text(json.dumps({
                "schema_version": 1, "result_kind": "a_share_theme_evidence_snapshot",
                "trade_date": day, "status": "COMPLETE", "point_in_time_eligible": True,
                "catalog_as_of_date": "2026-10-11", "no_trade_signal": True,
                "auxiliary_only": True}))
            env = os.environ.copy()
            env["GITHUB_STEP_SUMMARY"] = str(root / "summary.md")
            a = subprocess.run([sys.executable, "-c", block], cwd=root,
                               env=env, capture_output=True, text=True)
            self.assertEqual(a.returncode, 0, a.stderr)
            self.assertIn("sector_discovery=INDUSTRY_ONLY_PARTIAL", a.stdout)
            self.assertIn("theme_evidence=COMPLETE", a.stdout)
            self.assertTrue(sector.exists())
            self.assertTrue(theme.exists())

            # Old or future-dated evidence is removed, not silently committed.
            theme.write_text(json.dumps({
                "schema_version": 1, "result_kind": "a_share_theme_evidence_snapshot",
                "trade_date": day, "status": "COMPLETE", "point_in_time_eligible": True,
                "catalog_as_of_date": "2026-10-13", "no_trade_signal": True,
                "auxiliary_only": True}))
            audit.write_text(json.dumps({"schema_version": 1, "trade_date": "2026-10-09"}))
            b = subprocess.run([sys.executable, "-c", block], cwd=root,
                               env=env, capture_output=True, text=True)
            self.assertEqual(b.returncode, 0, b.stderr)
            self.assertIn("sector_discovery=UNAVAILABLE", b.stdout)
            self.assertIn("theme_evidence=UNAVAILABLE", b.stdout)
            self.assertFalse(sector.exists())
            self.assertFalse(audit.exists())
            self.assertFalse(theme.exists())
            self.assertIn("::warning", b.stdout)


if __name__ == "__main__":
    unittest.main()
