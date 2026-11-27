import copy
import hashlib
import json
import tempfile
from unittest.mock import patch
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validate_theme_handoff_routes import check_theme_routes
import intraday_focus_trial as focus


def fixtures():
    handoff = {
        "schema_version": 1, "result_kind": "a_share_trend_handoff",
        "trade_date": "2026-10-09", "signals": [
            {"rank": 1, "trend_name": "农业/粮食安全", "trend_state": "T1",
             "market_state": "候选趋势", "mapping_status": "resolved",
             "industry_codes": ["S110101", "S110502"],
             "industry_names": ["种子", "粮油加工"]}]}
    index = {
        "trade_date": "2026-10-09", "validation": {"status": "passed"},
        "industries": {
            "S110101": {"industry_name": "种子", "company_count": 6,
                        "manifest_file": "path/a", "part_count": 2},
            "S110502": {"industry_name": "粮油加工", "company_count": 8,
                        "manifest_file": "path/b", "part_count": 2},
            "S110102": {"industry_name": "粮食种植", "company_count": 2,
                        "manifest_file": "path/c", "part_count": 1},
        }}
    registry = {
        "result_kind": "a_share_trend_registry", "status": "COMPLETE",
        "trade_date": "2026-10-09", "trends": [
            {"trend_name": "农业/粮食安全", "trend_state": "T1",
             "market_state": "候选趋势", "in_new_position_priority": True,
             "priority_rank": 1,
             "industry_codes": ["S110101", "S110502"],
             "industry_names": ["种子", "粮油加工"]}]}
    return handoff, index, registry


