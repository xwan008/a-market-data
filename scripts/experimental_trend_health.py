#!/usr/bin/env python3
"""Read-only, experimental trend-health observations for *confirmed* A-share themes.

This is NOT trend discovery, formal state migration or a trading signal.
Inputs must be a published, matching-date registry + sector audit. Historical
sector metrics come only from previous runs of this isolated shadow artifact.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from datetime import date
from pathlib import Path
from statistics import median

SCHEMA = "experimental_trend_health_v1"
HISTORY_DAYS = 20
OBSERVATION_DAYS = 120
LABELS = {0: "正常/未触发", 1: "放缓", 2: "衰减", 3: "高风险"}
PROTECTION_RANK = {"持有": 0, "警戒": 1, "防御": 2, "退出": 3}


def protection_decision(health_rank, curr):
    """Research-only protection state. Never a personal sell order or a formal Gate."""
    # EXIT requires independent price, relative-strength and breadth weakness;
    # a single severe day or high-risk health rank is insufficient.
    broken = (curr["m3"] < 0 and curr["m5"] < 0
              and curr["r"] < 0 and curr["b3"] <= 0.35
              and curr["b1"] <= 0.25)
    if broken:
        return "退出", "RED", "3/5日核心结构同时转负、弱于市场且广度明显收缩；优先核查既定持仓退出条件"
    if health_rank >= 2 or (curr["m3"] < 0 and curr["r"] <= 0 and curr["b1"] <= 0.25):
        return "防御", "ORANGE", "多维衰减或结构与广度同步走弱；暂停追高并复核保护位"
    if health_rank >= 1 or (curr["r"] < 0 and curr["b1"] <= 0.25):
        return "警戒", "YELLOW", "已出现初步退潮信号；观察承接并检查原风险计划"
    return "持有", "GREEN", "当前未触发实验保护信号；仍须遵守原持仓风险计划"


def finite(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def valid_day(value):
    if not isinstance(value, str):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def sector_metric(row):
    """Independent SW3 market observations; never infer industry fundamentals."""
    if row.get("kind") != "industry" or row.get("sample_quality") != "OK":
        return None
    ident = row.get("id", "")
    if not isinstance(ident, str) or not ident.startswith("industry:S"):
        return None
    if not finite(row.get("usable_count")) or row["usable_count"] < 3:
        return None
    fields = {
        "r": "relative_1d_vs_market_median_pct", "p": "median_1d_pct",
        "m3": "median_3d_pct", "m5": "median_5d_pct",
        "b3": "breadth_3d", "b5": "breadth_5d", "b1": "advance_ratio",
    }
    metric = {key: row.get(source) for key, source in fields.items()}
    if not all(finite(x) for x in metric.values()):
        return None
    if not all(0 <= metric[k] <= 1 for k in ("b1", "b3", "b5")):
        return None
    metric["n"] = row["usable_count"]
    return ident.removeprefix("industry:"), metric


def fresh_snapshot(sector):
    metrics = {}
    for row in sector.get("sectors", []):
        metric = sector_metric(row)
        if metric:
            metrics[metric[0]] = metric[1]
    return {"trade_date": sector["trade_date"], "market_return_median_pct": sector.get("market_median_return_1d_pct"), "industries": metrics}


def aggregate(snapshot, codes):
    values = [snapshot["industries"].get(code) for code in codes]
    if not values or any(v is None for v in values):
        return None
    return {key: median(v[key] for v in values) for key in ("r", "p", "m3", "m5", "b3", "b5", "b1")}


def health_one(theme, snapshots):
    """At least 4 ordered as-of trading-day observations, same confirmed core set."""
    name = theme.get("trend_name") or theme.get("episode_id")
    base = {"episode_id": theme.get("episode_id"), "trend_name": name,
            "formal_market_state": theme.get("market_state"),
            "role": "NON_BINDING_SHADOW_ONLY", "market_invalidation": False,
            "new_position_eligibility_changed": False,
            "protection_status": "待评估", "protection_color": "GRAY",
            "protection_is_trade_instruction": False}
    if theme.get("trend_basis", "A_SHARE") != "A_SHARE":
        return {**base, "health": "未评估", "status": "COMMODITY_FIRST_ANCHOR",
                "reason": "商品第一锚需要自身多日价格和供需证据；A股扩散不得替代商品趋势健康度。"}
    confirmed = {x.get("industry_code") for x in theme.get("industry_assessments", [])
                 if x.get("market_state") == "趋势确认"}
    core = theme.get("confirmation_audit", {}).get("core_industry_codes") or theme.get("industry_codes") or []
    codes = sorted(set(core) & confirmed)
    base["confirmed_core_industry_codes"] = codes
    if not codes:
        return {**base, "health": "未评估", "status": "NO_CONFIRMED_CORE_SW3",
                "reason": "核心申万三级行业无独立确认样本。"}
    if len(snapshots) < 4:
        return {**base, "health": "待积累", "status": "INSUFFICIENT_HISTORY",
                "reason": "需要最近4个有效交易日的同口径数据；不得用最新一天重复填充历史。"}
    four = [aggregate(s, codes) for s in snapshots[-4:]]
    if any(v is None for v in four):
        return {**base, "health": "未评估", "status": "INCOMPLETE_CORE_COVERAGE",
                "reason": "至少一个已确认核心行业在4日窗口内缺少有效客观数据。"}
    old2, old1, prev, curr = four
    previous_relative = (old2["r"] + old1["r"]) / 2
    recent_relative = (prev["r"] + curr["r"]) / 2
    # Exploratory thresholds, NOT validated gates. Each flag is independently visible.
    rs_slow = (recent_relative <= 0.75 and previous_relative - recent_relative >= 1.5)
    momentum_slow = (curr["m3"] > 0 and prev["m3"] - curr["m3"] >= 2.0)
    breadth_narrow = (curr["b5"] >= 0.5 and curr["b3"] <= curr["b5"] - 0.25)
    signals = ["RELATIVE_STRENGTH_DECAY"] if rs_slow else []
    if momentum_slow:
        signals.append("MOMENTUM_DECAY")
    if breadth_narrow:
        signals.append("BREADTH_NARROWING")
    # Severe contraction is a warning, not proof of structural invalidation.
    severe_divergence = (curr["b1"] <= 0.25 and curr["r"] < 0
                         and prev["m3"] - curr["m3"] >= 2.0)
    if severe_divergence:
        signals.append("SEVERE_SAME_DAY_CONTRACTION")
    score = int(rs_slow) + int(momentum_slow) + int(breadth_narrow)
    rank = 3 if (score == 3 or severe_divergence) else min(score, 2)
    protection, color, protection_reason = protection_decision(rank, curr)
    return {**base, "health": LABELS[rank], "status": "ASSESSED",
            "protection_status": protection, "protection_color": color,
            "protection_rank": PROTECTION_RANK[protection],
            "protection_reason": protection_reason,
            "health_rank": rank, "signal_count": score, "signals": signals,
            "dimensions": {"relative_strength_decay": rs_slow,
                           "momentum_decay": momentum_slow,
                           "breadth_narrowing": breadth_narrow,
                           "severe_same_day_contraction": severe_divergence},
            "metrics": {"relative_recent_2d_pp": round(recent_relative, 4),
                        "relative_previous_2d_pp": round(previous_relative, 4),
                        "relative_today_pp": round(curr["r"], 4),
                        "median_3d_return_pct": round(curr["m3"], 4),
                        "previous_median_3d_return_pct": round(prev["m3"], 4),
                        "advance_ratio_today": round(curr["b1"], 4),
                        "breadth_3d": round(curr["b3"], 4),
                        "breadth_5d": round(curr["b5"], 4)},
            "reason": "独立3维量价健康度实验；高风险仍不等于正式失效，无法替代结构支撑和产业反证判断。"}


def build(registry, sector, previous=None):
    previous = previous or {}
    day = registry.get("trade_date")
    if not valid_day(day) or day != sector.get("trade_date"):
        raise ValueError("ASOF_DATE_MISMATCH")
    if registry.get("status") != "COMPLETE":
        raise ValueError("FORMAL_REGISTRY_NOT_COMPLETE")
    if not isinstance(sector.get("sectors"), list) or not sector["sectors"]:
        raise ValueError("SECTOR_AUDIT_UNAVAILABLE")
    if not finite(sector.get("market_median_return_1d_pct")):
        raise ValueError("MARKET_REFERENCE_UNAVAILABLE")
    if previous and previous.get("schema_version") != SCHEMA:
        raise ValueError("INCOMPATIBLE_PREVIOUS_SHADOW_FILE")
    history = [x for x in previous.get("sector_history", []) if x.get("trade_date") != day]
    if any(not valid_day(x.get("trade_date")) for x in history):
        raise ValueError("INVALID_SHADOW_HISTORY_DATE")
    if any(x["trade_date"] > day for x in history):
        raise ValueError("FUTURE_HISTORY_INPUT_FORBIDDEN")
    snap = fresh_snapshot(sector)
    if not snap["industries"]:
        raise ValueError("NO_VALID_INDUSTRY_METRICS")
    history.append(snap)
    history.sort(key=lambda x: x["trade_date"])
    if len({x["trade_date"] for x in history}) != len(history):
        raise ValueError("DUPLICATE_SHADOW_HISTORY_DATE")
    history = history[-HISTORY_DAYS:]
    if not isinstance(registry.get("trends"), list):
        raise ValueError("REGISTRY_TRENDS_UNAVAILABLE")
    observations = []
    for t in registry["trends"]:
        if t.get("market_state") == "趋势确认":
            observations.append(health_one(t, history))
    prev_observations = [x for x in previous.get("daily_observations", [])
                         if x.get("trade_date") != day and x.get("trade_date") < day]
    prev_by_episode = {}
    for o in prev_observations:
        for row in o.get("trends", []):
            prev_by_episode[row.get("episode_id")] = row
    for row in observations:
        prev = prev_by_episode.get(row["episode_id"])
        a, b = prev.get("health_rank") if prev else None, row.get("health_rank")
        row["change_vs_previous_observation"] = (
            "WORSENED" if a is not None and b is not None and b > a
            else "IMPROVED" if a is not None and b is not None and b < a
            else "UNCHANGED" if a is not None and b is not None else "NOT_COMPARABLE")
        c, d = prev.get("protection_rank") if prev else None, row.get("protection_rank")
        row["protection_change_vs_previous_observation"] = (
            "WORSENED" if c is not None and d is not None and d > c
            else "IMPROVED" if c is not None and d is not None and d < c
            else "UNCHANGED" if c is not None and d is not None else "NOT_COMPARABLE")
    prev_observations.append({"trade_date": day, "trends": observations})
    prev_observations.sort(key=lambda x: x["trade_date"])
    return {
        "schema_version": SCHEMA, "trade_date": day,
        "status": "EXPERIMENTAL_NON_BINDING",
        "disclaimer": "实验指标；无趋势确认/降级/退出及个股买卖权限，不参与正式Gate与handoff。",
        "input_sources": {"formal_registry": "research/trend_registry.json",
                          "sector_audit": "data/research/sector_discovery_audit.json"},
        "parameters": {"relative_recent_max_pp": 0.75, "relative_deterioration_min_pp": 1.5,
                       "momentum_drop_min_pp": 2.0, "breadth_gap_min": 0.25,
                       "required_sessions": 4, "parameter_status": "EXPLORATORY_NOT_VALIDATED"},
        "latest": observations,
        "daily_observations": prev_observations[-OBSERVATION_DAYS:],
        "sector_history": history,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", default="research/trend_registry.json")
    parser.add_argument("--sector", default="data/research/sector_discovery_audit.json")
    parser.add_argument("--output", default="research/experimental_trend_health.json")
    parser.add_argument("--dry-run", action="store_true", help="print results, write nothing")
    args = parser.parse_args()
    destination = Path(args.output)
    previous = read(destination) if destination.exists() else None
    result = build(read(args.registry), read(args.sector), previous)
    if args.dry_run:
        print(json.dumps({"trade_date": result["trade_date"], "latest": result["latest"]}, ensure_ascii=False, indent=2))
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=destination.parent,
                                     prefix=".trend-health-", suffix=".tmp", delete=False) as out:
        temp_name = out.name
        json.dump(result, out, ensure_ascii=False, indent=2)
        out.write("\n")
    try:
        os.replace(temp_name, destination)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    print("EXPERIMENTAL_TREND_HEALTH_OK", result["trade_date"], len(result["latest"]))


if __name__ == "__main__":
    main()
