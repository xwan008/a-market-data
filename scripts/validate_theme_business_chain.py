#!/usr/bin/env python3
"""Evidence gate BEFORE theme Top20: real direct value-chain business, not tags.

Only independently verified issuer disclosures documenting real attributable
product/segment REVENUE or signed commercial ORDERS qualify. Membership, R&D,
MOU, marketing stories, usage of robots or a broad unrelated company turnover
are NOT proof. Mechanical validations cannot replace reviewing cited documents.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

CODE = re.compile(r"^\d{6}$")
DIRECT_ROLES = {
    "DIRECT_COMPONENT_SUPPLIER",
    "DIRECT_EQUIPMENT_OR_ROBOT_MAKER",
    "DIRECT_SYSTEM_INTEGRATOR",
    "DIRECT_COMMERCIAL_CONTROL_SOFTWARE",
}
PROOF_TYPES = {"RECOGNIZED_SEGMENT_REVENUE", "SIGNED_EXECUTABLE_CUSTOMER_ORDER"}
VERIFICATION = "ISSUER_DISCLOSURE_CHECKED_INDEPENDENTLY"


def _parse_day(raw):
    try:
        return date.fromisoformat(str(raw))
    except (TypeError, ValueError) as exc:
        raise ValueError("THEME_BUSINESS_PROOF_DATE_INVALID") from exc


def _details(value, tag, min_length=8):
    if not isinstance(value, str) or len(value.strip()) < min_length:
        raise ValueError("THEME_BUSINESS_PROOF_" + tag + "_MISSING")
    return value.strip()


def _doc_url(url):
    if not isinstance(url, str):
        raise ValueError("THEME_BUSINESS_PROOF_DISCLOSURE_URL_INVALID")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("THEME_BUSINESS_PROOF_DISCLOSURE_URL_INVALID")
    # Merely linking a stock exchange/company homepage cannot substantiate
    # attributed robot product revenue. Require exact issuer document locator.
    if (not parsed.path or parsed.path in ("/", "/index.html") or
            "/list/info/company/" in parsed.path or
            "/market/product/stock/list/" in parsed.path):
        raise ValueError("THEME_BUSINESS_PROOF_GENERIC_COMPANY_PAGE")
    return url


def validate_business_chain_snapshot(snapshot, day, required_concept_codes):
    """Return {concept_code: {stock_code: validated_record}}.

    Snapshot intentionally lists ONLY approved positive cases. Missing stocks
    are unverified, never assumed eligible. A malformed positive record blocks
    the run instead of being silently ranked. No auto-substitute or top20 fill.
    """
    if (not isinstance(snapshot, dict) or snapshot.get("schema_version") != 1 or
            snapshot.get("result_kind") != "verified_theme_commercial_chain_evidence" or
            snapshot.get("as_of_trade_date") != day or
            snapshot.get("scope") != "SH_SZ_MAINBOARD_ONLY"):
        raise ValueError("THEME_BUSINESS_PROOF_SNAPSHOT_DATE_SCOPE_INVALID")
    reviewer = _details(snapshot.get("reviewer"), "REVIEWER")
    if reviewer.upper() in {"AUTO_CONCEPT_TAG", "DATA_VENDOR", "NONE"}:
        raise ValueError("THEME_BUSINESS_PROOF_NOT_INDEPENDENT_REVIEW")
    try:
        verified_at = datetime.fromisoformat(snapshot["verified_at"])
        if verified_at.tzinfo is None or verified_at.date() != _parse_day(day):
            raise ValueError("REVIEW_TIMESTAMP")
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("THEME_BUSINESS_PROOF_REVIEW_TIMESTAMP_INVALID") from exc
    themes = snapshot.get("themes")
    if not isinstance(themes, list):
        raise ValueError("THEME_BUSINESS_PROOF_THEME_ARRAY_REQUIRED")
    result = {}
    for group in themes:
        concept_code = str(group.get("concept_code") or "")
        if (not CODE.fullmatch(concept_code) or concept_code in result or
                not isinstance(group.get("companies"), list)):
            raise ValueError("THEME_BUSINESS_PROOF_THEME_CODE_INVALID")
        business_driver = _details(group.get("business_driver"), "THEME_BUSINESS_DRIVER", 15)
        approved = {}
        for item in group["companies"]:
            code = str(item.get("stock_code") or "")
            if not CODE.fullmatch(code) or code in approved:
                raise ValueError("THEME_BUSINESS_PROOF_STOCK_CODE_INVALID")
            if item.get("review_status") != "VERIFIED_DIRECT_COMMERCIAL_CHAIN":
                raise ValueError("THEME_BUSINESS_PROOF_DIRECT_REVIEW_NOT_VERIFIED")
            if item.get("review_method") != VERIFICATION:
                raise ValueError("THEME_BUSINESS_PROOF_DOCUMENT_REVIEW_NOT_DONE")
            if item.get("commercial_relationship") not in DIRECT_ROLES:
                raise ValueError("THEME_BUSINESS_PROOF_NO_DIRECT_SUPPLIER_ROLE")
            node = _details(item.get("specific_chain_node"), "SPECIFIC_CHAIN_NODE")
            link = _details(item.get("driver_revenue_link"), "REVENUE_DRIVER_LINK", 30)
            if link.strip() == business_driver:
                raise ValueError("THEME_BUSINESS_PROOF_DRIVER_LINK_NOT_COMPANY_SPECIFIC")
            significance = _details(item.get("materiality_assessment"), "MATERIALITY", 25)
            proof = item.get("commercial_proof") or {}
            if proof.get("type") not in PROOF_TYPES:
                raise ValueError("THEME_BUSINESS_PROOF_NO_REVENUE_OR_SIGNED_ORDER")
            amount = proof.get("amount_cny")
            if (isinstance(amount, bool) or not isinstance(amount, (int, float)) or
                    not math.isfinite(amount) or amount <= 0):
                raise ValueError("THEME_BUSINESS_PROOF_AMOUNT_NOT_QUANTIFIED")
            accounting_end = _parse_day(proof.get("period_end"))
            cutoff = _parse_day(day)
            if accounting_end > cutoff or accounting_end < cutoff-timedelta(days=540):
                raise ValueError("THEME_BUSINESS_PROOF_REVENUE_OR_ORDER_PERIOD_INVALID")
            published = _parse_day(proof.get("published_at"))
            if published > cutoff or published < accounting_end:
                raise ValueError("THEME_BUSINESS_PROOF_DISCLOSURE_FUTURE_OR_INCONSISTENT")
            title = _details(proof.get("issuer_document_title"), "DOCUMENT_TITLE", 12)
            location = _details(proof.get("page_or_section"), "DOCUMENT_LOCATION", 3)
            excerpt = _details(proof.get("specific_disclosure_excerpt"), "DOCUMENT_EXCERPT", 30)
            economic_line = _details(proof.get("attributable_product_or_order"), "REVENUE_LINE", 8)
            url = _doc_url(proof.get("issuer_document_url"))
            if "公司全部收入" in economic_line or "企业整体营收" in economic_line:
                raise ValueError("THEME_BUSINESS_PROOF_UNATTRIBUTED_WHOLE_COMPANY_SALES")
            approved[code] = item
        result[concept_code] = approved
    missing = set(required_concept_codes) - set(result)
    if missing:
        raise ValueError("THEME_BUSINESS_PROOF_MISSING_CONCEPT:" + ",".join(sorted(missing)))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--concept-code", action="append", required=True)
    args = parser.parse_args()
    snapshot = json.loads(Path(args.file).read_text(encoding="utf-8"))
    groups = validate_business_chain_snapshot(
        snapshot, args.trade_date, args.concept_code)
    print(json.dumps({
        "status": "VERIFIED_EVIDENCE_CONTRACT_ONLY",
        "concepts": {code: len(stocks) for code, stocks in groups.items()},
        "document_contents_must_be_reviewed": True,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
