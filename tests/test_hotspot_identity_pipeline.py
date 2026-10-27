"""Frozen hotspot identity, independent evidence and post-state mainboard routing."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import resolve_hotspot_identities as resolver
import build_mapped_hotspot_market_evidence as metrics
import route_hotspot_themes as router

DAY = "2026-10-26"


def registry():
    return {"schema_version": 1,"result_kind":"verified_hotspot_identity_registry",
            "entries":[{"canonical_name":"人形机器人","board_type":"THEME",
                        "board_code":"886069","source":"THS_ADATA",
                        "aliases":[]}]}


def concept():
    return {"schema_version":1,"source":"THS_ADATA",
            "as_of_trade_date":DAY,
            "source_observed_at":DAY+"T18:30:15+08:00",
            "concepts":[{"concept_id":"886069","source":"THS_ADATA","name":"人形机器人",
                         "member_codes":["600001","600002","600003",
                                         "600004","600005","000001","300001"]}]}


def item(name="人形机器人", board_type="THEME", code="886069",
         driver_kind="TECHNOLOGY_CATALYST"):
    return {
        "hotspot_id":"robot-test",
        "hotspot_name":name,
        "industry_seed_codes":["S640701","S640702"],
        "representative_codes":["600001","000001"],
        "origin":{"board_type":board_type,"board_code":code,
                  "source":"THS_ADATA" if board_type=="THEME" else
                           "SW2021_L3" if board_type=="INDUSTRY" else ""},
        "driver":{"kind":driver_kind,"target_board_code":code,
                  "summary":"mock unit test driving evidence",
                  "sources":[{"source":"https://example.org/mock-unit-test-only",
                              "published_at":DAY,
                              "claim":"Synthetic evidence for unit tests, not real market research"}]}
    }


def discovery(obj):
    return {"schema_version":1,"result_kind":"independent_hotspot_discovery_frozen",
            "trade_date":DAY,"frozen_at":DAY+"T18:30:00+08:00",
            "discovery_stage":"FROZEN_BEFORE_HISTORICAL_REVIEW","hotspots":[obj]}


def market():
    codes=["600001","600002","600003","600004","600005","000001"]
    industry = {"companies": {
        code: {"mapping_status":"mapped",
               "industry_code":"S640701" if code in codes[:3] else "S640702"}
        for code in codes}}
    quotes={"trade_date":DAY,"market_status":"closed",
            "stocks":{code:{"confidence":"high","change_pct":1.5,
                            "name":"测试"+code} for code in codes}}
    structure={"reference_trade_date":DAY,
               "companies":{code:{"mock_score":.85,
                                   "data_status":"verified",
                                   "data_date":DAY,
                                   "phase_evidence":{"return_3d_pct":2.5,
                                                     "return_5d_pct":3.5}}
                            for code in codes}}
    return industry,quotes,structure


class IdentityAndRouterTest(unittest.TestCase):
    def test_explicit_concept_identity_requires_driver_and_same_day_members(self):
        resolved=resolver.resolve(discovery(item()),registry(),concept())
        self.assertEqual(resolved["status"],"COMPLETE")
        ident=resolved["identities"][0]
        self.assertEqual((ident["board_type"],ident["board_code"]),("THEME","886069"))
        self.assertEqual(ident["concept_mainboard_member_count"],6)
        self.assertNotIn("market_state",ident)

    def test_real_name_collision_must_not_force_humanoid_theme(self):
        ambiguous=item(name="工业自动化/机器人",board_type="UNSPECIFIED",code="",
                       driver_kind="INDUSTRY_ECONOMICS")
        resolved=resolver.resolve(discovery(ambiguous),registry(),concept())
        self.assertEqual(resolved["status"],"NEEDS_IDENTITY_REVIEW")
        self.assertEqual(resolved["identities"][0]["mapping_status"],
                         "MAPPING_UNRESOLVED")
        self.assertIsNone(resolved["identities"][0]["board_type"])

    def test_industry_source_passes_codes_without_members(self):
        obj=item(name="工业自动化",board_type="INDUSTRY",
                 code="S640701",driver_kind="INDUSTRY_ECONOMICS")
        result=resolver.resolve(discovery(obj),registry(),industry_index=market()[0],
                                resolved_at=DAY+"T18:31:00+08:00")
        self.assertEqual(result["identities"][0]["mapping_status"],"VERIFIED")
        self.assertEqual(result["identities"][0]["industry_codes"],
                         ["S640701","S640702"])
        industry,latest,structure=market()
        evidence=metrics.summarize(result,industry,latest,structure)
        self.assertEqual(evidence["hotspots"][0]["member_count"],6)
        self.assertEqual(evidence["hotspots"][0]["evaluation_status"],
                         "READY_FOR_INDEPENDENT_STATE_REVIEW")
        handoff={"result_kind":"a_share_trend_handoff",
                 "generated_at":DAY+"T18:34:00+08:00",
                 "trade_date":DAY,
                 "source":{"identity_verified_before_state":True},
                 "signals":[{"rank":1,"trend_name":"工业自动化",
                             "board_type":"INDUSTRY","board_code":"S640701",
                             "industry_codes":["S640701","S640702"],
                             "trend_state":"T1","market_state":"候选趋势"}]}
        routes=router.build_verified_routes(handoff,industry,latest,structure,result)
        self.assertEqual(routes["routes"][0]["hotspot_type"],"INDUSTRY")
        self.assertEqual(routes["routes"][0]["industry_codes"],["S640701","S640702"])
        self.assertEqual(routes["routes"][0]["candidate_stocks"],[])
        self.assertNotIn("concept_member_codes",routes["routes"][0])

    def test_concept_market_evidence_and_top20_are_separate_from_state(self):
        ident=resolver.resolve(discovery(item()),registry(),concept(),
                               resolved_at=DAY+"T18:31:00+08:00")
        industry,latest,structure=market()
        report=metrics.summarize(ident,industry,latest,structure,concept())
        self.assertEqual(report["hotspots"][0]["r3_breadth"],1)
        self.assertIsNone(report["hotspots"][0]["market_state"])
        handoff={"result_kind":"a_share_trend_handoff",
                 "generated_at":DAY+"T18:34:00+08:00","trade_date":DAY,
                 "source":{"identity_verified_before_state":True},
                 "signals":[{"rank":1,"trend_name":"人形机器人",
                             "board_type":"THEME","board_code":"886069",
                             "industry_codes":["S640701","S640702"],
                             "trend_state":"T1","market_state":"候选趋势"}]}
        with patch("build_trend_buy_manual_research.compact_opportunity",
                   side_effect=lambda row, d: ({"opportunity_score":row["mock_score"]},None)):
            routed=router.build_verified_routes(handoff,industry,latest,structure,
                                                ident,concept(),cap=3)
        route=routed["routes"][0]
        self.assertEqual(route["hotspot_type"],"THEME")
        self.assertEqual(route["concept_member_count"],7)
        self.assertEqual(route["concept_mainboard_member_count"],6)
        self.assertEqual(len(route["candidate_stocks"]),3)
        self.assertTrue(all(router.is_main_board(x["stock_code"])
                            for x in route["candidate_stocks"]))
        self.assertEqual(route["market_state"],"候选趋势")

    def test_unverified_state_cannot_be_used_downstream(self):
        identity=resolver.resolve(discovery(item()),registry(),concept(),
                                   resolved_at=DAY+"T18:31:00+08:00")
        industry,latest,structure=market()
        handoff={"result_kind":"a_share_trend_handoff",
                 "generated_at":DAY+"T18:34:00+08:00","trade_date":DAY,
                 "source":{},
                 "signals":[{"rank":1,"trend_name":"人形机器人",
                             "board_type":"THEME","board_code":"886069",
                             "industry_codes":[],"trend_state":"T1",
                             "market_state":"候选趋势"}]}
        with self.assertRaisesRegex(ValueError,"NOT_ADJUDICATED_AFTER_IDENTITY"):
            router.build_verified_routes(handoff,industry,latest,structure,
                                         identity,concept())

    def test_bad_identity_driver_and_stale_concept_are_not_accepted(self):
        bad=item(driver_kind="INDUSTRY_ECONOMICS")
        self.assertEqual(resolver.resolve(discovery(bad),registry(),concept())
                         ["identities"][0]["mapping_status"],"MAPPING_UNRESOLVED")
        future=concept();future["as_of_trade_date"]="2026-10-27"
        self.assertEqual(resolver.resolve(discovery(item()),registry(),future)
                         ["identities"][0]["mapping_status"],"DATA_INSUFFICIENT")

    def test_missing_concept_capture_time_blocks_verified_mapping(self):
        snapshot=concept()
        snapshot.pop("source_observed_at")
        result=resolver.resolve(discovery(item()),registry(),snapshot)
        self.assertEqual(result["identities"][0]["mapping_status"],
                         "DATA_INSUFFICIENT")

    def test_concept_capture_after_identity_resolution_is_rejected(self):
        snapshot=concept()
        snapshot["source_observed_at"]=DAY+"T18:32:00+08:00"
        result=resolver.resolve(discovery(item()),registry(),snapshot,
                                resolved_at=DAY+"T18:31:00+08:00")
        self.assertEqual(result["identities"][0]["mapping_status"],
                         "DATA_INSUFFICIENT")

    def test_unverifiable_driver_source_and_future_publication_rejected(self):
        no_source=item();no_source["driver"]["sources"]=[]
        self.assertEqual(resolver.resolve(discovery(no_source),registry(),concept())
                         ["identities"][0]["mapping_status"],"MAPPING_UNRESOLVED")
        future=item();future["driver"]["sources"][0]["published_at"]="2026-10-27"
        self.assertEqual(resolver.resolve(discovery(future),registry(),concept())
                         ["identities"][0]["mapping_status"],"MAPPING_UNRESOLVED")


if __name__=="__main__":
    unittest.main()
