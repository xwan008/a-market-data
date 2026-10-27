"""Pure synthetic fixture tests: structural checks are NOT factual issuer verification."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from validate_theme_business_chain import validate_business_chain_snapshot as validate
from test_hotspot_theme_router import commercial_fixture

DAY="2026-10-26"


class CommercialQualificationGateTest(unittest.TestCase):
    def tested(self):
        return commercial_fixture(codes=["600001"])

    def first(self, data):
        return data["themes"][0]["companies"][0]

    def test_issuer_proven_segment_revenue_schema(self):
        result=validate(self.tested(), DAY, ["886069"])
        self.assertEqual(list(result["886069"]),["600001"])

    def test_vendor_label_only_cannot_enter_top20(self):
        data=self.tested()
        data["themes"][0]["companies"]=[]
        self.assertEqual(validate(data,DAY,["886069"])["886069"],{})

    def test_mou_without_actual_revenue_or_signed_order_rejected(self):
        data=self.tested()
        self.first(data)["commercial_proof"]["type"]="STRATEGIC_MOU"
        with self.assertRaisesRegex(ValueError,"NO_REVENUE_OR_SIGNED_ORDER"):
            validate(data,DAY,["886069"])

    def test_using_robots_not_supplying_value_chain_rejected(self):
        data=self.tested()
        self.first(data)["commercial_relationship"]="APPLICATION_END_USER"
        with self.assertRaisesRegex(ValueError,"NO_DIRECT_SUPPLIER_ROLE"):
            validate(data,DAY,["886069"])

    def test_generic_exchange_company_page_does_not_prove_revenue(self):
        data=self.tested()
        self.first(data)["commercial_proof"]["issuer_document_url"]=(
            "https://www.sse.com.cn/assortment/stock/list/info/company/index.shtml?COMPANY_CODE=600001")
        with self.assertRaisesRegex(ValueError,"GENERIC_COMPANY_PAGE"):
            validate(data,DAY,["886069"])

    def test_missing_quantification_blocks_revenue_claim(self):
        data=self.tested()
        self.first(data)["commercial_proof"]["amount_cny"]=None
        with self.assertRaisesRegex(ValueError,"AMOUNT_NOT_QUANTIFIED"):
            validate(data,DAY,["886069"])

    def test_future_disclosure_or_prior_550_day_stale_period(self):
        data=self.tested()
        self.first(data)["commercial_proof"]["published_at"]="2026-10-27"
        with self.assertRaisesRegex(ValueError,"DISCLOSURE_FUTURE"):
            validate(data,DAY,["886069"])
        data=self.tested()
        self.first(data)["commercial_proof"]["period_end"]="2024-01-01"
        with self.assertRaisesRegex(ValueError,"PERIOD_INVALID"):
            validate(data,DAY,["886069"])

    def test_commercial_proof_cannot_be_lifted_from_other_concept(self):
        data=self.tested()
        with self.assertRaisesRegex(ValueError,"MISSING_CONCEPT"):
            validate(data,DAY,["885517"])

    def test_new_concept_requires_new_specific_segment_evidence(self):
        data=self.tested()
        data["themes"][0]["concept_code"]="885517"
        self.assertNotIn("886069",validate(data,DAY,["885517"]))
        # The gate only enforces structure and explicit per-theme records.
        # Independent reviewers must still verify the document really
        # substantiates attributed business and market-driver materiality.


if __name__=="__main__":
    unittest.main()
