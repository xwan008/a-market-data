"""Buy-point builder accepts exactly dated concept snapshots without SW theme inflation."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_trend_buy_manual_research as buy

DAY = "2026-10-26"


def company(code, sector, name):
    return {"code": code, "name": name, "industry_code": sector,
            "industry_name": "真实所属行业" + sector,
            "price": 10.0, "ma20": 9.8, "ma60": 9.3, "pb": 1.4,
            "revenue_yoy": 10.0, "net_profit_yoy": 10.0,
            "basic_eps": .4, "deduct_basic_eps": .38,
            "operating_cashflow_per_share": .4}


def stock_technical():
    return {"current_price": 10.0, "mock_score": .75}


class ThemeBuyRoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.handoff = {"schema_version": 1, "result_kind": "a_share_trend_handoff",
                        "trade_date": DAY, "signals": [
                            {"rank": 1, "trend_name": "工业自动化/机器人",
                             "trend_state": "T1", "market_state": "候选趋势",
                             "industry_codes": ["S640701"], "mapping_status": "resolved"}]}
        self.companies = {"000001": company("000001", "S640701", "原行业股票"),
                          "000003": company("000003", "S650101", "跨行业甲"),
                          "000004": company("000004", "S650101", "跨行业乙")}
        idx = {"trade_date": DAY, "validation": {"status": "passed"}, "industries": {}}
        for sector in ("S640701", "S650101"):
            rows = [x for x in self.companies.values() if x["industry_code"] == sector]
            partpath = "data/low_risk/by_industry/" + sector + "/part0.json"
            manifestpath = "data/low_risk/by_industry/" + sector + "/manifest.json"
            part = {"trade_date": DAY, "industry_code": sector, "companies": rows}
            payload = json.dumps(part, ensure_ascii=False).encode("utf-8")
            self.put_bytes(partpath, payload)
            self.put(manifestpath, {
                "trade_date": DAY, "industry_code": sector, "company_count": len(rows),
                "universe_company_codes": [r["code"] for r in rows],
                "parts": [{"file": partpath, "byte_size": len(payload),
                           "company_count": len(rows),
                           "company_codes": [r["code"] for r in rows]}]})
            idx["industries"][sector] = {"layout": "chunked_manifest_v1",
                                          "company_count": len(rows),
                                          "manifest_file": manifestpath}
        self.put("data/low_risk/index.json", idx)
        self.put("research/trend_handoff.json", self.handoff)
        self.put("evidence.json", {
            "as_of_date": DAY,
            "reviews": [{"code": code, "transmission": "SUPPORTED",
                         "source_materials": [{"url": "https://example.org/a", "asof": DAY}],
                         "source_review": "已验证来源", "review_basis": "TEST",
                         "review_evidence_date": DAY, "research_falsifier": "假设被证伪"}
                        for code in self.companies]})
        self.put("structure.json", {
            "contract_id": "a-share-low-risk-price-structure",
            "reference_trade_date": DAY,
            "companies": {code: stock_technical() for code in self.companies}})
        self.route = {"schema_version": 1, "result_kind": "hotspot_stock_route_snapshot",
                      "status": "COMPLETE", "trade_date": DAY,
                      "concept_as_of_trade_date": DAY,
                      "routes": [{"rank": 1, "trend_name": "工业自动化/机器人",
                                  "trend_state": "T1", "market_state": "候选趋势",
                                  "original_industry_codes": ["S640701"],
                                  "hotspot_type": "THEME", "mapping_source": "EASTMONEY_AKSHARE",
                                  "mapping_code": "BKTEST", "concept_member_codes":
                                  ["000001", "000003", "000004"],
                                  "candidate_stocks": [
                                      {"rank": 1, "stock_code": "000003",
                                       "industry_code": "S650101"},
                                      {"rank": 2, "stock_code": "000004",
                                       "industry_code": "S650101"}]}]}
        self.put("route.json", self.route)

    def put_bytes(self, name, payload):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    def put(self, name, value):
        self.put_bytes(name, json.dumps(value, ensure_ascii=False).encode("utf-8"))

    @staticmethod
    def mock_opportunity(stock, day):
        assert day == DAY
        return {"opportunity_score": stock["mock_score"]}, None

    def run_builder(self, use_concept=True):
        with patch.object(buy, "ROOT", self.root), \
             patch.object(buy, "TREND", self.root / "research/trend_handoff.json"), \
             patch.object(buy, "INDEX", self.root / "data/low_risk/index.json"), \
             patch.object(buy, "compact_opportunity", side_effect=self.mock_opportunity):
            return buy.build(self.root / "evidence.json",
                             str(self.root / "structure.json"), None,
                             str(self.root / "route.json") if use_concept else None)

    def test_theme_uses_only_concept_candidates_not_original_sw_members(self):
        result = self.run_builder()
        self.assertEqual(result["mode"], "FORMAL")
        self.assertEqual(result["screen_audit"]["theme_group_count"], 1)
        self.assertEqual(result["screen_audit"]["hard_eligible"], 2)
        self.assertEqual({x["code"] for x in result["companies"]},
                         {"000003", "000004"})
        self.assertEqual({x["trend_name"] for x in result["companies"]},
                         {"工业自动化/机器人"})
        self.assertEqual({x["industry_code"] for x in result["companies"]},
                         {"S650101"})

    def test_original_industry_route_works_when_extension_disabled(self):
        result = self.run_builder(use_concept=False)
        self.assertEqual(result["screen_audit"]["theme_group_count"], 0)
        self.assertEqual([x["code"] for x in result["companies"]], ["000001"])
        self.assertEqual(result["screen_audit"]["research_scope"],
                         "dynamic_tertiary_industry_top5_after_lightweight_scan")

    def test_data_insufficient_blocks_formal_buy_pipeline(self):
        self.route["routes"][0]["hotspot_type"] = "DATA_INSUFFICIENT"
        self.route["routes"][0]["candidate_stocks"] = []
        self.put("route.json", self.route)
        with self.assertRaisesRegex(ValueError, "THEME_ROUTE_COVERAGE_INSUFFICIENT"):
            self.run_builder()

    def test_changed_trend_state_blocks_stale_concept_snapshot(self):
        self.route["routes"][0]["trend_state"] = "T2"
        self.put("route.json", self.route)
        with self.assertRaisesRegex(ValueError, "CHANGED_UPSTREAM_SIGNAL"):
            self.run_builder()

    def test_stock_not_actually_in_concept_blocks(self):
        self.route["routes"][0]["candidate_stocks"][0]["stock_code"] = "000999"
        self.put("route.json", self.route)
        with self.assertRaisesRegex(ValueError, "MEMBERSHIP_INVALID"):
            self.run_builder()


if __name__ == "__main__":
    unittest.main()