class UpstreamRouteCheckTests(unittest.TestCase):
    def test_existing_contract_accepts_multiple_verified_industry_codes(self):
        handoff, index, registry = fixtures()
        result = check_theme_routes(handoff, index, registry)
        self.assertEqual(result["theme_count"], 1)
        self.assertEqual(result["unique_industry_count"], 2)
        self.assertEqual(result["status"], "ROUTING_IDENTITY_VALIDATED")
        self.assertTrue(result["identity_only"])

    def test_cross_industry_expansion_not_limited_to_initial_seed(self):
        handoff, index, registry = fixtures()
        # S110102 had only 2 stocks; still routeable if upstream research
        # INDEPENDENTLY verifies business and market evidence.
        handoff["signals"][0]["industry_codes"].append("S110102")
        handoff["signals"][0]["industry_names"].append("粮食种植")
        registry["trends"][0]["industry_codes"].append("S110102")
        registry["trends"][0]["industry_names"].append("粮食种植")
        self.assertEqual(check_theme_routes(handoff, index, registry)["unique_industry_count"], 3)

    def test_unknown_code_is_never_published(self):
        handoff, index, registry = fixtures()
        handoff["signals"][0]["industry_codes"][1] = "S999999"
        registry["trends"][0]["industry_codes"][1] = "S999999"
        with self.assertRaisesRegex(ValueError, "no_universe_industry_code"):
            check_theme_routes(handoff, index, registry)

    def test_wrong_code_name_pair_is_blocked(self):
        handoff, index, registry = fixtures()
        handoff["signals"][0]["industry_names"][1] = "种子"
        registry["trends"][0]["industry_names"][1] = "种子"
        with self.assertRaisesRegex(ValueError, "industry_name_code_mismatch"):
            check_theme_routes(handoff, index, registry)

    def test_same_day_required_and_duplicates_rejected(self):
        handoff, index, registry = fixtures()
        index["trade_date"] = "2026-10-08"
        with self.assertRaisesRegex(ValueError, "trade_date_mismatch"):
            check_theme_routes(handoff, index, registry)
        index["trade_date"] = "2026-10-09"
        handoff["signals"][0]["industry_codes"].append("S110101")
        handoff["signals"][0]["industry_names"].append("种子")
        registry["trends"][0]["industry_codes"].append("S110101")
        registry["trends"][0]["industry_names"].append("种子")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            check_theme_routes(handoff, index, registry)

    def test_registry_and_handoff_must_match(self):
        handoff, index, registry = fixtures()
        registry["trends"][0]["industry_codes"] = ["S110101"]
        with self.assertRaisesRegex(ValueError, "registry_route_mismatch"):
            check_theme_routes(handoff, index, registry)

    def test_new_route_can_contain_only_verified_confirmed_subset(self):
        h, idx, r = fixtures()
        day = "2026-10-27"
        r["schema_version"] = 2
        r["trends"][0]["episode_id"] = "合成方向#2026-10-27"
        h["trade_date"] = idx["trade_date"] = r["trade_date"] = day
        r["scan_audit"] = {
            "full_market_scan_completed": True,
            "state_migration_gate": {"mode": "full_close", "current_trade_date": day}
        }
        h["signals"][0]["market_state"] = "趋势确认"
        r["trends"][0]["market_state"] = "趋势确认"
        r["trends"][0]["industry_assessments"] = [
            {"industry_code": "S110101", "industry_name": "种子",
             "market_state": "趋势确认", "benefit_level": "CORE"},
            {"industry_code": "S110502", "industry_name": "粮油加工",
             "market_state": "观察", "benefit_level": "RELATED"}
        ]
        h["signals"][0]["industry_codes"] = ["S110101"]
        h["signals"][0]["industry_names"] = ["种子"]
        self.assertEqual(check_theme_routes(h, idx, r)["unique_industry_count"], 1)
        h["signals"][0]["industry_codes"].append("S110502")
        h["signals"][0]["industry_names"].append("粮油加工")
        with self.assertRaisesRegex(ValueError, "publication_pair_invalid"):
            check_theme_routes(h, idx, r)

    def test_zero_verified_routes_do_not_require_company_index(self):
        h, idx, r = fixtures()
        day = "2026-10-27"
        r["schema_version"] = 2
        r["trends"][0]["episode_id"] = "合成方向#2026-10-27"
        h["trade_date"] = r["trade_date"] = day
        r["scan_audit"] = {
            "full_market_scan_completed": True,
            "state_migration_gate": {"mode": "full_close", "current_trade_date": day}
        }
        r["trends"][0]["in_new_position_priority"] = False
        h["signals"] = []
        self.assertEqual(
            check_theme_routes(h, {}, r)["status"], "NO_ELIGIBLE_CONFIRMED_TREND")
        with self.assertRaisesRegex(ValueError, "registry_required_for_verified_handoff"):
            check_theme_routes(h, {}, None)

    def test_formal_workflow_enforces_pair_and_nothing_to_publish(self):
        root = Path(__file__).resolve().parents[1]
        formal = (root / ".github/workflows/run-trend-buy-formal.yml").read_text()
        direct = (root / "scripts/build_trend_buy_manual_research.py").read_text()
        snapshot = (root / ".github/workflows/update-intraday-snapshot.yml").read_text()
        self.assertIn("check_theme_routes(handoff,index,registry)", formal)
        self.assertIn("NO_ELIGIBLE_CONFIRMED_TREND", formal)
        self.assertEqual(formal.count("if: steps.admission.outputs.should_run == 'true'"), 4)
        # All post-admission steps remain gated; result + handoff are now
        # produced and committed as a single validated pair, not two pushes.
        self.assertIn("run_model_top1_formal.py", formal)
        self.assertIn("git add research/trend_buy_formal_result.json research/trend_buy_handoff.json", formal)
        self.assertIn("TOP1_HANDOFF_SCOPE_VERIFIED", formal)
        self.assertEqual(formal.count("git push origin HEAD:main"), 1)
        self.assertIn("check_theme_routes(trend,index,registry)", direct)
        self.assertIn("NO_ELIGIBLE_CONFIRMED_TREND", direct)
        # The staged snapshot delegates baseline gates to the actual collector.
        # Keep the deployment boundary and readback checks; test runtime behavior below.
        self.assertIn("FOCUS_MODE: SHADOW", snapshot)
        self.assertIn("python3 scripts/intraday_focus_trial.py", snapshot)
        self.assertIn("test_intraday_focus_trial.py", snapshot)
        self.assertIn("git add research/intraday_focus_snapshot.json", snapshot)
        self.assertIn("git show FETCH_HEAD:research/intraday_focus_snapshot.json | cmp - focus_trial_public.json", snapshot)
        self.assertNotIn("git add research/trend_buy_formal_result.json", snapshot)
        self.assertNotIn("git add research/trend_buy_handoff.json", snapshot)

    def test_shadow_baseline_checks_actual_paired_inputs(self):
        day = "2026-11-27"
        registry = {"schema_version": 2, "result_kind": "a_share_trend_registry",
                    "status": "COMPLETE", "trade_date": day,
                    "scan_audit": {"full_market_scan_completed": True,
                                   "state_migration_gate": {"mode": "full_close",
                                                            "current_trade_date": day}},
                    "trends": [{"trend_name": "测试方向", "episode_id": "测试方向#2026-11-27",
                                "trend_state": "T1", "market_state": "趋势确认",
                                "in_new_position_priority": True,
                                "industry_assessments": [{"industry_code": "S110101",
                                                          "industry_name": "种子",
                                                          "market_state": "趋势确认",
                                                          "benefit_level": "CORE"}]}]}
        sector = {"schema_version": 1, "result_kind": "a_share_trend_handoff",
                  "trade_date": day, "signals": [{"rank": 1, "trend_name": "测试方向",
                                                  "trend_state": "T1", "market_state": "趋势确认",
                                                  "industry_codes": ["S110101"],
                                                  "industry_names": ["种子"]}]}
        stock = {"code": "600105", "company_name": "测试公司", "industry_code": "S110101",
                 "industry_name": "种子", "trend_name": "测试方向", "market_state": "趋势确认",
                 "status": "WAIT", "wait_reason": "WAIT_CONFIRMATION"}
        formal = {"schema_version": "trend_buy_result_v2", "status": "COMPLETE",
                  "production_eligible": True, "selection_policy": "MODEL_TOP1_V1_6_R1",
                  "trade_date": day, "run_id": "fixture-run", "ready": [], "wait": [stock],
                  "top1_by_industry": [{"industry_code": "S110101", "trend_name": "测试方向",
                                        "items": [{"code": "600105", "reference": None}]}],
                  "top1_decisions": [{"industry_code": "S110101", "top1_code": "600105",
                                      "risk_status": "WAIT"}]}
        raw = json.dumps(formal, ensure_ascii=False).encode("utf-8")
        sha = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        handoff = focus.project(formal, sha, shadow=False)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            research = root / "research"
            research.mkdir()
            def write(name, value):
                (research / name).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            (research / "trend_buy_formal_result.json").write_bytes(raw)
            write("trend_registry.json", registry)
            write("trend_handoff.json", sector)
            write("trend_buy_handoff.json", handoff)
            with patch.object(focus, "ROOT", root):
                self.assertEqual(focus.baseline(day)["symbols"], ["sh600105"])
                # Real production projector detects a changed source hash or roster.
                tampered = copy.deepcopy(handoff)
                tampered["source_formal_blob_sha"] = "0" * 40
                write("trend_buy_handoff.json", tampered)
                with self.assertRaisesRegex(ValueError, "BASELINE_PAIR"):
                    focus.baseline(day)
                write("trend_buy_handoff.json", handoff)
                # A valid pair from another session is not a fresh baseline.
                with self.assertRaisesRegex(ValueError, "BASELINE_DATE"):
                    focus.baseline("2026-11-30")
                bad_sector = copy.deepcopy(sector)
                bad_sector["signals"][0]["industry_codes"] = ["S999999"]
                write("trend_handoff.json", bad_sector)
                with self.assertRaisesRegex(ValueError, "BASELINE_PAIR"):
                    focus.baseline(day)
                # Valid empty sector pair cannot resurrect the same-date old buy list.
                empty_registry = copy.deepcopy(registry)
                empty_registry["trends"][0]["in_new_position_priority"] = False
                write("trend_registry.json", empty_registry)
                write("trend_handoff.json", {**sector, "signals": []})
                with self.assertRaisesRegex(ValueError, "BASELINE_NO_ELIGIBLE_TREND"):
                    focus.baseline(day)
                self.assertEqual(focus.wrapped(lambda: focus.baseline(day))["status"], "failed")

    def test_empty_company_pool_fails(self):
        handoff, index, registry = fixtures()
        index["industries"]["S110502"]["company_count"] = 0
        with self.assertRaisesRegex(ValueError, "no_universe_member"):
            check_theme_routes(handoff, index, registry)


if __name__ == "__main__":
    unittest.main()
