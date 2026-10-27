"""Post-state identity-first routing never reclassifies industries using returns."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import route_hotspot_themes as router

DAY="2026-10-26"
MAIN=["600001","600002","600003","600004","600005","000001"]


def fixture(kind="THEME"):
    identity={
        "result_kind":"hotspot_identity_snapshot",
        "trade_date":DAY, "status":"COMPLETE",
        "market_scope":"SH_SZ_MAINBOARD_ONLY",
        "resolved_at":DAY+"T18:31:00+08:00",
        "identities":[{"hotspot_name":"人形机器人",
                       "mapping_status":"VERIFIED",
                       "board_type":kind,
                       "board_code":"886069" if kind=="THEME" else "S640701",
                       "concept_code":"886069" if kind=="THEME" else None,
                       "origin_source":"THS_ADATA" if kind=="THEME" else "SW2021_L3",
                       "industry_codes":[] if kind=="THEME" else ["S640701","S640702"]}]}
    signal={"rank":1,"trend_name":"人形机器人",
            "board_type":kind,"board_code":identity["identities"][0]["board_code"],
            "industry_codes":[] if kind=="THEME" else ["S640701","S640702"],
            "trend_state":"T1","market_state":"候选趋势"}
    handoff={"result_kind":"a_share_trend_handoff","trade_date":DAY,
             "generated_at":DAY+"T18:34:00+08:00",
             "source":{"identity_verified_before_state":True},
             "signals":[signal]}
    latest={"trade_date":DAY,"market_status":"closed",
            "stocks":{code:{"name":"测试"+code,
                            "confidence":"high","change_pct":-5}
                      for code in MAIN}}
    industries={"companies":{
        code:{"mapping_status":"mapped",
              "industry_code":"S640701" if code in MAIN[:3] else "S640702"}
        for code in MAIN}}
    structure={"reference_trade_date":DAY,"companies":{
        code:{"mock_score":.7} for code in MAIN}}
    catalog={"schema_version":1,"source":"THS_ADATA",
             "as_of_trade_date":DAY,
             "source_observed_at":DAY+"T18:30:15+08:00",
             "concepts":[{"concept_id":"886069","name":"人形机器人",
                          "source":"THS_ADATA",
                          "member_codes":MAIN+["300001","688001","830001"]}]}
    return handoff,industries,latest,structure,identity,catalog


def chain_proof_for(code, concept="886069"):
    """Synthetic test fixture only; fake disclosures are never real evidence."""
    return {"stock_code":code,
            "review_status":"VERIFIED_DIRECT_COMMERCIAL_CHAIN",
            "review_method":"ISSUER_DISCLOSURE_CHECKED_INDEPENDENTLY",
            "commercial_relationship":"DIRECT_COMPONENT_SUPPLIER",
            "specific_chain_node":"机器人伺服控制产品",
            "driver_revenue_link":"机器人增量需求带动本公司真实伺服控制产品销售收入增长（仅单元测试）",
            "materiality_assessment":"该伺服控制业务收入属于可测量的真实业务线，仅供单元测试",
            "commercial_proof":{
                "type":"RECOGNIZED_SEGMENT_REVENUE",
                "amount_cny":50000000,
                "period_end":"2026-06-30",
                "published_at":"2026-08-30",
                "issuer_document_url":"https://example.org/unit-test-specific-report/"+code+".pdf",
                "issuer_document_title":"单元测试假想公司伺服业务半年度收入报告",
                "page_or_section":"第12页分部收入附注",
                "specific_disclosure_excerpt":"单元测试伺服产品业务报告期内收入五千万元，本内容完全为虚构测试数据",
                "attributable_product_or_order":"机器人伺服控制产品收入"}}


def commercial_fixture(*, codes=MAIN, include_all=True):
    return {
        "schema_version":1,
        "result_kind":"verified_theme_commercial_chain_evidence",
        "as_of_trade_date":DAY,"scope":"SH_SZ_MAINBOARD_ONLY",
        "verified_at":DAY+"T18:32:00+08:00",
        "reviewer":"SYNTHETIC_UNIT_TEST_ONLY",
        "themes":[{"concept_code":"886069",
                   "business_driver":"机器人需求带动机器人本体和控制零部件的订单兑现",
                   "companies":[chain_proof_for(c) for c in
                                (codes if include_all else codes[:2])]}]}


def mock_opportunity(item, day):
    assert day==DAY
    return ({"opportunity_score":item["mock_score"]},None)


class VerifiedRouteTest(unittest.TestCase):
    def build(self,args,**kwargs):
        if args[4]["identities"][0]["board_type"]=="THEME":
            kwargs.setdefault("business_evidence",commercial_fixture())
        with patch("build_trend_buy_manual_research.compact_opportunity",
                   side_effect=mock_opportunity):
            return router.build_verified_routes(*args,**kwargs)

    def test_theme_identity_survives_market_pullback(self):
        args=fixture()
        row=self.build(args,cap=4)["routes"][0]
        self.assertEqual(row["hotspot_type"],"THEME")
        self.assertEqual(row["concept_member_count"],9)
        self.assertEqual(row["concept_mainboard_member_count"],6)
        self.assertEqual(row["quote_coverage"],1)
        self.assertEqual(len(row["candidate_stocks"]),4)
        self.assertTrue(all(router.is_main_board(x["stock_code"])
                            for x in row["candidate_stocks"]))
        self.assertNotIn("concept_up_ratio",row)
        self.assertNotIn("recognition_basis",row)

    def test_no_business_evidence_disallows_vendor_concept_top20(self):
        with self.assertRaisesRegex(ValueError,"PROOF_REQUIRED_BEFORE_TOP20"):
            router.build_verified_routes(*fixture())

    def test_only_directly_commercial_verified_stocks_count(self):
        route=self.build(fixture(),business_evidence=commercial_fixture(
            include_all=False))["routes"][0]
        self.assertEqual(len(route["candidate_stocks"]),2)
        self.assertEqual(route["business_chain_reviewed_count"],2)
        self.assertEqual({x["stock_code"] for x in route["candidate_stocks"]},
                         set(MAIN[:2]))

    def test_no_padded_top20_when_there_are_no_verified_stocks(self):
        empty=commercial_fixture()
        empty["themes"][0]["companies"]=[]
        with self.assertRaisesRegex(ValueError,"NO_VERIFIED_COMMERCIAL_CHAIN"):
            self.build(fixture(),business_evidence=empty)

    def test_unrelated_business_or_marketing_mou_rejected(self):
        for changed in [
            {"commercial_relationship":"APPLICATION_END_USER"},
            {"commercial_proof":{"type":"MEMORANDUM_OF_UNDERSTANDING"}},
        ]:
            bad=commercial_fixture()
            bad["themes"][0]["companies"][0].update(changed)
            with self.assertRaisesRegex(ValueError,"PROOF_"):
                self.build(fixture(),business_evidence=bad)

    def test_industry_only_passes_codes_never_industry_member_list(self):
        handoff,idx,latest,structure,ident,catalog=fixture("INDUSTRY")
        route=self.build((handoff,idx,latest,structure,ident))["routes"][0]
        self.assertEqual(route["hotspot_type"],"INDUSTRY")
        self.assertEqual(route["industry_codes"],["S640701","S640702"])
        self.assertEqual(route["candidate_stocks"],[])
        self.assertNotIn("concept_member_codes",route)

    def test_missing_mainboard_quotes_are_insufficient(self):
        args=list(fixture())
        for code in MAIN[:2]:
            args[2]["stocks"].pop(code)
        with self.assertRaisesRegex(ValueError,"QUOTE_COVERAGE_INSUFFICIENT"):
            self.build(args)

    def test_missing_identity_confirmed_before_state_is_blocked(self):
        args=list(fixture())
        args[0]["source"]={}
        with self.assertRaisesRegex(ValueError,"NOT_ADJUDICATED_AFTER_IDENTITY"):
            self.build(args)

    def test_identity_resolution_after_trend_state_is_blocked(self):
        args=list(fixture())
        args[4]["resolved_at"]=DAY+"T18:36:00+08:00"
        with self.assertRaisesRegex(ValueError,"AFTER_TREND_STATE"):
            self.build(args)

    def test_membership_captured_after_trend_state_is_blocked(self):
        args=list(fixture())
        args[5]["source_observed_at"]=DAY+"T18:35:00+08:00"
        with self.assertRaisesRegex(ValueError,"AFTER_TREND_STATE"):
            self.build(args)

    def test_concept_code_mismatch_cannot_be_replaced_by_better_performance(self):
        args=list(fixture())
        args[0]["signals"][0]["board_code"]="886068"
        with self.assertRaisesRegex(ValueError,"STATE_OR_IDENTITY_MISMATCH"):
            self.build(args)

    def test_mismatched_identity_date_cannot_publish(self):
        args=list(fixture())
        args[4]["trade_date"]="2026-10-25"
        with self.assertRaisesRegex(ValueError,"DATE_SCOPE_INVALID"):
            self.build(args)

    def test_invalid_member_code_fails_closed(self):
        args=list(fixture())
        args[5]["concepts"][0]["member_codes"].append("INVALID")
        with self.assertRaisesRegex(ValueError,"INVALID_STOCK"):
            self.build(args)

    def test_unresolved_identity_not_claimed_as_industry(self):
        args=list(fixture())
        args[4]["identities"][0]["mapping_status"]="MAPPING_UNRESOLVED"
        with self.assertRaisesRegex(ValueError,"IDENTITIES_NOT_MATCHED"):
            self.build(args)

    def test_unresolved_unpublished_hotspots_do_not_block_valid_industry(self):
        handoff,index,latest,structure,identity,catalog=fixture("INDUSTRY")
        identity["status"]="NEEDS_IDENTITY_REVIEW"
        identity["identities"].append({
            "hotspot_name":"待核验其他概念","board_type":None,
            "mapping_status":"MAPPING_UNRESOLVED"})
        result=self.build((handoff,index,latest,structure,identity))
        self.assertEqual(result["routes"][0]["hotspot_type"],"INDUSTRY")

    def test_extra_identity_observation_does_not_enter_handoff(self):
        args=list(fixture())
        args[4]["identities"].append({"hotspot_name":"其他未入选研究",
                                      "mapping_status":"MAPPING_UNRESOLVED"})
        result=self.build(args)
        self.assertEqual(len(result["routes"]),1)


if __name__=="__main__":
    unittest.main()
