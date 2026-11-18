import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_low_risk_working_sets.py"


class ChunkOnlyWorkingSetsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.index = self.root / "companies.json"
        self.shards = self.root / "shards"
        self.output = self.root / "output"
        self.shards.mkdir()
        companies = {}
        stocks = {}
        for n in range(1, 8):
            code = f"60000{n}"
            industry = "S110101" if n < 7 else "S110102"
            companies[code] = {"mapping_status": "mapped", "industry_code": industry,
                               "sw_level3_name": industry, "name": "公司" + str(n)}
            stocks[code] = {"name": "公司" + str(n), "price": n + 10,
                            "sw_level3_code": industry,
                            "fundamentals": {"revenue_yoy": n, "deduct_net_profit_yoy": n * 2}}
        self.index.write_text(json.dumps({"companies": companies}), encoding="utf-8")
        self.shard = self.shards / "60000.json"
        self.shard.write_text(json.dumps({"trade_date": "2026-11-17", "stocks": stocks}),
                              encoding="utf-8")

    def run_builder(self):
        return subprocess.run([sys.executable, str(SCRIPT), "--industry-index", str(self.index),
                               "--shard-dir", str(self.shards), "--output-dir", str(self.output)],
                              capture_output=True, text=True)

    def test_regeneration_removes_legacy_files_and_preserves_complete_chunk_routes(self):
        industry_dir = self.output / "by_industry"
        industry_dir.mkdir(parents=True)
        (industry_dir / "S110101.json").write_text("old compatibility file")
        stale = industry_dir / "S999999"
        stale.mkdir()
        (stale / "part-001.json").write_text("obsolete part")
        result = self.run_builder()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list(industry_dir.glob("*.json")), [])
        self.assertFalse(stale.exists())
        index = json.loads((self.output / "index.json").read_text())
        self.assertEqual((index["industry_count"], index["company_count"]), (2, 7))
        self.assertEqual(index["chunking"]["total_parts"], 3)
        self.assertNotIn("legacy_single_file_retained", index["chunking"])
        seen = []
        for code, entry in index["industries"].items():
            self.assertNotIn("file", entry)
            self.assertNotIn("legacy_file", entry)
            manifest = json.loads(Path(entry["manifest_file"]).read_text())
            self.assertNotIn("legacy_file", manifest["source"])
            rows = []
            for part in manifest["parts"]:
                raw = Path(part["file"]).read_bytes()
                self.assertEqual(len(raw), part["byte_size"])
                payload = json.loads(raw)
                self.assertEqual(payload["trade_date"], "2026-11-17")
                self.assertEqual(payload["industry_code"], code)
                self.assertEqual(payload["company_codes"], part["company_codes"])
                self.assertLessEqual(len(payload["companies"]), 5)
                rows.extend(payload["companies"])
            self.assertEqual([r["code"] for r in rows], manifest["universe_company_codes"])
            for row in rows:
                n = int(row["code"][-1])
                self.assertEqual(row["price"], n + 10)
                self.assertEqual(row["deduct_net_profit_yoy"], n * 2)
            seen.extend(r["code"] for r in rows)
        self.assertEqual(sorted(seen), [f"60000{n}" for n in range(1, 8)])
        self.assertEqual(self.run_builder().returncode, 0)
        self.assertEqual(list(industry_dir.glob("*.json")), [])

    def test_missing_source_does_not_destroy_existing_publication(self):
        self.assertEqual(self.run_builder().returncode, 0)
        before = {p.relative_to(self.output): p.read_bytes()
                  for p in self.output.rglob("*.json")}
        self.shard.unlink()
        result = self.run_builder()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing_shards", result.stderr)
        self.assertEqual(before, {p.relative_to(self.output): p.read_bytes()
                                  for p in self.output.rglob("*.json")})

    def test_industry_mismatch_blocks_publication(self):
        shard = json.loads(self.shard.read_text())
        shard["stocks"]["600001"]["sw_level3_code"] = "S999999"
        self.shard.write_text(json.dumps(shard), encoding="utf-8")
        result = self.run_builder()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("industry_mismatches", result.stderr)
        self.assertFalse((self.output / "index.json").exists())


if __name__ == "__main__":
    unittest.main()
