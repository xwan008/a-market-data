from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SHARDS_DIR = DATA_DIR / "shards"
INDEX_PATH = DATA_DIR / "research" / "company_industry_index.json"


def read_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def mapping_fields(item: dict | None) -> dict:
    item = item if isinstance(item, dict) else {}
    level3_code = item.get("sw_level3_code")
    level3_name = item.get("sw_level3_name")
    status = item.get("mapping_status")
    if not status:
        status = "mapped" if level3_code and level3_name else "missing"
    return {
        "sw_level3_code": level3_code,
        "sw_level3_name": level3_name,
        "industry_mapping_status": status,
    }


def enrich_shard_payload(payload: dict, companies: dict, index_meta: dict) -> tuple[dict, dict]:
    stocks = payload.get("stocks")
    if not isinstance(stocks, dict):
        stocks = {}
        payload["stocks"] = stocks

    mapped = unmapped = missing = 0
    for code, stock in stocks.items():
        if not isinstance(stock, dict):
            continue
        company = companies.get(str(code).zfill(6))
        fields = mapping_fields(company)
        stock.update(fields)
        status = fields["industry_mapping_status"]
        if status == "mapped" and fields["sw_level3_code"] and fields["sw_level3_name"]:
            mapped += 1
        elif company is None:
            missing += 1
        else:
            unmapped += 1

    payload["industry_mapping"] = {
        "taxonomy": index_meta.get("taxonomy") or "申万行业分类标准2021版",
        "source": "data/research/company_industry_index.json",
        "index_generated_at": index_meta.get("generated_at"),
        "trade_date_reference": index_meta.get("trade_date_reference"),
        "mapped_count": mapped,
        "unmapped_count": unmapped,
        "missing_count": missing,
    }
    return payload, {
        "stocks": len(stocks),
        "mapped": mapped,
        "unmapped": unmapped,
        "missing": missing,
    }


def main() -> int:
    index = read_json(INDEX_PATH, {})
    companies = index.get("companies")
    if not isinstance(companies, dict) or not companies:
        print(json.dumps({"status": "error", "reason": "company_industry_index_unavailable"}, ensure_ascii=False))
        return 2

    shard_files = sorted(SHARDS_DIR.glob("*.json"))
    if not shard_files:
        print(json.dumps({"status": "error", "reason": "no_quote_shards"}, ensure_ascii=False))
        return 2

    totals = {"shards": 0, "stocks": 0, "mapped": 0, "unmapped": 0, "missing": 0}
    index_meta = {
        "taxonomy": index.get("taxonomy"),
        "generated_at": index.get("generated_at"),
        "trade_date_reference": index.get("trade_date_reference"),
    }

    for path in shard_files:
        payload = read_json(path, {})
        payload, stats = enrich_shard_payload(payload, companies, index_meta)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        totals["shards"] += 1
        for key in ("stocks", "mapped", "unmapped", "missing"):
            totals[key] += stats[key]

    totals["status"] = "ok"
    totals["mapped_pct"] = round(totals["mapped"] / totals["stocks"] * 100, 2) if totals["stocks"] else 0.0
    print(json.dumps(totals, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
