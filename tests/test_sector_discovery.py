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
    def test_industry_only_does_not_claim_concept_coverage(self):
        snap, audit = build(*inputs())
        self.assertEqual(snap["status"], "INDUSTRY_ONLY_PARTIAL")
        self.assertEqual(audit["industry_count"], 2)
        self.assertEqual(audit["concept_coverage_status"], "UNAVAILABLE_NO_MEMBERSHIP")
        self.assertEqual(len(snap["model_research_candidates"]), 1)
        self.assertEqual(snap["model_research_candidates"][0]["name"], "Sample hot")
        self.assertEqual(snap["model_research_candidates"][0]["channels"], ["STRONG", "EMERGING"])
        self.assertTrue(snap["no_trade_signal"])

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


if __name__ == "__main__":
    unittest.main()
