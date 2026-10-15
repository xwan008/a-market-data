import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_theme_evidence import build


def sample_data():
    day = "2026-10-09"
    latest = {"trade_date": day, "market_status": "closed", "stocks": {}}
    industry = {"companies": {}}
    structure = {"reference_trade_date": day, "companies": {}}
    for i in range(18):
        code = f"{i+1:06d}"
        if i < 6:
            ic, iname, change, r3, r5 = "S100101", "Test core industry", 4, 6, 4
        elif i < 12:
            ic, iname, change, r3, r5 = "S200101", "Related only", -3, -4, -2
        else:
            ic, iname, change, r3, r5 = "S300101", "Unmapped hot", 3, 4, 3
        latest["stocks"][code] = {"change_pct": change, "confidence": "high"}
        industry["companies"][code] = {"mapping_status": "mapped", "industry_code": ic,
                                      "sw_level3_name": iname}
        structure["companies"][code] = {
            "data_status": "verified", "data_date": day,
            "phase_evidence": {"return_3d_pct": r3, "return_5d_pct": r5,
                               "volume_ratio_1d": 1.5}}
    catalog = {"schema_version": 1, "result_kind": "a_share_static_theme_industry_catalog",
               "catalog_version": "test-1", "catalog_as_of_date": day,
               "authority": "AUXILIARY_ONLY",
               "themes": [
                   {"theme_id": "test", "theme_name": "Test trend", "aliases": ["Test trend"],
                    "industries": [
                        {"code": "S100101", "name": "Test core industry", "role": "core"},
                        {"code": "S200101", "name": "Related only", "role": "related"}]},
                   {"theme_id": "weak", "theme_name": "Weak group", "aliases": ["Weak group"],
                    "industries": [
                        {"code": "S200101", "name": "Related only", "role": "core"}]}
               ]}
    registry = {
        "result_kind": "a_share_trend_registry", "trade_date": day,
        "trends": [
            {"trend_name": "Test trend", "lifecycle_status": "有效"},
            {"trend_name": "Weak group", "lifecycle_status": "有效"},
            {"trend_name": "Model only", "lifecycle_status": "有效"}
        ]
    }
    audit = {
        "trade_date": day, "industry_count": 3,
        "sectors": [
            {"kind": "industry", "id": "industry:S300101", "name": "Unmapped hot",
             "channels": ["STRONG"], "score": 5.1, "sample_quality": "OK",
             "member_count": 6, "median_1d_pct": 3,
             "advance_ratio": 1,
             "relative_1d_vs_market_median_pct": 3.0},
            {"kind": "industry", "id": "industry:S100101", "name": "Test core industry",
             "channels": ["STRONG"], "score": 6, "sample_quality": "OK",
             "member_count": 6, "median_1d_pct": 4,
             "advance_ratio": 1,
             "relative_1d_vs_market_median_pct": 4.0}
        ]
    }
    return latest, industry, structure, catalog, registry, audit


