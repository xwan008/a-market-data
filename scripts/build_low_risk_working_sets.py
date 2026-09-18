#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

FORMAT = "low_risk_industry_working_set"
INDEX_FORMAT = "low_risk_industry_working_set_index"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def project_company(code: str, stock: dict[str, Any], industry: dict[str, Any]) -> dict[str, Any]:
    fundamentals = stock.get("fundamentals") or {}
    trend = stock.get("trend") or {}
    structure = trend.get("structure_60d") or {}
    evolution = structure.get("structure_evolution") or {}

    return {
        "code": code,
        "name": stock.get("name") or industry.get("name"),
        "industry_code": industry.get("industry_code"),
        "industry_name": industry.get("sw_level3_name"),
        "price": stock.get("price"),
        "prev_close": stock.get("prev_close"),
        "open": stock.get("open"),
        "high": stock.get("high"),
        "low": stock.get("low"),
        "price_time": stock.get("price_time"),
        "price_confidence": stock.get("confidence"),
        "primary_source": stock.get("primary_source"),
        "market_cap": fundamentals.get("market_cap"),
        "valuation_date": fundamentals.get("valuation_date"),
        "report_date": fundamentals.get("report_date"),
        "pe_ttm": fundamentals.get("pe_ttm"),
        "pe_dynamic": fundamentals.get("pe_dynamic"),
        "pb": fundamentals.get("pb"),
        "roe": fundamentals.get("roe"),
        "revenue_yoy": fundamentals.get("revenue_yoy"),
        "net_profit_yoy": fundamentals.get("net_profit_yoy"),
        "deduct_net_profit_yoy": fundamentals.get("deduct_net_profit_yoy"),
        "deduct_basic_eps_yoy": fundamentals.get("deduct_basic_eps_yoy"),
        "operating_cashflow_per_share": fundamentals.get("operating_cashflow_per_share"),
        "gross_margin": fundamentals.get("gross_margin"),
        "revenue": fundamentals.get("revenue"),
        "net_profit": fundamentals.get("net_profit"),
        "basic_eps": fundamentals.get("basic_eps"),
        "deduct_basic_eps": fundamentals.get("deduct_basic_eps"),
        "fundamental_warnings": fundamentals.get("warnings") or [],
        "history_confidence": trend.get("history_confidence"),
        "history_warnings": trend.get("history_warnings") or [],
        "close_change_5d_pct": trend.get("close_change_5d_pct"),
        "close_change_20d_pct": trend.get("close_change_20d_pct"),
        "high_60d": structure.get("high"),
        "low_60d": structure.get("low"),
        "ma20": structure.get("ma20"),
        "ma60": structure.get("ma60"),
        "position_pct": structure.get("position_pct"),
        "support_zones": structure.get("support_zones") or [],
        "resistance_zones": structure.get("resistance_zones") or [],
        "dense_price_zones": structure.get("dense_price_zones") or [],
        "volume_profile_method": structure.get("volume_profile_method"),
        "volume_profile_unit": structure.get("volume_profile_unit"),
        "volume_profile_zones": structure.get("volume_profile_zones") or [],
        "trend_state": evolution.get("trend_state"),
        "break_state": evolution.get("break_state"),
        "invalidation": evolution.get("invalidation"),
        "latest_high": evolution.get("latest_high"),
        "latest_low": evolution.get("latest_low"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--industry-index", default="data/research/company_industry_index.json")
    parser.add_argument("--shard-dir", default="data/shards")
    parser.add_argument("--output-dir", default="data/low_risk")
    args = parser.parse_args()

    index_path = Path(args.industry_index)
    shard_dir = Path(args.shard_dir)
    output_dir = Path(args.output_dir)
    industry_dir = output_dir / "by_industry"

    source_index = load_json(index_path)
    companies = source_index.get("companies") or {}
    if not isinstance(companies, dict) or not companies:
        raise SystemExit("company_industry_index companies missing or empty")

    expected_by_industry: dict[str, dict[str, Any]] = {}
    expected_codes: set[str] = set()
    shard_targets: dict[str, list[str]] = defaultdict(list)

    for code, industry in companies.items():
        if industry.get("mapping_status") != "mapped":
            continue
        industry_code = str(industry.get("industry_code") or "")
        industry_name = str(industry.get("sw_level3_name") or "")
        if not industry_code or not industry_name:
            raise SystemExit(f"mapped company missing level3 industry: {code}")
        group = expected_by_industry.setdefault(
            industry_code,
            {"industry_name": industry_name, "codes": []},
        )
        if group["industry_name"] != industry_name:
            raise SystemExit(
                f"industry name mismatch for {industry_code}: "
                f"{group['industry_name']!r} vs {industry_name!r}"
            )
        code = str(code)
        group["codes"].append(code)
        expected_codes.add(code)
        shard_targets[code[:5]].append(code)

    if not expected_codes:
        raise SystemExit("no mapped companies available for low-risk working sets")

    projected: dict[str, dict[str, Any]] = {}
    shard_trade_dates: set[str] = set()
    missing_shards: list[str] = []
    missing_codes: list[str] = []
    industry_mismatches: list[dict[str, str]] = []

    for shard_key in sorted(shard_targets):
        path = shard_dir / f"{shard_key}.json"
        if not path.exists():
            missing_shards.append(shard_key)
            continue
        shard = load_json(path)
        trade_date = str(shard.get("trade_date") or "")
        if trade_date:
            shard_trade_dates.add(trade_date)
        stocks = shard.get("stocks") or {}
        for code in shard_targets[shard_key]:
            stock = stocks.get(code)
            if not isinstance(stock, dict):
                missing_codes.append(code)
                continue
            industry = companies[code]
            expected_industry = str(industry.get("industry_code") or "")
            shard_industry = str(stock.get("sw_level3_code") or "")
            if shard_industry and shard_industry != expected_industry:
                industry_mismatches.append(
                    {
                        "code": code,
                        "index_industry": expected_industry,
                        "shard_industry": shard_industry,
                    }
                )
                continue
            projected[code] = project_company(code, stock, industry)

    if missing_shards or missing_codes or industry_mismatches:
        raise SystemExit(
            json.dumps(
                {
                    "missing_shards": missing_shards[:20],
                    "missing_codes": missing_codes[:50],
                    "industry_mismatches": industry_mismatches[:20],
                },
                ensure_ascii=False,
            )
        )

    if set(projected) != expected_codes:
        missing = sorted(expected_codes - set(projected))
        extra = sorted(set(projected) - expected_codes)
        raise SystemExit(
            f"projected company coverage mismatch: missing={missing[:20]} extra={extra[:20]}"
        )

    if len(shard_trade_dates) != 1:
        raise SystemExit(f"inconsistent shard trade dates: {sorted(shard_trade_dates)}")
    trade_date = next(iter(shard_trade_dates))

    industry_dir.mkdir(parents=True, exist_ok=True)
    for stale in industry_dir.glob("*.json"):
        stale.unlink()

    generated_at = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
    industry_index: dict[str, Any] = {}
    written_codes: set[str] = set()

    for industry_code in sorted(expected_by_industry):
        info = expected_by_industry[industry_code]
        codes = sorted(info["codes"])
        rows = [projected[code] for code in codes]
        payload = {
            "runtime_format": FORMAT,
            "trade_date": trade_date,
            "generated_at": generated_at,
            "industry_code": industry_code,
            "industry_name": info["industry_name"],
            "company_count": len(rows),
            "universe_company_codes": codes,
            "source": {
                "universe_authority": index_path.as_posix(),
                "company_fact_authority": f"{shard_dir.as_posix()}/<code[:5]>.json",
                "materialization": "deterministic_join_projection",
            },
            "companies": rows,
        }
        out_path = industry_dir / f"{industry_code}.json"
        write_json(out_path, payload)
        written_codes.update(codes)
        industry_index[industry_code] = {
            "industry_name": info["industry_name"],
            "company_count": len(rows),
            "file": out_path.as_posix(),
        }

    if written_codes != expected_codes:
        raise SystemExit("written industry files do not exactly cover mapped company universe")

    index_payload = {
        "runtime_format": INDEX_FORMAT,
        "trade_date": trade_date,
        "generated_at": generated_at,
        "industry_count": len(industry_index),
        "company_count": len(expected_codes),
        "source_company_industry_index": index_path.as_posix(),
        "source_shard_dir": shard_dir.as_posix(),
        "validation": {
            "status": "passed",
            "mapped_company_coverage_exact": True,
            "industry_partition_exact": True,
            "shard_trade_date_consistent": True,
            "industry_mapping_consistent": True,
        },
        "industries": industry_index,
    }
    write_json(output_dir / "index.json", index_payload)

    print(
        json.dumps(
            {
                "trade_date": trade_date,
                "industry_count": len(industry_index),
                "company_count": len(expected_codes),
                "output_dir": output_dir.as_posix(),
                "validation": "passed",
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
