"""Synthetic accounting scenarios, not historical research or stock recommendations."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from research_audit import initialise, validate, write

SHA = "a" * 40


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.runtime = self.root / "data/runtime"
        self.run_dir = self.root / "data/research_runs/test-run"
        self.runtime.mkdir(parents=True)
        columns = ["code", "name", "industry_code"]
        write(self.runtime / "meta.json", {
            "runtime_kind": "low_risk_research", "runtime_validation": {"status": "passed"},
            "snapshot": {"trade_date": "2026-09-11", "counts": {"candidates": 4}},
            "source_candidate_count": 4, "screening_count": 4, "industry_count": 4,
            "screening_columns": columns, "industry_columns": ["code", "name"],
            "screening_file": "data/runtime/screening_snapshot.json",
            "industry_state_file": "data/runtime/industry_state_compact.json",
            "detail_file_template": "data/runtime/details/{code}.json",
        })
        write(self.runtime / "screening_snapshot.json", {
            "trade_date": "2026-09-11", "columns": columns,
            "rows": [["000001", "Synthetic A", "I1"], ["000002", "Synthetic B", "I1"],
                     ["000003", "Synthetic C", "I2"], ["000004", "Synthetic D", "I3"]],
        })
        write(self.runtime / "industry_state_compact.json", {
            "trade_date": "2026-09-11", "columns": ["code", "name"],
            "rows": [["I1", "One"], ["I2", "Two"], ["I3", "Three"], ["I4", "Empty"]],
        })
        self.run = {"run_id": "test-run", "locked_sha": SHA, "trade_date": "2026-09-11",
                    "stage": "final", "group_files": ["groups/one.json", "groups/two.json"],
                    "notable_codes": ["000002", "000004"]}
        self.industries = [{"industry_code": code, "decision": decision,
                            "reason": "Synthetic industry finding", "source_refs": ["fixture:industry"]}
                           for code, decision in [("I1", "research"), ("I2", "uncertain"),
                                                  ("I3", "excluded"), ("I4", "no_candidates")]]

        def member(code, decision, status=None):
            item = {"code": code, "decision": decision, "reason": "Synthetic comparison reason",
                    "comparisons": {d: {"status": "assessed", "finding": "Synthetic finding", "source_refs": ["fixture:statement"]}
                                    for d in ["earnings_quality", "cashflow", "valuation"]}}
            if decision == "excluded":
                item.update(preferred_codes=["000001"], revisit_condition="Synthetic valuation convergence")
            else:
                item["detail_read"] = {"locked_sha": SHA, "path": f"data/runtime/details/{code}.json", "eof_confirmed": True}
                item["outcome"] = {"status": status, "stage": "ranking", "reason": "Synthetic final finding",
                                   "source_refs": ["fixture:research"], "company_confirmed": True,
                                   "entry_admitted": status == "recommended", "asymmetry_passed": status == "recommended"}
            return item

        self.groups = {
            "one": {"group_id": "one", "business_basis": "Synthetic comparable business", "source_refs": ["fixture:business"],
                    "members": [member("000001", "winner", "recommended"), member("000002", "excluded")]},
            "two": {"group_id": "two", "business_basis": "Different synthetic driver", "source_refs": ["fixture:business"],
                    "members": [member("000003", "research_uncertain", "waiting")]},
        }

    def save(self):
        write(self.run_dir / "run.json", self.run)
        write(self.run_dir / "industries.json", self.industries)
        for name, group in self.groups.items():
            write(self.run_dir / "groups" / f"{name}.json", group)

    def check(self):
        self.save()
        return validate(self.run_dir, self.runtime, self.run["locked_sha"])

    def test_complete_final_and_every_company_destination(self):
        report, index = self.check()
        self.assertTrue(report["publishable"])
        self.assertEqual(report["deep_read_codes"], ["000001", "000003"])
        self.assertEqual(report["counts"]["final_recommendation_count"], 1)
        self.assertEqual(set(index), {"000001", "000002", "000003", "000004"})
        self.assertEqual(index["000002"]["allocation"], "excluded")
        self.assertEqual(index["000004"]["allocation"], "excluded_industry")

    def test_cannot_stop_comparison_before_valuation(self):
        del self.groups["one"]["members"][1]["comparisons"]["valuation"]
        with self.assertRaisesRegex(ValueError, "valuation"):
            self.check()

    def test_uncertain_valuation_cannot_exclude(self):
        self.groups["one"]["members"][1]["comparisons"]["valuation"]["status"] = "uncertain"
        with self.assertRaisesRegex(ValueError, "cannot exclude"):
            self.check()

    def test_uncertain_candidate_can_be_retained_without_cap(self):
        b = self.groups["one"]["members"][1]
        b["decision"] = "research_uncertain"
        b["comparisons"]["valuation"]["status"] = "uncertain"
        self.run["stage"] = "allocation"
        report, _ = self.check()
        self.assertEqual(report["deep_read_codes"], ["000001", "000002", "000003"])
        self.assertFalse(report["publishable"])

    def test_missing_candidate_cannot_silently_disappear(self):
        self.groups["one"]["members"].pop()
        with self.assertRaisesRegex(ValueError, "coverage incomplete"):
            self.check()

    def test_duplicate_candidate_rejected(self):
        self.groups["two"]["members"].append(copy.deepcopy(self.groups["one"]["members"][0]))
        with self.assertRaisesRegex(ValueError, "more than one"):
            self.check()

    def test_group_exclusion_requires_retained_peer(self):
        self.groups["one"]["members"][1]["preferred_codes"] = ["000003"]
        with self.assertRaisesRegex(ValueError, "same group"):
            self.check()

    def test_missing_cashflow_evidence_rejected(self):
        self.groups["one"]["members"][1]["comparisons"]["cashflow"]["source_refs"] = []
        with self.assertRaisesRegex(ValueError, "cashflow finding/evidence"):
            self.check()

    def test_no_candidates_cannot_hide_populated_industry(self):
        self.industries[2]["decision"] = "no_candidates"
        with self.assertRaisesRegex(ValueError, "silently omitted"):
            self.check()

    def test_industry_coverage_must_be_exact(self):
        self.industries.pop()
        with self.assertRaisesRegex(ValueError, "industry coverage"):
            self.check()

    def test_no_unlisted_group_files(self):
        self.run["group_files"].pop()
        with self.assertRaisesRegex(ValueError, "manifest"):
            self.check()

    def test_empty_board_still_requires_outcomes(self):
        del self.groups["two"]["members"][0]["outcome"]
        with self.assertRaisesRegex(ValueError, "final destination"):
            self.check()

    def test_valid_empty_board(self):
        o = self.groups["one"]["members"][0]["outcome"]
        o.update(status="waiting", entry_admitted=False, asymmetry_passed=False)
        report, _ = self.check()
        self.assertTrue(report["publishable"])
        self.assertEqual(report["counts"]["final_recommendation_count"], 0)

    def test_detail_read_must_use_same_commit(self):
        self.groups["two"]["members"][0]["detail_read"]["locked_sha"] = "b" * 40
        with self.assertRaisesRegex(ValueError, "detail-read"):
            self.check()

    def test_recommendation_requires_all_admissions(self):
        self.groups["one"]["members"][0]["outcome"]["asymmetry_passed"] = False
        with self.assertRaisesRegex(ValueError, "recommended before"):
            self.check()

    def test_runtime_sha_and_date_mismatch_rejected(self):
        self.save()
        with self.assertRaisesRegex(ValueError, "differs"):
            validate(self.run_dir, self.runtime, "b" * 40)
        self.run["trade_date"] = "2026-09-10"
        with self.assertRaisesRegex(ValueError, "trade_date"):
            self.check()

    def test_template_is_incomplete_and_cannot_overwrite_history(self):
        initialise(self.runtime, self.run_dir, "test-run", SHA, ["000001"])
        report, _ = validate(self.run_dir, self.runtime, SHA)
        self.assertEqual(report["status"], "incomplete")
        self.assertFalse(report["publishable"])
        with self.assertRaisesRegex(ValueError, "overwrite"):
            initialise(self.runtime, self.run_dir, "test-run", SHA, [])

    def test_modified_evidence_changes_fingerprint(self):
        first, _ = self.check()
        self.groups["one"]["members"][1]["reason"] += " revised"
        second, _ = self.check()
        self.assertNotEqual(first["audit_sha256"], second["audit_sha256"])

    def test_cli_failure_replaces_prior_success_report(self):
        self.save()
        report_dir = self.root / "reports"
        script = Path(__file__).resolve().parents[1] / "scripts/research_audit.py"
        command = [sys.executable, str(script), "validate", str(self.run_dir),
                   "--runtime-dir", str(self.runtime), "--expected-sha", SHA,
                   "--report-dir", str(report_dir)]
        success = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(success.returncode, 0, success.stderr)
        self.groups["one"]["members"][1]["comparisons"].pop("valuation")
        self.save()
        failure = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(failure.returncode, 1)
        self.assertFalse(json.loads((report_dir / "validation.json").read_text())["publishable"])
        self.assertEqual(json.loads((report_dir / "company_outcomes.json").read_text()), {})

    def test_ci_uses_recorded_runtime_not_newer_snapshot(self):
        def git(*args):
            return subprocess.check_output(["git", *args], cwd=self.root, stderr=subprocess.DEVNULL).decode().strip()
        git("init", "-q")
        git("config", "user.name", "Synthetic Test")
        git("config", "user.email", "test@example.invalid")
        git("add", "data/runtime")
        git("commit", "-qm", "synthetic runtime")
        sha = git("rev-parse", "HEAD")
        self.run["locked_sha"] = sha
        for group in self.groups.values():
            for member in group["members"]:
                if "detail_read" in member:
                    member["detail_read"]["locked_sha"] = sha
        self.save()
        # Current runtime changes: historical audit must still validate against sha.
        write(self.runtime / "meta.json", {"bad_new_runtime": True})
        git("add", "data")
        git("commit", "-qm", "synthetic audit plus unrelated newer data")
        event = self.root / "event.json"
        write(event, {"before": sha})
        script = Path(__file__).resolve().parents[1] / "scripts/check_research_audits.py"
        env = dict(os.environ, GITHUB_EVENT_PATH=str(event), AUDIT_RUN_DIR="")
        result = subprocess.run([sys.executable, str(script)], cwd=self.root, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads((self.root / "audit-reports/test-run/validation.json").read_text())
        self.assertTrue(report["publishable"])
        self.assertEqual(report["locked_sha"], sha)


if __name__ == "__main__":
    unittest.main()
