import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_sector_discovery import build


def inputs():
    trade_date = "2026-10-09"
    latest = {"trade_date": trade_date, "market_status": "closed", "stocks": {}}
    industry = {"companies": {}}
    structure = {"reference_trade_date": trade_date, "companies": {}}
    for i in range(12):
        code = f"{i+1:06d}"
        is_hot = i < 6
        latest["stocks"][code] = {"change_pct": 3 if is_hot else -1, "confidence": "high"}
        industry["companies"][code] = {
            "mapping_status": "mapped", "industry_code": "S100101" if is_hot else "S200101",
            "sw_level3_name": "Sample hot" if is_hot else "Sample weak"}
        structure["companies"][code] = {
            "data_status": "verified", "data_date": trade_date,
            "phase_evidence": {"return_3d_pct": 4 if is_hot else -2,
                               "return_5d_pct": 2 if is_hot else -3,
                               "volume_ratio_1d": 1.8 if is_hot else .8}}
    return latest, industry, structure


class SectorDiscoveryTests(unittest.TestCase):
    def test_missing_historical_participation_does_not_invent_breadth(self):
        latest, industry, structure = inputs()
        for code in ("000001", "000002"):
            structure["companies"][code]["phase_evidence"]["return_3d_pct"] = None
            structure["companies"][code]["phase_evidence"]["return_5d_pct"] = None
        _, audit = build(latest, industry, structure)
        hot = next(x for x in audit["sectors"] if x["id"] == "industry:S100101")
        self.assertEqual(hot["usable_3d_count"], 4)
        self.assertIsNone(hot["breadth_3d"])
        self.assertIsNone(hot["breadth_5d"])

    def test_industry_only_does_not_claim_concept_coverage(self):
        snap, audit = build(*inputs())
        self.assertEqual(snap["status"], "INDUSTRY_ONLY_PARTIAL")
        self.assertEqual(audit["industry_count"], 2)
        self.assertEqual(audit["concept_coverage_status"], "UNAVAILABLE_NO_MEMBERSHIP")
        hot = next(x for x in audit["sectors"] if x["id"] == "industry:S100101")
        self.assertEqual(hot["breadth_3d"], 1.0)
        self.assertEqual(hot["breadth_5d"], 1.0)
        self.assertEqual(hot["usable_3d_count"], 6)
        self.assertEqual(hot["usable_5d_count"], 6)
        self.assertEqual(len(snap["model_research_candidates"]), 1)
        self.assertEqual(snap["model_research_candidates"][0]["name"], "Sample hot")
        self.assertEqual(snap["model_research_candidates"][0]["channels"], ["STRONG", "EMERGING"])
        self.assertTrue(snap["no_trade_signal"])
        self.assertEqual(snap["discovery_role"]["mode"], "AUXILIARY_EVIDENCE_ONLY")
        self.assertEqual(snap["discovery_role"]["primary_research"],
                         "independent_full_market_research")
        self.assertFalse(snap["discovery_role"]["may_set_new_position_priority"])
        self.assertFalse(snap["discovery_role"]["may_determine_trend_state"])
        self.assertFalse(snap["discovery_role"]["may_override_independent_existing_trend"])
        self.assertFalse(snap["discovery_role"]["missing_discovery_blocks_primary_research"])
        self.assertTrue(snap["theme_research_budget"]["does_not_limit_model_independent_research"])
        self.assertEqual(snap["theme_research_budget"]["scope"],
                         "supplemental_program_discovery_only")

    def test_protocol_preserves_original_model_decision_priority(self):
        protocol = (Path(__file__).resolve().parents[1]
                    / "skill/TREND_REGISTRY_PROTOCOL.md").read_text(encoding="utf-8")
        self.assertIn("模型独立发现 → 观察/候选/确认连续复核 → 合并判断、校验发布", protocol)
        self.assertIn("Python只负责客观行情计算和必要技术校验", protocol)
        self.assertIn("不作为第二个趋势发现者", protocol)
        self.assertIn("不排除模型已发现的方向", protocol)
        self.assertIn("crosscheck_shortlist", protocol)
        self.assertIn("不足时披露缺口", protocol)

    def test_canonical_skills_do_not_resurrect_pre_confirmed_stock_routing(self):
        root = Path(__file__).resolve().parents[1] / "skill"
        protocol = (root / "TREND_REGISTRY_PROTOCOL.md").read_text(encoding="utf-8")
        buy = (root / "TREND_BUY_CANONICAL.md").read_text(encoding="utf-8")
        routing = (root / "TREND_HANDOFF_ROUTING_OVERRIDE.md").read_text(encoding="utf-8")
        prescreen = (root / "PRE_SCREEN_RESEARCH_SCOPE_OVERRIDE.md").read_text(encoding="utf-8")
        intraday = (root / "INTRADAY_MONITOR_CANONICAL.md").read_text(encoding="utf-8")
        # Research reviews the surge promptly but a deadline never forces
        # confirmation. The formal stock route is narrower than the registry.
        self.assertIn("### 2.2 单日爆发后的D1/D2/D3证据复核", protocol)
        self.assertIn("D3必须明确选择", protocol)
        self.assertIn("不再推进D3", protocol)
        self.assertIn("不确认是合格的结论", protocol)
        self.assertIn("候选与观察不得进入股票handoff", protocol)
        self.assertIn("signals=[]", protocol)
        self.assertIn("market_environment_source", protocol)
        # Domain descriptions may name industries as examples; guard the
        # decision rule rather than matching forbidden words in general prose.
        self.assertIn("只有趋势确认且至少存在一个独立确认", protocol)
        self.assertIn("D阶段与市场状态是独立维度", protocol)
        self.assertIn("NO_ELIGIBLE_CONFIRMED_TREND", buy)
        self.assertIn("CORE/DIRECT+趋势确认", routing)
        self.assertIn("不得通过人工alias", routing)
        self.assertIn("绝不能据此跳过上游唯一", prescreen)
        self.assertIn("不得把上一日", intraday)
        # Reject legacy descriptions that silently restore old permissions.
        for obsolete in (
            "仅候选/确认连续复核",
            "接口字段、行业路由、排序与资格均保持不变",
            "不改变T等级、市场状态、优先级、配对/迁移校验或发布硬Gate",
            "2026年10月机器人示例",
        ):
            self.assertNotIn(obsolete, protocol)

    def test_verified_concept_and_future_prevention(self):
        latest, index, structure = inputs()
        c = {"schema_version": 1, "source": "verified provider",
             "as_of_trade_date": "2026-10-08",
             "concepts": [{"concept_id": "foo", "name": "Sample cross theme",
                           "source": "verified provider",
                           "member_codes": [f"{i:06d}" for i in range(1, 7)]}]}
        snap, audit = build(latest, index, structure, c)
        self.assertEqual(snap["status"], "COMPLETE")
        self.assertEqual(audit["concept_count"], 1)
        self.assertEqual(len(snap["model_research_candidates"]), 1)
        self.assertEqual(audit["overlap_deduplicated_count"], 1)
        c["as_of_trade_date"] = "2026-10-10"
        with self.assertRaisesRegex(ValueError, "future"):
            build(latest, index, structure, c)

    def test_stale_membership_is_not_silently_accepted(self):
        latest, index, structure = inputs()
        c = {"schema_version": 1, "source": "verified provider",
             "as_of_trade_date": "2026-09-01", "concepts": []}
        snap, audit = build(latest, index, structure, c)
        self.assertEqual(snap["status"], "INDUSTRY_ONLY_PARTIAL")
        self.assertEqual(audit["concept_coverage_status"], "STALE_MEMBERSHIP")

    def test_bounded_model_research_keeps_deferred_audit(self):
        latest, index, structure = inputs()
        c = {"schema_version": 1, "source": "verified provider",
             "as_of_trade_date": "2026-10-09", "concepts": [
                 {"concept_id": "hot", "name": "Hot concept", "source": "verified provider",
                  "member_codes": [f"{i:06d}" for i in range(1, 7)]}]}
        # Two distinct strong industries plus a fully overlapping concept alias.
        for i in range(13, 25):
            code = f"{i:06d}"
            hot = i < 19
            latest["stocks"][code] = {"change_pct": 4 if hot else -1, "confidence": "high"}
            index["companies"][code] = {
                "mapping_status": "mapped", "industry_code": "S300101" if hot else "S400101",
                "sw_level3_name": "Second hot" if hot else "Second weak"}
            structure["companies"][code] = {
                "data_status": "verified", "data_date": latest["trade_date"],
                "phase_evidence": {"return_3d_pct": 5 if hot else -2,
                                   "return_5d_pct": 2 if hot else -3,
                                   "volume_ratio_1d": 2 if hot else .8}}
        snap, audit = build(latest, index, structure, c, review_cap=1)
        self.assertEqual(audit["eligible_count"], 2)
        self.assertEqual(audit["overlap_deduplicated_count"], 1)
        self.assertEqual(len(snap["model_research_candidates"]), 1)
        self.assertEqual(len(snap["deferred_candidates"]), 1)
        self.assertEqual(sum(r["reason"] == "CAPACITY_DEFERRED" for r in audit["sectors"]), 1)

    def test_full_candidate_queue_is_available_after_seed_theme_merging(self):
        latest, index, structure = inputs()
        for i in range(13, 25):
            code = f"{i:06d}"
            hot = i < 19
            latest["stocks"][code] = {"change_pct": 4 if hot else -1, "confidence": "high"}
            index["companies"][code] = {
                "mapping_status": "mapped",
                "industry_code": "S300101" if hot else "S400101",
                "sw_level3_name": "Second hot" if hot else "Second weak"}
            structure["companies"][code] = {
                "data_status": "verified", "data_date": latest["trade_date"],
                "phase_evidence": {"return_3d_pct": 5 if hot else -2,
                                   "return_5d_pct": 2 if hot else -3,
                                   "volume_ratio_1d": 2 if hot else .8}}
        snap, audit = build(latest, index, structure, review_cap=1)
        queue = snap["candidate_overview"]
        self.assertEqual(len(queue), audit["eligible_count"])
        self.assertEqual({row["industry_code"] for row in queue},
                         {"S100101", "S300101"})
        self.assertEqual(len(snap["model_research_candidates"]), 1)
        self.assertEqual(len(snap["deferred_candidates"]), 1)
        self.assertEqual(snap["theme_research_budget"]["max_new_theme_deep_research"], 1)
        self.assertTrue(snap["theme_research_budget"]["refill_from_candidate_overview_after_merging"])
        self.assertEqual(snap["all_industry_metrics"],
                         "data/research/sector_discovery_audit.json#sectors")

    def test_classification_peers_are_only_research_hints(self):
        latest, index, structure = inputs()
        for i in range(13, 18):
            code = f"{i:06d}"
            latest["stocks"][code] = {"change_pct": -0.6, "confidence": "high"}
            index["companies"][code] = {"mapping_status": "mapped",
                "industry_code": "S100102", "sw_level3_name": "Related classification weak"}
            structure["companies"][code] = {
                "data_status": "verified", "data_date": latest["trade_date"],
                "phase_evidence": {"return_3d_pct": -1, "return_5d_pct": -2,
                                   "volume_ratio_1d": .7}}
        snap, audit = build(latest, index, structure)
        seed = next(x for x in snap["classification_peer_hints"]
                    if x["anchor_industry_code"] == "S100101")
        self.assertTrue(seed["classification_only"])
        self.assertIn("S100102", [x["code"] for x in seed["nearby_industries"]])
        self.assertNotIn("S100102", [x["industry_code"]
                                    for x in snap["candidate_overview"]])
        self.assertEqual(next(x for x in audit["sectors"]
                              if x["id"] == "industry:S100102")["channels"], [])

    def test_snapshot_must_match_completed_trade_date(self):
        latest, index, structure = inputs()
        structure["reference_trade_date"] = "2026-10-08"
        with self.assertRaisesRegex(ValueError, "date_mismatch"):
            build(latest, index, structure)
        structure["reference_trade_date"] = "2026-10-09"
        latest["market_status"] = "trading"
        with self.assertRaisesRegex(ValueError, "completed_market_session"):
            build(latest, index, structure)

    def test_three_or_four_stock_industries_can_trigger_auxiliary_signals(self):
        for remaining in (3, 4):
            latest, index, structure = inputs()
            for code in ("000004", "000005", "000006")[:6 - remaining]:
                del index["companies"][code]
            snap, audit = build(latest, index, structure)
            hot = next(r for r in audit["sectors"] if r["name"] == "Sample hot")
            self.assertEqual(hot["member_count"], remaining)
            self.assertEqual(hot["sample_quality"], "SMALL_SAMPLE")
            self.assertIn("STRONG", hot["channels"])
            self.assertIn(hot["id"], [r["id"] for r in snap["model_research_candidates"]])
            self.assertFalse(snap["discovery_role"]["may_determine_trend_state"])

    def test_small_sample_still_requires_quote_coverage(self):
        latest, index, structure = inputs()
        for code in ("000005", "000006"):
            del index["companies"][code]
        del latest["stocks"]["000004"]
        _, audit = build(latest, index, structure)
        hot = next(r for r in audit["sectors"] if r["name"] == "Sample hot")
        self.assertEqual(hot["sample_quality"], "INSUFFICIENT")
        self.assertEqual(hot["channels"], [])

    def test_low_sample_does_not_create_false_confirmed_sector(self):
        latest, index, structure = inputs()
        for key in list(index["companies"]):
            if int(key) < 6:
                del index["companies"][key]
        snap, audit = build(latest, index, structure)
        hot = next(r for r in audit["sectors"] if r["name"] == "Sample hot")
        self.assertEqual(hot["sample_quality"], "LOW_SAMPLE")
        self.assertEqual(hot["channels"], [])
        self.assertEqual(hot["reason"], "LOW_SAMPLE_OBSERVE")

    def test_coverage_watch_is_not_a_trend_or_capacity_gate(self):
        latest, index, structure = inputs()
        for i in range(1, 7):
            latest["stocks"][f"{i:06d}"]["change_pct"] = -.2
        for i in range(7, 13):
            latest["stocks"][f"{i:06d}"]["change_pct"] = -4
        snap, audit = build(latest, index, structure, review_cap=1)
        coverage = snap["discovery_coverage_audit"]
        hints = coverage["sw3_watch_hints"]
        self.assertEqual(len(snap["model_research_candidates"]), 0)
        self.assertEqual(audit["eligible_count"], 0)
        self.assertEqual(len(hints), 1)
        self.assertIn("RELATIVE_BREADTH_DIVERGENCE", hints[0]["flags"])
        self.assertIn("PERSISTENT_STRUCTURE", hints[0]["flags"])
        self.assertFalse(hints[0]["selected_in_top3"])
        self.assertFalse(hints[0]["market_state_authority"])
        self.assertEqual(coverage, audit["discovery_coverage_audit"])
        self.assertEqual(coverage["sw2_feed_status"], "UNAVAILABLE_NO_VERIFIED_SOURCE")
        self.assertEqual(coverage["price_feed_status"], "UNAVAILABLE_NO_VERIFIED_SOURCE")

    def test_external_coverage_quotes_have_strict_cutoff(self):
        latest, index, structure = inputs()
        sw2 = {"schema_version": 1, "source": "test feed",
               "as_of_trade_date": "2026-10-09", "indices": [
                   {"sw_level2_code": "100100", "return_1d_pct": 4,
                    "quote_at": "2026-10-09T15:00:00+08:00", "source": "test index source"}]}
        anchors = {"schema_version": 1, "source": "test feed",
                   "as_of_trade_date": "2026-10-09", "anchors": [
                       {"anchor_id": "test", "instrument": "test contract", "market": "test market",
                        "price_basis": "close", "quote_at": "2026-10-09T15:00:00+08:00",
                        "price": 100, "unit": "test unit", "change_5d_pct": 3,
                        "research_sw3_codes": ["S200101"], "source": "test source"}]}
        snap, _ = build(latest, index, structure, None, 3, sw2, anchors)
        result = snap["discovery_coverage_audit"]
        self.assertEqual(result["counts"]["official_indices"], 1)
        self.assertEqual(result["counts"]["price_anchors"], 1)
        self.assertTrue(result["price_anchor_hints"][0]["price_vs_equity_divergence"])
        self.assertFalse(result["price_anchor_hints"][0]["beneficiary_verified"])
        sw2["indices"][0]["quote_at"] = "2026-10-09T19:00:00+08:00"
        with self.assertRaisesRegex(ValueError, "indices_invalid"):
            build(latest, index, structure, None, 3, sw2, anchors)
        sw2["indices"][0]["quote_at"] = "2026-10-09T15:00:00+08:00"
        anchors["as_of_trade_date"] = "2026-10-10"
        with self.assertRaisesRegex(ValueError, "future_data"):
            build(latest, index, structure, None, 3, sw2, anchors)


if __name__ == "__main__":
    unittest.main()
