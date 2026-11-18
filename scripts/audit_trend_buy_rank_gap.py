#!/usr/bin/env python3
"""Read-only audit of near-term reversal evidence in the SINGLE official Top5.

Never reorders, selects, publishes a second list, or grants trade permission.
An outcome file, if supplied, is used for historical evaluation ONLY.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def calculate_rows(formal):
    if formal.get("result_kind") != "a_share_trend_buy_result" or formal.get("mode") != "FORMAL":
        raise ValueError("OFFICIAL_FORMAL_RESULT_REQUIRED")
    date = formal.get("trade_date")
    if not isinstance(date, str) or len(date) != 10:
        raise ValueError("FORMAL_DATE_INVALID")
    source = list(formal.get("ready", [])) + list(formal.get("wait", []))
    if not all(isinstance(r, dict) and r.get("data_date") == date for r in source):
        raise ValueError("ASOF_PRICE_EVIDENCE_MISMATCH")
    rows = []
    for r in source:
        ev = r.get("phase_evidence") or {}
        tech = r.get("technical_context") or {}
        p5 = ev.get("previous_5d_return_pct")
        r5 = ev.get("return_5d_pct")
        up = ev.get("positive_days_5d")
        fresh = ev.get("fresh_break") is True
        reversal = (finite(p5) and finite(r5) and finite(up)
                    and p5 < 0 < r5 and up >= 3 and fresh)
        resistance = tech.get("first_effective_resistance") or {}
        overhead = resistance.get("price") if isinstance(resistance, dict) else None
        close = r.get("current_price")
        overhead_pct = (round((overhead / close - 1) * 100, 2)
                        if finite(overhead) and finite(close) and close > 0 and overhead > close
                        else None)
        rows.append({
            "trade_date": date, "trend_name": r.get("trend_name"),
            "code": r.get("code"), "company_name": r.get("company_name"),
            "official_rank": r.get("model_priority"), "official_status": r.get("status"),
            "wait_reason": r.get("wait_reason"),
            "previous_5d_return_pct": p5, "return_5d_pct": r5,
            "return_3d_pct": ev.get("return_3d_pct"), "positive_days_5d": up,
            "fresh_break": fresh, "close_location_pct": tech.get("close_location_pct"),
            "distance_to_ma20_pct": tech.get("distance_to_ma20_pct"),
            "volume_ratio_1d_vs_20d": tech.get("volume_ratio_1d_vs_20d"),
            "first_overhead_resistance": overhead if finite(overhead) else None,
            "overhead_distance_pct": overhead_pct,
            "reversal_observed": reversal,
            "ready_unchanged": r.get("status") == "READY",
            "setup_confirmed": r.get("structure_confirmed") is True,
        })
    return sorted(rows, key=lambda r: (
        str(r["trend_name"]),
        r["official_rank"] if isinstance(r["official_rank"], int) else 999,
        str(r["code"])))


def attach_matured_outcomes(rows, outcomes):
    if not isinstance(outcomes, dict) or not isinstance(outcomes.get("items"), list):
        raise ValueError("OUTCOME_FILE_INVALID")
    # Outcomes only annotate already frozen as-of rows; never feed ranking or signals.
    by_key = {(r.get("trade_date"), r.get("code")): r for r in outcomes["items"]}
    for r in rows:
        history = by_key.get((r["trade_date"], r["code"]), {}).get("horizons", {})
        r["observed_excess_vs_market_pct"] = {
            h: item.get("excess_vs_market_pct")
            for h in ("1", "3", "5")
            if isinstance((item := history.get(h)), dict)
            and item.get("state") == "matured"
            and finite(item.get("excess_vs_market_pct"))
        }
    return rows


def audit(formal, outcomes=None):
    rows = calculate_rows(formal)
    if outcomes is not None:
        attach_matured_outcomes(rows, outcomes)
    flagged = [r for r in rows if r["reversal_observed"]]
    lower = [r for r in flagged if isinstance(r["official_rank"], int) and r["official_rank"] >= 3]
    return {
        "kind": "NON_PRODUCTION_READ_ONLY_RANK_GAP_AUDIT",
        "trade_date": formal["trade_date"],
        "notes": [
            "原正式排名、READY/WAIT和风险门槛全部保持不变",
            "反转观察仅代表前5日跌、本5日涨、至少3个上涨日且突破此前5日高点；不是买点",
            "未来收益仅用于事后验证，不参与信号生成或评价当日是否应READY",
            "仅比较正式已入选的公司，不能衡量候选池漏选问题",
        ],
        "row_count": len(rows),
        "reversal_observation_count": len(flagged),
        "reversal_outside_top2_count": len(lower),
        "rows": rows,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--formal", required=True, type=Path)
    ap.add_argument("--outcomes", type=Path, help="historical validation/results/stocks.json, optional")
    ap.add_argument("--theme", help="optional display filter applied after audit")
    args = ap.parse_args()
    formal = json.loads(args.formal.read_text(encoding="utf-8"))
    outcomes = json.loads(args.outcomes.read_text(encoding="utf-8")) if args.outcomes else None
    result = audit(formal, outcomes)
    if args.theme is not None:
        result["rows"] = [r for r in result["rows"] if r["trend_name"] == args.theme]
        result["row_count"] = len(result["rows"])
        result["reversal_observation_count"] = sum(r["reversal_observed"] for r in result["rows"])
        result["reversal_outside_top2_count"] = sum(
            r["reversal_observed"] and isinstance(r["official_rank"], int)
            and r["official_rank"] >= 3 for r in result["rows"])
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
