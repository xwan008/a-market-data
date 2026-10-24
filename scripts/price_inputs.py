"""Existing quote shards provide daily momentum; 65-bar OHLCV is loaded only for screened names.

Do not persist an all-market detailed price-structure JSON.
"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import median


def load_momentum_shards(trade_date: str, shard_dir="data/shards") -> dict:
    root = Path(shard_dir)
    paths = sorted(root.glob("*.json"))
    if not paths:
        raise ValueError("momentum_shards_missing")
    companies = {}
    valid = 0
    total = 0
    for path in paths:
        shard = json.loads(path.read_text(encoding="utf-8"))
        if str(shard.get("trade_date")) != trade_date:
            raise ValueError("momentum_shard_date_mismatch:" + path.name)
        for code, stock in (shard.get("stocks") or {}).items():
            if code in companies:
                raise ValueError("momentum_duplicate_stock:" + code)
            total += 1
            trend = (stock or {}).get("trend") or {}
            memo = trend.get("momentum_evidence") or {}
            fresh = (memo.get("data_date") == trade_date
                     and trend.get("last_date") == trade_date
                     and trend.get("history_confidence") in ("high", "medium")
                     and all(isinstance(memo.get(key), (int, float))
                             for key in ("return_3d_pct", "return_5d_pct", "return_20d_pct")))
            if fresh:
                valid += 1
            companies[code] = {
                "data_status": "verified" if fresh else "unavailable",
                "data_date": memo.get("data_date"),
                "phase_evidence": {
                    "return_3d_pct": memo.get("return_3d_pct"),
                    "return_5d_pct": memo.get("return_5d_pct"),
                    "volume_ratio_1d": memo.get("volume_ratio_1d"),
                    "return_20d_pct": memo.get("return_20d_pct"),
                },
            }
    if total == 0 or valid / total < .90:
        raise ValueError(f"momentum_coverage_below_90pct:{valid}/{total}")
    return {"reference_trade_date": trade_date, "companies": companies,
            "momentum_valid": valid, "momentum_total": total}


class SelectedStockStructures:
    """Compute 65-day technical signals for hard-filtered companies only."""

    def __init__(self, trade_date: str, shard_dir="data/shards"):
        from build_full_market_price_structure import base_metrics, classify, rows_for
        self._base_metrics = base_metrics
        self._classify = classify
        self._rows_for = rows_for
        self.trade_date = trade_date
        snapshot = load_momentum_shards(trade_date, shard_dir)
        returns = [
            row["phase_evidence"]["return_20d_pct"]
            for row in snapshot["companies"].values()
            if row["data_status"] == "verified"
        ]
        if not returns:
            raise ValueError("market_relative_strength_baseline_missing")
        self.market_ret20 = median(returns) / 100

    @staticmethod
    def _attention_resistance(rows, current, trade_date):
        """As-of 120–180-bar confirmed swing-high for READY gate and Top5 risk annotation only."""
        if len(rows) < 120 or rows[-1]["date"] != trade_date:
            return {"status": "UNVERIFIED", "price": None,
                    "reason": "not_enough_same_day_history"}
        pivots = []
        for i in range(3, len(rows) - 3):
            high = rows[i]["high"]
            if (high > current * 1.005
                    and all(high >= rows[k]["high"] for k in range(i - 3, i + 4))):
                pivots.append(rows[i])
        if not pivots:
            return {"status": "UNVERIFIED", "price": None,
                    "reason": "no_confirmed_overhead_pivot_in_lookback",
                    "history_points": len(rows)}
        nearest = min(pivots, key=lambda r: r["high"])
        return {"status": "VERIFIED", "price": round(nearest["high"], 4),
                "date": nearest["date"], "source": "asof_180bar_confirmed_pivot",
                "history_points": len(rows)}

    def get(self, code: str, company: dict) -> dict:
        # Keep original 65-bar trading indicators; longer history is ONLY
        # for the separate attention/resistance annotation.
        full_rows = [r for r in self._rows_for(code)
                     if r["date"] <= self.trade_date][-180:]
        base = self._base_metrics(code, company.get("name") or code, full_rows[-65:],
                                  {"price": company.get("price")},
                                  self.trade_date, min_points=65)
        assessed = self._classify(base, self.market_ret20)
        if assessed.get("data_status") == "verified":
            assessed["attention_resistance"] = self._attention_resistance(
                full_rows, assessed["current_price"], self.trade_date)
        return assessed