class ThemeEvidenceTests(unittest.TestCase):
    def test_compact_shortlist_core_only_and_research_only_roles(self):
        result = build(*sample_data())
        self.assertEqual(result["scan_summary"]["themes_evaluated"], 2)
        self.assertEqual(len(result["research_candidates"]), 1)
        candidate = result["research_candidates"][0]
        self.assertEqual(candidate["theme_id"], "test")
        self.assertEqual(candidate["core_stock_count"], 6)
        self.assertEqual(candidate["usable_stock_count"], 6)
        self.assertEqual(candidate["breadth_1d"], 1)
        self.assertEqual(candidate["median_return_1d_pct"], 4)
        self.assertEqual(candidate["related_industry_codes_not_scored"], ["S200101"])
        self.assertNotIn("core_industries", candidate)
        self.assertTrue(result["no_trade_signal"])
        self.assertTrue(result["auxiliary_only"])
        self.assertEqual(result["decision_authority"], "legacy_model_driven_trend_research")
        self.assertNotIn("trend_state", candidate)
        self.assertNotIn("priority_rank", candidate)
        self.assertEqual(len(result["unmapped_industry_alerts"]), 1)
        self.assertEqual(result["unmapped_industry_alerts"][0]["industry_code"], "S300101")

    def test_known_old_trend_weakness_only_generates_alert(self):
        result = build(*sample_data())
        self.assertEqual(len(result["tracked_theme_alerts"]), 1)
        alert = result["tracked_theme_alerts"][0]
        self.assertEqual(alert["theme_name"], "Weak group")
        self.assertIn("WEAK_BREADTH_AND_PRICE", alert["reason_codes"])
        self.assertIn("Model only", result["scan_summary"]["unknown_tracked_themes"])
        self.assertNotIn("trend_state", alert)
        self.assertNotIn("invalidation", alert)

    def test_not_all_themes_are_written_to_snapshot(self):
        result = build(*sample_data(), max_research=1)
        self.assertEqual(len(result["research_candidates"]), 1)
        self.assertNotIn("full_theme_metrics", result)
        self.assertEqual(result["scan_summary"]["all_theme_detail_retention"],
                         "computed_in_memory_not_persisted")

    def test_low_sample_theme_does_not_become_candidate(self):
        data = list(sample_data())
        for code in list(data[1]["companies"]):
            if data[1]["companies"][code]["industry_code"] == "S100101" and int(code) > 4:
                data[1]["companies"].pop(code)
        result = build(*data)
        self.assertEqual(len(result["research_candidates"]), 0)
        self.assertEqual(result["scan_summary"]["invalid_or_low_sample_themes"], 1)

    def test_catalog_asof_future_and_retrospective_label(self):
        data = list(sample_data())
        data[3] = copy.deepcopy(data[3])
        data[3]["catalog_as_of_date"] = "2026-10-11"
        with self.assertRaisesRegex(ValueError, "point_in_time_violation"):
            build(*data)
        retrospective = build(*data, retrospective=True)
        self.assertEqual(retrospective["status"], "RETROSPECTIVE_MAPPING_SMOKE")
        self.assertFalse(retrospective["point_in_time_eligible"])

    def test_strict_date_and_mapping_gates(self):
        data = list(sample_data())
        data[2] = copy.deepcopy(data[2])
        data[2]["reference_trade_date"] = "2026-10-08"
        with self.assertRaisesRegex(ValueError, "structure_date_mismatch"):
            build(*data)
        data = list(sample_data())
        data[3] = copy.deepcopy(data[3])
        data[3]["themes"][0]["industries"][0]["name"] = "Invented"
        with self.assertRaisesRegex(ValueError, "catalog_industry_not_in_same_universe"):
            build(*data)
        data = list(sample_data())
        data[5] = copy.deepcopy(data[5])
        data[5]["trade_date"] = "2026-10-08"
        with self.assertRaisesRegex(ValueError, "sector_audit_date_or_coverage_mismatch"):
            build(*data)
        data = list(sample_data())
        data[4] = copy.deepcopy(data[4])
        data[4]["trade_date"] = "2026-10-10"
        with self.assertRaisesRegex(ValueError, "future_or_invalid_registry"):
            build(*data)

    def test_catalog_does_not_become_handoff_or_apply_alias_scores(self):
        data = list(sample_data())
        data[3] = copy.deepcopy(data[3])
        data[3]["authority"] = "PRIMARY"
        with self.assertRaisesRegex(ValueError, "catalog_cannot_be_authoritative"):
            build(*data)
        data = list(sample_data())
        data[3] = copy.deepcopy(data[3])
        data[3]["themes"][0]["industries"].append(
            {"code": "S100101", "name": "Test core industry", "role": "core"})
        with self.assertRaisesRegex(ValueError, "catalog_invalid_industry_code"):
            build(*data)

    def test_committed_catalog_has_complete_disjoint_331_sector_taxonomy(self):
        import json
        root = Path(__file__).resolve().parents[1]
        catalog = json.loads((root / "research/theme_industry_catalog.json").read_text(encoding="utf-8"))
        universe = json.loads((root / "data/low_risk/index.json").read_text(encoding="utf-8"))
        groups = catalog["base_industry_groups"]
        codes = [industry["code"] for group in groups for industry in group["industries"]]
        self.assertEqual(len(groups), 131)
        self.assertEqual(len(codes), 331)
        self.assertEqual(len(set(codes)), 331)
        self.assertEqual(set(codes), set(universe["industries"]))
        self.assertEqual(len(catalog["themes"]), 17)
        for group in groups:
            self.assertEqual(group["sw_level2_code"][-2:], "00")
            self.assertEqual(group["industry_count"], len(group["industries"]))
            for industry in group["industries"]:
                self.assertEqual(industry["code"][1:5], group["sw_level2_code"][:4])
                self.assertEqual(industry["name"],
                                 universe["industries"][industry["code"]]["industry_name"])

    def test_taxonomy_groups_are_an_independent_market_evidence_layer(self):
        data = list(sample_data())
        # Make both strong independent groups beat a low overall market median.
        for i in range(19, 26):
            code = f"{i:06d}"
            data[0]["stocks"][code] = {"change_pct": -3, "confidence": "high"}
            data[1]["companies"][code] = {
                "mapping_status": "mapped", "industry_code": "S200101",
                "sw_level3_name": "Related only"}
            data[2]["companies"][code] = {
                "data_status": "verified", "data_date": data[0]["trade_date"],
                "phase_evidence": {"return_3d_pct": -4, "return_5d_pct": -2,
                                   "volume_ratio_1d": 1.5}}
        data[3] = copy.deepcopy(data[3])
        data[3]["base_industry_groups"] = [
            {"group_id": f"sw_l2_{prefix}", "group_name": label,
             "group_kind": "SW_L2_TAXONOMY", "sw_level2_code": prefix+"00",
             "industry_count": 1,
             "industries": [{"code": sector, "name": name, "role": "core"}]}
            for prefix, sector, name, label in [
                ("1001", "S100101", "Test core industry", "test base"),
                ("2001", "S200101", "Related only", "related base"),
                ("3001", "S300101", "Unmapped hot", "unmapped base"),
            ]
        ]
        result = build(*data, max_research=3)
        self.assertEqual(result["scan_summary"]["taxonomy_groups_evaluated"], 3)
        self.assertEqual(result["scan_summary"]["taxonomy_covered_level3_industries"], 3)
        self.assertEqual(result["scan_summary"]["themes_evaluated"], 2)
        self.assertEqual(result["scan_summary"]["curated_candidates_returned"], 1)
        self.assertEqual(result["scan_summary"]["taxonomy_candidates_returned"], 1)
        self.assertEqual(len(result["research_candidates"]), 2)
        self.assertEqual({x["evidence_group_type"] for x in result["research_candidates"]},
                         {"RESEARCH_THEME", "SW_L2_TAXONOMY"})
        self.assertEqual(result["unmapped_industry_alerts"][0]["industry_code"], "S300101")
        self.assertTrue(result["auxiliary_only"])

    def test_taxonomy_missing_duplicate_and_misplaced_industry_fail_closed(self):
        data = list(sample_data())
        data[3] = copy.deepcopy(data[3])
        baseline = [
            {"group_id": f"sw_l2_{prefix}", "group_name": label,
             "group_kind": "SW_L2_TAXONOMY", "sw_level2_code": prefix+"00",
             "industry_count": 1,
             "industries": [{"code": sector, "name": name, "role": "core"}]}
            for prefix, sector, name, label in [
                ("1001", "S100101", "Test core industry", "test base"),
                ("2001", "S200101", "Related only", "related base"),
                ("3001", "S300101", "Unmapped hot", "unmapped base"),
            ]
        ]
        data[3]["base_industry_groups"] = baseline[:-1]
        with self.assertRaisesRegex(ValueError, "taxonomy_incomplete_level3_coverage"):
            build(*data)
        data[3]["base_industry_groups"] = copy.deepcopy(baseline)
        data[3]["base_industry_groups"][1]["group_id"] = "sw_l2_1001"
        with self.assertRaisesRegex(ValueError, "taxonomy_invalid_group_identity"):
            build(*data)
        data[3]["base_industry_groups"] = copy.deepcopy(baseline)
        data[3]["base_industry_groups"][2]["sw_level2_code"] = "100100"
        with self.assertRaisesRegex(ValueError, "taxonomy_code_hierarchy_mismatch"):
            build(*data)

    def test_regression_flags_model_first_protocol_and_source(self):
        protocol = (Path(__file__).resolve().parents[1]
                    / "skill/TREND_REGISTRY_PROTOCOL.md").read_text(encoding="utf-8")
        self.assertIn("Python只负责客观行情计算和必要技术校验", protocol)
        self.assertIn("不作为第二个趋势发现者", protocol)
        self.assertIn("全行业及主要概念板块客观数据", protocol)
        self.assertIn("不能因旧池或热门板块限制扫描范围", protocol)
        self.assertIn("状态不是必须逐级经过的机械序列", protocol)


if __name__ == "__main__":
    unittest.main()
