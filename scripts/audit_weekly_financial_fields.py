#!/usr/bin/env python3
"""Read-only audit of weekly financial *field* coverage, independent of 95% gate.

This does not fetch fundamentals, alter data, or trigger any model. It exposes
that 'financial usable' does not mean core/deducted-profit growth available.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

KEYS=("revenue_yoy","net_profit_yoy","deduct_net_profit_yoy",
      "deduct_basic_eps_yoy","deduct_basic_eps",
      "operating_cashflow_per_share","roe")
ROOT=Path(__file__).resolve().parents[1]


def number(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool)


def calculate(latest):
    stock=latest.get("stocks") or {}
    if not isinstance(stock,dict) or not stock:
        raise ValueError("missing_full_market_stocks")
    count=len(stock)
    counts={name:sum(number((row.get("fundamentals") or {}).get(name))
                     for row in stock.values()) for name in KEYS}
    return {
        "mode":"V4_WEEKLY_FINANCIAL_FIELD_COVERAGE_ONLY",
        "trade_date":latest.get("trade_date"),
        "stock_count":count,
        "reported_financial_usable":(latest.get("fundamental_stats") or {}).get("financial_usable"),
        "reported_valuation_usable":(latest.get("fundamental_stats") or {}).get("valuation_usable"),
        "deduct_profit_growth_usable_by_fetcher":(
            latest.get("fundamental_stats") or {}).get("deduct_profit_growth_usable"),
        "field_coverage":{
            name:{"count":value,"total":count,
                  "coverage_pct":round(100*value/count,2)}
            for name,value in counts.items()},
        "core_profit_growth_available":sum(
            number((row.get("fundamentals") or {}).get("deduct_net_profit_yoy"))
            or number((row.get("fundamentals") or {}).get("deduct_basic_eps_yoy"))
            for row in stock.values()),
        "data_quality_warning_not_failure":True,
        "new_stock_research_or_forecast_generated":False
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--latest",type=Path,default=ROOT/"data/latest.json")
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    stats=calculate(json.loads(args.latest.read_text(encoding="utf-8")))
    print("V4_WEEKLY_FIELD_COVERAGE "+json.dumps(stats,ensure_ascii=False))
    if args.output:
        file=args.output.resolve()
        if "shadow" not in str(file).lower() or any(x in str(file) for x in
                ("trend_buy_formal_result","trend_buy_handoff")):
            raise ValueError("shadow_only_output_required")
        file.parent.mkdir(parents=True,exist_ok=True)
        file.write_text(json.dumps(stats,ensure_ascii=False,indent=2)+"\n",
                        encoding="utf-8")
    total=stats["stock_count"]
    core=stats["core_profit_growth_available"]
    if core/total<.5:
        # Does not fail weekly refresh, but makes the insufficiency visible.
        print("::warning title=V4 core-profit coverage is low::"
              f"Only {core}/{total} stocks have a usable deducted-profit growth field. "
              "This DOES NOT invalidate the already-established 95% general financial gate.")
    return stats


if __name__=="__main__":
    main()
