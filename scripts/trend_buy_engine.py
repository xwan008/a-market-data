#!/usr/bin/env python3
"""A-share trend entry plan evaluator V2, offline, versioned and fail-closed.

Consumes an independently screened/researched current-date candidate JSON and
the existing full-market mechanical price-structure snapshot. No order placement.
Produces a versioned, independently validated trade research result.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path

STATES = {"READY", "WAIT", "UNCERTAIN", "DROP"}
TRANSMISSION = {"SUPPORTED", "EARLY_EVIDENCE", "UNCERTAIN", "NOT_SUPPORTED"}
WAIT_REASONS = {"WAIT_BREAKOUT", "WAIT_PULLBACK", "WAIT_CONFIRMATION", "WAIT_RISK_REWARD"}
MAX_ENTRY_RISK_PCT = 6.0  # initial trial parameter; NOT proven optimal
MAX_MA20_DISTANCE_PCT = 8.0  # initial trial parameter; NOT proven optimal
MIN_UPSIDE_R = 1.5  # only when a grounded overhead resistance exists
MAX_ENTRY_SLIPPAGE_PCT = 1.2


def val(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def pos(x):
    return val(x) and x > 0


def price(x):
    return round(x, 3)


def pair(a, b):
    if not pos(a) or not pos(b) or a > b:
        return None
    return [price(a), price(b)]


def verified_overhead(s, current, trade_date=None):
    """Nearest independently grounded overhead; never use future/unverified pivots."""
    candidates = []
    local = s.get("first_effective_resistance") or {}
    if isinstance(local, dict) and pos(local.get("price")) and local["price"] > current:
        # Comes from the already same-day verified 65-bar structure.
        candidates.append({"status": "VERIFIED", "price": local["price"],
                           "source": local.get("source") or "asof_structure",
                           "date": local.get("date")})
    extended = s.get("attention_resistance") or {}
    date = extended.get("date") if isinstance(extended, dict) else None
    if (isinstance(extended, dict)
            and extended.get("status") == "VERIFIED"
            and extended.get("source") == "asof_180bar_confirmed_pivot"
            and val(extended.get("history_points"))
            and extended["history_points"] >= 120
            and isinstance(date, str) and len(date) == 10
            and isinstance(trade_date, str) and date <= trade_date
            and pos(extended.get("price")) and extended["price"] > current):
        candidates.append({"status": "VERIFIED", "price": extended["price"],
                           "source": extended["source"], "date": date})
    return min(candidates, key=lambda x: x["price"]) if candidates else None


def build_plan(kind, s, current, confirmed=False, trade_date=None):
    ma20 = s.get("ma20")
    breakout = s.get("breakout_level")
    if not pos(current) or not pos(ma20) or not confirmed:
        # Without actual signal confirmation, an entry/stop is not a price plan.
        return None
    if kind == "BREAKOUT":
        if not pos(breakout):
            return None
        entry_floor = (max(breakout * 1.002, current * .995)
                       if confirmed else breakout * 1.002)
        entry_ceiling = (min(breakout * 1.025, current * (1 + MAX_ENTRY_SLIPPAGE_PCT / 100))
                         if confirmed else breakout * 1.025)
        # Trade failure is a sustained recapture below the very breakout
        # boundary being traded, NOT the low of the preceding entire trend.
        invalid = price(breakout * .995)  # trial 0.5% boundary buffer
        evidence_source = "confirmed_breakout_boundary"
        failure_anchor = breakout
        trigger = "收盘确认突破已有压力位；如有效跌回本次突破价下方则本次交易假设失效"
        invalid_rule = ("本次突破价 " + str(price(breakout)) +
                        " 元为交易失效边界；参考缓冲止损价 " +
                        str(invalid) + " 元，须事先明确收盘确认与跳空处置规则")
    elif kind == "PULLBACK":
        entry_floor = (max(ma20, current * .995) if confirmed else ma20 * .995)
        entry_ceiling = (current * (1 + MAX_ENTRY_SLIPPAGE_PCT / 100)
                         if confirmed else ma20 * 1.018)
        # A PULLBACK stop must be the LOW OF THE CONFIRMED REBOUND setup.
        # An MA line or an older uptrend bottom cannot stand in for it.
        if not (pos(s.get("current_day_low"))
                and pos(s.get("previous_close"))
                and current > s["previous_close"]
                and current >= ma20
                and ma20 * .97 <= s["current_day_low"] <= ma20 * 1.02
                and s.get("higher_low") is True
                and val(s.get("close_location_pct"))
                and s["close_location_pct"] >= 55):
            return None
        failure_anchor = s["current_day_low"]
        invalid = price(failure_anchor * .995)  # trial 0.5% low buffer
        evidence_source = "same_day_confirmed_pullback_rebound_low"
        trigger = "回踩MA20附近后已有真实反弹收盘确认；未再次确认不得借原日低点追认买点"
        invalid_rule = ("本次已确认回踩低点 " + str(price(failure_anchor)) +
                        " 元为失效依据；参考缓冲止损价 " +
                        str(invalid) + " 元，须事先明确收盘确认与跳空处置规则")
    else:
        raise ValueError("unknown_setup")
    zone = pair(entry_floor, entry_ceiling)
    if zone is None or not pos(invalid) or invalid >= zone[0]:
        return None
    risk_pct = (zone[1] - invalid) / zone[1] * 100
    resistance = verified_overhead(s, current, trade_date)
    overhead = resistance["price"] if resistance else None
    # A verified obstacle between current price and the proposed entry ceiling
    # gives a negative/zero R, NOT an unknown/unbounded upside.
    expected_r = ((overhead - zone[1]) / (zone[1] - invalid)
                  if pos(overhead) else None)
    return {
        "setup_type": kind,
        "entry_zone": zone,
        "max_entry_price": zone[1],
        "entry_trigger": trigger,
        "invalidation_price": price(invalid),
        "invalidation_rule": invalid_rule,
        "setup_stop_evidence": {
            "source": evidence_source, "anchor_price": price(failure_anchor),
            "buffer_pct": 0.5, "asof_date": trade_date,
            "confirmation": "same_day_completed_bar"
        },
        "initial_risk_pct": round(risk_pct, 2),
        "upside_to_resistance_R": round(expected_r, 2) if expected_r is not None else None,
        "exit_plan": {
            "failed_setup": "突破失败或回调未获确认则不入场；已入场后触及预先定义的结构失败条件退出",
            "trend_weakening": "趋势与板块强度持续衰退时减少风险敞口；不得单凭单日回调强制清仓",
            "profit_protection": "持仓后逐步上移结构保护位，结合新高、回调低点和风险预算分批退出",
            "risk_gap": "跳空、涨跌停与成交滑点可能使真实亏损超过理论结构风险",
        },
    }


def evaluate_candidate(c, structure, trade_date):
    code = str(c.get("code") or "").zfill(6)
    st = str(c.get("transmission") or "")
    result = {
        "code": code, "company_name": c.get("company_name"),
        "industry_name": c.get("industry_name"), "current_price": c.get("asof_price"),
        "trend_name": c.get("trend_name"), "industry_code": c.get("industry_code"),
        "market_state": c.get("market_state"), "trend_state": c.get("trend_state"),
        "status": "UNCERTAIN", "wait_reason": None, "decision_reason": None,
        "transmission": st, "setup_type": None, "entry_zone": None,
        "max_entry_price": None, "entry_trigger": None, "invalidation_price": None,
        "invalidation_rule": None, "initial_risk_pct": None,
        "upside_to_resistance_R": None, "exit_plan": None,
        "structure_confirmed": False,
        "data_date": trade_date, "price_basis": "completed_daily_bar",
        "research_falsifier": c.get("research_falsifier"), "source_review": c.get("source_review"),
        "trend_phase": (structure or {}).get("trend_phase", "TRANSITION"),
        "phase_evidence": (structure or {}).get("phase_evidence") or {},
    }
    if st == "NOT_SUPPORTED" or c.get("filter_passed") is False:
        result.update(status="DROP", decision_reason="无可验证的直接主题关联或公司级硬筛失败")
        return result
    if st not in TRANSMISSION or not c.get("theme_link_verified"):
        result["decision_reason"] = "主题关联或Transmission不可核实"
        return result
    if st == "UNCERTAIN":
        result["decision_reason"] = "公司关联或核心研究证据不确定"
        return result
    if c.get("material_risk_unresolved"):
        result["decision_reason"] = "财务、退市或重大信息风险尚未解除"
        return result
    if not structure or structure.get("data_status") != "verified" or structure.get("data_date") != trade_date or structure.get("history_points", 0) < 65:
        result["decision_reason"] = "完整同日有效OHLCV结构不足；禁止用过期MA或推测价格补齐"
        return result
    if not structure.get("low_risk_eligible"):
        result.update(status="DROP", decision_reason="已有风险提示，不符趋势买点候选资格")
        return result
    current, ma20, ma60 = structure.get("current_price"), structure.get("ma20"), structure.get("ma60")
    if not (pos(current) and pos(ma20) and pos(ma60)):
        result["decision_reason"] = "缺少同日价格和均线"
        return result
    frozen_price = c.get("asof_price")
    if not pos(frozen_price) or abs(current - frozen_price) > max(.011, current * .001):
        result["decision_reason"] = "STRUCTURE_PRICE_MISMATCH: 当前公司冻结价与技术快照价格不一致"
        return result
    result["technical_context"] = {
        "ma20": ma20, "ma60": ma60,
        "support_invalidation": structure.get("support_invalidation"),
        "breakout_level": structure.get("breakout_level"),
        "prior_60d_high": structure.get("prior_60d_high"),
        "attention_resistance": structure.get("attention_resistance"),
        "recent_acceptance": structure.get("recent_acceptance"),
        "first_effective_resistance": structure.get("first_effective_resistance"),
        "distance_to_ma20_pct": structure.get("distance_to_ma20_pct"),
        "chase_risk": structure.get("chase_risk"),
        "volume_ratio_1d_vs_20d": structure.get("volume_ratio_1d_vs_20d"),
        "volume_ratio_5d_vs_20d": structure.get("volume_ratio_5d_vs_20d"),
        "relative_strength_20d_vs_market_pct": structure.get("relative_strength_20d_vs_market_pct"),
        "ma20_slope_5d_pct": structure.get("ma20_slope_5d_pct"),
        "close_location_pct": structure.get("close_location_pct"),
        "higher_low": structure.get("higher_low"),
        "trend_phase": structure.get("trend_phase", "TRANSITION"),
        "phase_evidence": structure.get("phase_evidence") or {},
    }
    # A moving-average cross is a lagging context, not proof that a newly
    # forming move has failed. Only verified structural failure can DROP.
    phase = result["trend_phase"]
    if phase == "FAILED":
        result.update(status="DROP", decision_reason="近20日关键低点有效跌破且短线跌势持续")
        return result
    if phase == "COOLING":
        result.update(status="WAIT", wait_reason="WAIT_CONFIRMATION",
                      decision_reason="放量弱收盘且涨幅扩张，暂停新建仓优先推荐；原有持仓按独立退出规则")
        return result
    if current < ma60:
        result.update(status="WAIT", wait_reason="WAIT_CONFIRMATION",
                      decision_reason="MA60下方仍可观察启动或修复；尚未形成经确认的低风险入场条件")
        return result
    # A direct business link is enough to study trend setups; early pre-revenue
    # does NOT get upgraded to commercially SUPPORTED by a price breakout.
    is_early = st == "EARLY_EVIDENCE"
    shape = structure.get("structure_type")
    breakout_confirmed = bool(structure.get("breakout_confirmed") and shape == "breakout")
    pullback_confirmed = bool(
        shape == "pullback" and structure.get("higher_low")
        and pos(structure.get("current_day_low"))
        and ma20 * .97 <= structure["current_day_low"] <= ma20 * 1.02
        and current >= ma20
        and pos(structure.get("previous_close"))
        and current > structure["previous_close"]
        and val(structure.get("close_location_pct"))
        and structure["close_location_pct"] >= 55
    )
    if breakout_confirmed:
        kind = "BREAKOUT"
    elif pullback_confirmed:
        kind = "PULLBACK"
    elif shape in {"breakout", "transition", "base_not_started"}:
        kind = "BREAKOUT"
    else:
        kind = "PULLBACK"
    result["structure_confirmed"] = breakout_confirmed or pullback_confirmed
    if not result["structure_confirmed"]:
        overheated = ((pos(structure.get("distance_to_ma20_pct"))
                       and structure["distance_to_ma20_pct"] > MAX_MA20_DISTANCE_PCT)
                      or structure.get("chase_risk") == "high")
        result.update(status="WAIT", setup_type=kind,
                      wait_reason=("WAIT_PULLBACK" if overheated else
                                   "WAIT_BREAKOUT" if kind == "BREAKOUT"
                                   else "WAIT_PULLBACK"),
                      decision_reason=("已有趋势观察价值，但尚未确认本次突破或回踩承接；"
                                       "缺对应的交易失效位，不能虚构入场区"))
        return result
    plan = build_plan(kind, structure, current, confirmed=True,
                      trade_date=trade_date)
    if plan is None:
        result.update(status="WAIT", setup_type=kind,
                      wait_reason="WAIT_CONFIRMATION",
                      decision_reason="买点形态虽已确认，但缺少有效且处于本次入场下方的近端结构失效位")
        return result
    result.update(plan)
    if c.get("market_state") != "趋势确认":
        result.update(status="WAIT", wait_reason="WAIT_CONFIRMATION",
                      decision_reason="上游板块市场状态未到趋势确认；现为"
                       + str(c.get("market_state") or "UNVERIFIED") + "，禁止只靠个股形态升级READY")
    elif plan["initial_risk_pct"] > MAX_ENTRY_RISK_PCT:
        result.update(status="WAIT", wait_reason="WAIT_RISK_REWARD", decision_reason="结构失效距离太远，风险超过试验性6%阈值")
    elif (plan["upside_to_resistance_R"] is not None
          and plan["upside_to_resistance_R"] < MIN_UPSIDE_R):
        result.update(status="WAIT", wait_reason="WAIT_RISK_REWARD",decision_reason="已知首个阻力相对于风险距离太近")
    elif (pos(structure.get("distance_to_ma20_pct"))
          and structure["distance_to_ma20_pct"] > MAX_MA20_DISTANCE_PCT
          or structure.get("chase_risk") == "high"):
        # Never pretend a future pullback was already observed. A new
        # pullback candle can be evaluated on its own completed trading day.
        result.update(status="WAIT", wait_reason="WAIT_PULLBACK",
                      entry_zone=None, max_entry_price=None, entry_trigger=None,
                      invalidation_price=None, invalidation_rule=None,
                      initial_risk_pct=None, upside_to_resistance_R=None,
                      exit_plan=None, setup_stop_evidence=None,
                      decision_reason="当前突破偏离过大；等待以后真实回踩承接，再以那次低点重新计算失效价")
    elif phase == "REPAIRING":
        result.update(status="WAIT", wait_reason="WAIT_CONFIRMATION",
                      decision_reason="修复阶段需验证后续承接；单次放量不自动形成READY")
    elif is_early and not c.get("early_evidence_risk_review_passed"):
        result.update(status="WAIT",wait_reason="WAIT_CONFIRMATION",decision_reason="早期主题关联已有，但未完成特定早期业务风险审查")
    elif breakout_confirmed or pullback_confirmed:
        result.update(status="READY",decision_reason="截至收盘的技术确认通过；仅为下一交易日有条件入场计划")
    else:
        result.update(status="WAIT",
                      wait_reason="WAIT_BREAKOUT" if kind=="BREAKOUT" else "WAIT_PULLBACK",
                      decision_reason="公司筛选通过，尚未形成有效突破或回踩承接确认")
    return result



EARLY_WATCH_MAX_PLAN_RISK_PCT = 8.0  # tentative risk filter for an unconfirmed early setup


def early_watch_reference(row):
    """Price to OBSERVE, not hypothetical entry/stop or permission to buy.

    Confirmed and risk-bounded individual setups in WAIT (e.g. sector pending)
    may retain their original setup pair; other WAITs cannot borrow a trend
    bottom, a moving average, or an unrelated previous day low as a stop.
    """
    if (row.get("structure_confirmed") is True
            and row.get("setup_type") in {"BREAKOUT", "PULLBACK"}
            and isinstance(row.get("entry_zone"), list)
            and len(row["entry_zone"]) == 2
            and all(pos(z) for z in row["entry_zone"])
            and pos(row.get("invalidation_price"))
            and row["invalidation_price"] < row["entry_zone"][0]
            and pos(row.get("initial_risk_pct"))
            and row["initial_risk_pct"] <= MAX_ENTRY_RISK_PCT):
        return {
            "stage": "STOCK_CONFIRMED_SECTOR_PENDING",
            "setup_mode": row["setup_type"],
            "conditional_trigger": "已有个股交易结构，但仍受板块/赔率/风险等WAIT条件约束；下个完整交易日复核，非买单",
            "reference_trigger_price": row["entry_zone"][0],
            "reference_zone": row["entry_zone"],
            "invalidation_price": row["invalidation_price"],
            "estimated_price_risk_pct": row["initial_risk_pct"],
            "risk_threshold_pct": MAX_ENTRY_RISK_PCT,
            "price_basis": "同日确认的本次突破或回踩结构，WAIT仍不可执行",
        }
    ctx = row.get("technical_context") or {}
    p, ma20, ma60 = row.get("current_price"), ctx.get("ma20"), ctx.get("ma60")
    if not all(pos(z) for z in (p, ma20, ma60)):
        return {
            "stage": "EVIDENCE_PENDING",
            "conditional_trigger": "缺少有效同日价格与均线",
            "reference_trigger_price": None, "reference_zone": None,
            "invalidation_price": None, "estimated_price_risk_pct": None,
        }
    kind = row.get("setup_type")
    if kind == "BREAKOUT":
        level = ctx.get("breakout_level") or ctx.get("prior_60d_high")
        if not pos(level) or abs(level / p - 1) > .08:
            # A stale/distant hypothetical breakout is not a useful nearby
            # watch trigger. Show recovery into local structure instead.
            if p < ma60:
                level = max(ma20, ma60)
                mode = "RECLAIM"
            elif p < ma20:
                level = ma20
                mode = "MA20_RECOVERY"
            else:
                level = ma20
                mode = "SETUP_REASSESSMENT"
            rule = "远期突破价不作为当前买点；观察近端结构，待有效突破或承接另行确立"
        else:
            mode = "BREAKOUT_CONFIRMATION"
            rule = "仅关注本次突破关口；尚无已确认的突破失败结构，不给交易止损或入场区"
    elif p < ma60:
        level = max(ma20, ma60)
        mode = "RECLAIM"
        rule = "等待重新站稳均线并出现明确的回踩承接，再从该次形态计算失效位"
    elif p < ma20:
        level = ma20
        mode = "MA20_RECOVERY"
        rule = "等待重新站上MA20并验证本次回踩低点与承接"
    else:
        level = ma20
        mode = "PULLBACK_HOLD"
        rule = "观察将来回踩MA20附近能否完成承接；在真实形态出现前不得指定止损"
    return {
        "stage": "PRE_TREND_WATCH", "setup_mode": mode,
        "conditional_trigger": rule,
        "reference_trigger_price": price(level),
        "reference_zone": None, "invalidation_price": None,
        "estimated_price_risk_pct": None,
        "risk_threshold_pct": EARLY_WATCH_MAX_PLAN_RISK_PCT,
        "price_basis": "同一已完成交易日观察触发价，非入场/持仓止损",
    }


def opportunity_key(row):
    """Best *new* entry today; price strength is not an unconditional bonus."""
    phase = row.get("trend_phase") or "TRANSITION"
    ref = early_watch_reference(row)
    p, trigger = row.get("current_price"), ref.get("reference_trigger_price")
    distance = abs(trigger / p - 1) * 100 if pos(p) and pos(trigger) else 100.0
    direct = (row.get("status") == "READY" and row.get("structure_confirmed") is True)
    feasible = (ref.get("reference_zone") is not None
                and pos(ref.get("invalidation_price")))
    independently_confirmed = (row.get("status") == "WAIT"
                               and row.get("structure_confirmed") is True
                               and ref.get("stage") == "STOCK_CONFIRMED_SECTOR_PENDING"
                               and feasible)
    # Confirmed READY comes first, but not if the current phase says COOLING.
    phase_tier = {
        "REACCELERATING": 0, "INITIATING": 1, "REPAIRING": 2,
        "PULLBACK": 3, "TRANSITION": 4, "COOLING": 9, "FAILED": 10
    }.get(phase, 5)
    maturity_tier = (0 if direct else 1 if independently_confirmed else 2)
    return (maturity_tier, 0 if feasible else 1, phase_tier,
            0 if distance <= 8 else 1, round(distance, 4),
            row.get("code") or "")


def top5_rank_details(row):
    """Rank RECENT trend-follow opportunities, independently of READY.

    PR54 as-of 1–3 day closing acceptance and 5–10-day momentum are ranking
    evidence. Formal 60/120-day breakout confirmation, entry-zone, overhead
    pivots, fundamentals and 1.5R must NEVER promote a Top5 attention rank.
    A swept support is observation, not a proven stop.
    """
    ctx = row.get("technical_context") or {}
    ev = row.get("phase_evidence") or {}
    recent = ctx.get("recent_acceptance") or {}
    if (recent.get("data_date") != row.get("data_date")
            or recent.get("lookback_trading_days") not in (1, 2, 3)):
        recent = {}
    pattern = recent.get("pattern") or "UNVERIFIED"
    p = row.get("current_price")
    ratio = ctx.get("volume_ratio_1d_vs_20d")
    loc = ctx.get("close_location_pct")
    fresh = ev.get("fresh_break") is True  # close above previous FIVE daily highs
    strong_break = (fresh and val(ratio) and ratio >= 1.3
                    and val(loc) and loc >= 65)
    hold = pattern == "LOCAL_SUPPORT_HOLD"
    sweep = pattern == "SAME_DAY_SWEEP_RECLAIM"
    support_observed = hold or sweep

    # Two current-cycle observations can coexist: the breakout no longer
    # hides the previous 1–3-day support and its sweep/reclaim.
    if strong_break and hold:
        signal_tier, signal = 0, "FRESH_BREAK_AND_RECENT_SUPPORT_HOLD"
    elif strong_break and sweep:
        signal_tier, signal = 1, "FRESH_BREAK_AND_RECENT_SWEEP_RECLAIM"
    elif hold:
        signal_tier, signal = 2, "RECENT_SUPPORT_HOLD"
    elif sweep:
        signal_tier, signal = 3, "RECENT_SWEEP_RECLAIM"
    elif strong_break:
        signal_tier, signal = 4, "FRESH_5D_BREAK_FOLLOW"
    elif fresh:
        signal_tier, signal = 5, "UNCONFIRMED_5D_BREAK"
    else:
        signal_tier, signal = 6, "RECENT_TREND_WATCH"

    # Use as-of 5–10d evidence, NOT the formal MA60/60-day phase label.
    ret5, up5 = ev.get("return_5d_pct"), ev.get("positive_days_5d")
    trend_tier = (0 if val(ret5) and ret5 > 0 and val(up5) and up5 >= 3
                  else 1 if val(ret5) and ret5 > 0 else 2)
    gap = ctx.get("distance_to_ma20_pct")
    if not val(gap) and pos(p) and pos(ctx.get("ma20")):
        gap = (p / ctx["ma20"] - 1) * 100
    overextended = (bool(val(gap) and gap > MAX_MA20_DISTANCE_PCT)
                    or ctx.get("chase_risk") == "high")

    # A swept support CANNOT supply a new stop or quantified risk.
    if (hold and pos(p) and pos(recent.get("support_low"))
            and recent["support_low"] < p):
        observation_distance = (p - recent["support_low"]) / p * 100
        risk_basis = "CLOSE_TO_PRIOR_SUPPORT_OBSERVATION_NOT_STOP"
    else:
        observation_distance = None
        risk_basis = "UNKNOWN_NOT_ZERO"
    position_distance = abs(gap) if val(gap) else 100.
    def normalized(v, start, span):
        return min(1., max(0., (v - start) / span)) if val(v) else 0.
    volume_strength = (
        .25 * normalized(ratio, 1., 2.)
        + .20 * normalized(ctx.get("volume_ratio_5d_vs_20d"), 1., 1.5)
        + .25 * normalized(loc, 50., 50.)
        + .20 * normalized(ctx.get("relative_strength_20d_vs_market_pct"), 0., 15.)
        + .10 * normalized(up5, 2., 3.)
    )
    # Deterministic, non-weighted comparison; no unknown risk is rewarded.
    ranking_key = (
        int(overextended), trend_tier, signal_tier,
        round(position_distance, 5),
        0 if observation_distance is not None else 1,
        round(observation_distance, 5) if observation_distance is not None else 100.,
        -round(volume_strength, 6), row.get("code") or ""
    )
    return {
        "ranking_key": ranking_key,
        "trend_tier": trend_tier, "follow_signal": signal,
        "recent_support_pattern": pattern,
        "recent_support_close_band": recent.get("support_close_band"),
        "recent_support_dates": recent.get("support_dates") or [],
        "recent_support_observed": support_observed,
        "five_day_break_confirmed_asof": strong_break,
        "observation_risk_pct": (round(observation_distance, 2)
                                 if observation_distance is not None else None),
        "risk_basis": risk_basis,
        "overextended": overextended,
        "volume_strength": round(volume_strength, 4),
        "no_r_assumed": True,
        "ignores_formal_60day_confirmation": True,
    }



def top5_rank_key(row, fundamental=None):
    """Deterministic order of *already-selected* Top5; fundamentals unused."""
    return top5_rank_details(row)["ranking_key"]


def dynamic_top5_by_theme(ready, wait, research):
    """Rank up to five names per theme, including evidence-backed trend watches.

    Immediate/nearby entry candidates come first. When fewer than five qualify,
    include only WAIT stocks with observable trend evidence; never invent a buy
    zone or fill the list merely to reach five. Cooling/failed structures stay out.
    """
    sectors = sorted({str(x.get("trend_name") or "") for x in research.get("companies", [])
                      if x.get("trend_name")})

    def trend_watch_signal(row):
        if row.get("status") != "WAIT" or row.get("transmission") not in {"SUPPORTED", "EARLY_EVIDENCE"}:
            return False
        ctx, evidence = row.get("technical_context") or {}, row.get("phase_evidence") or {}
        if not (pos(row.get("current_price")) and pos(ctx.get("ma20")) and pos(ctx.get("ma60"))):
            return False
        if row.get("trend_phase") in {"REACCELERATING", "INITIATING", "REPAIRING", "PULLBACK"}:
            return True
        if ctx.get("higher_low") is True and evidence.get("pullback_low_holds") is True:
            return True
        return (evidence.get("fresh_break") is True
                and ((val(ctx.get("volume_ratio_1d_vs_20d"))
                      and ctx["volume_ratio_1d_vs_20d"] >= 1.1)
                     or (val(ctx.get("close_location_pct"))
                         and ctx["close_location_pct"] >= 60)))

    def trend_watch_key(row):
        ctx, evidence = row.get("technical_context") or {}, row.get("phase_evidence") or {}
        break_signal = evidence.get("fresh_break") is True and (
            (val(ctx.get("volume_ratio_1d_vs_20d")) and ctx["volume_ratio_1d_vs_20d"] >= 1.1)
            or (val(ctx.get("close_location_pct")) and ctx["close_location_pct"] >= 60))
        higher_low = ctx.get("higher_low") is True and evidence.get("pullback_low_holds") is True
        phase = row.get("trend_phase")
        phase_rank = {"REACCELERATING": 0, "INITIATING": 1, "REPAIRING": 2,
                      "PULLBACK": 3, "TRANSITION": 4}.get(phase, 5)
        signal_score = 2 * int(break_signal) + 2 * int(higher_low) + int(phase_rank < 4)
        dist = ctx.get("distance_to_ma20_pct")
        if not val(dist) and pos(ctx.get("ma20")) and pos(row.get("current_price")):
            dist = (row["current_price"] / ctx["ma20"] - 1) * 100
        return (-signal_score, phase_rank, abs(dist) if val(dist) else 100,
                row.get("code") or "")

    groups = []
    for sector in sectors:
        primary, watches = [], []
        for row in ready + wait:
            if row.get("trend_name") != sector or row.get("trend_phase") in {"COOLING", "FAILED"}:
                continue
            ref = early_watch_reference(row)
            p, trigger = row.get("current_price"), ref.get("reference_trigger_price")
            distance = abs(trigger / p - 1) * 100 if pos(p) and pos(trigger) else 100
            feasible = ref.get("reference_zone") is not None
            near = distance <= 8
            if row.get("status") == "READY" or near or feasible:
                primary.append(row)
            elif trend_watch_signal(row):
                watches.append(row)
        primary.sort(key=opportunity_key)
        watches.sort(key=trend_watch_key)
        selected = primary[:5]
        selected.extend(watches[:max(0, 5 - len(selected))])
        # Keep the exact selected members/cap; only the internal order changes.
        selected.sort(key=top5_rank_key)
        primary_codes = {row["code"] for row in primary}
        groups.append({
            "trend_name": sector,
            "qualified_opportunity_count": len(primary),
            "trend_watch_candidate_count": len(watches),
            "items": [{
                "code": row["code"], "company_name": row["company_name"],
                "status": row["status"], "trend_phase": row.get("trend_phase"),
                "entry_opportunity": ("READY" if row["status"] == "READY"
                                      else "EARLY_NOT_READY" if row["code"] in primary_codes
                                      else "TREND_WATCH_ONLY"),
                "current_price": row.get("current_price"),
                "reference": early_watch_reference(row),
                "decision_reason": row.get("decision_reason"),
            } for row in selected]
        })
    return groups


def add_attention_priorities(groups, ready, wait, research):
    """Add an independent per-theme research order without reordering Top5.

    The only fundamental input is the existing same-run pre-screen audit;
    attention is not a new eligibility, READY or trading signal.
    """
    audit = research.get("screen_audit") or {}
    fundamentals = {x["code"]: x.get("fundamental_score")
                    for x in audit.get("pre_screen_selected", [])
                    if isinstance(x, dict) and x.get("code")}
    lookup = {row["code"]: row for row in ready + wait}
    phase_quality = {
        "REACCELERATING": 1.0, "INITIATING": .9, "REPAIRING": .65,
        "PULLBACK": .6, "TRANSITION": .45,
    }

    def priority(item):
        row = lookup[item["code"]]
        ref = item.get("reference") or {}
        current = item.get("current_price")
        trigger = ref.get("reference_trigger_price")
        distance = (abs(trigger / current - 1) * 100
                    if pos(current) and pos(trigger) else None)
        risk = (row.get("initial_risk_pct") if row["status"] == "READY"
                else ref.get("estimated_price_risk_pct"))
        zone = (row.get("entry_zone") if row["status"] == "READY"
                else ref.get("reference_zone"))
        stop = (row.get("invalidation_price") if row["status"] == "READY"
                else ref.get("invalidation_price"))
        valid_zone = (isinstance(zone, list) and len(zone) == 2
                      and all(pos(p) for p in zone)
                      and pos(stop) and stop < zone[0])
        ctx = row.get("technical_context") or {}
        overhead = (verified_overhead(ctx, current, row.get("data_date"))
                    if pos(current) else None) or {}
        resistance_price = overhead.get("price")
        reward_r = None
        if (overhead.get("status") == "VERIFIED" and pos(resistance_price)
                and valid_zone):
            reward_r = (resistance_price - zone[1]) / (zone[1] - stop)
        space_status = ("SUFFICIENT" if reward_r is not None
                        and reward_r >= MIN_UPSIDE_R
                        else "LIMITED" if reward_r is not None else "UNVERIFIED")
        ma20_distance = ctx.get("distance_to_ma20_pct")
        overheated = ((val(ma20_distance)
                       and ma20_distance > MAX_MA20_DISTANCE_PCT)
                      or ctx.get("chase_risk") == "high")
        # READY always first. Within WAIT reward/risk and overextension
        # precede momentum/trigger proximity; unknown is never unlimited upside.
        if row["status"] == "READY":
            tier = 0
        elif valid_zone and not overheated and space_status == "SUFFICIENT":
            tier = 1 if row.get("structure_confirmed") is True else 2
        elif valid_zone and not overheated and space_status == "UNVERIFIED":
            tier = 3
        elif valid_zone and not overheated:
            tier = 4
        elif valid_zone:
            tier = 5
        else:
            tier = 6
        quality = fundamentals.get(row["code"])
        quality = max(0, min(1, quality)) if val(quality) else None
        risk_fit = max(0, 1 - risk / 8) if val(risk) else 0
        reward_fit = (max(0, min(1, reward_r / MIN_UPSIDE_R))
                      if reward_r is not None else .25)
        risk_space_fit = .5 * risk_fit + .5 * reward_fit
        distance_fit = max(0, 1 - distance / 8) if val(distance) else 0
        phase_fit = phase_quality.get(row.get("trend_phase"), .4)
        position = .5 * risk_space_fit + .35 * distance_fit + .15 * phase_fit
        # Balanced only *inside* the non-negotiable buy-point evidence tiers.
        # A missing financial score stays neutral, never an invented advantage.
        combined = .5 * position + .5 * (quality if quality is not None else .5)
        return (tier, combined, quality, risk, distance, reward_r,
                space_status, overheated, ma20_distance, overhead)

    for group in groups:
        items = group.get("items", [])
        metrics = {item["code"]: priority(item) for item in items}
        # Single public ranking: attention fields describe the formal Top5 order.
        for rank, item in enumerate(items, 1):
            row = lookup[item["code"]]
            (tier, _, quality, risk, distance, reward_r,
             space_status, overheated, ma20_distance, overhead) = metrics[item["code"]]
            if overheated:
                judgement = "偏离MA20过大，暂缓追涨；" + (
                    "上方阻力空间不足" if space_status == "LIMITED"
                    else "上方空间仍需核验")
            elif space_status == "LIMITED" and reward_r < 0:
                judgement = "上方阻力低于计划价格上限，等待新结构"
            elif space_status == "LIMITED":
                judgement = f"上方压力仅约{reward_r:.2f}R，等待回踩或有效突破"
            elif tier == 6:
                judgement = "近期趋势可观察，尚无可执行入场与止损组合"
            elif space_status == "UNVERIFIED":
                judgement = "上方阻力空间待核验，不能视为无阻力"
            elif tier == 0:
                judgement = "优先评估条件性买点"
            elif tier == 1:
                judgement = "重点跟踪个股确认，等待板块条件"
            elif tier == 3:
                judgement = "缺可靠观察区间，暂缓买点跟踪"
            elif quality is None:
                judgement = "等待结构确认，盈利质量待核验"
            elif quality < .35:
                judgement = "优先核实盈利质量"
            elif val(risk) and risk > 6:
                judgement = "结构风险偏高，谨慎观察"
            elif val(distance) and distance > 3:
                judgement = "等待靠近合理观察位置"
            elif quality >= .65:
                judgement = "优先深研并跟踪买点"
            else:
                judgement = "关注结构确认"
            item["attention_rank"] = rank
            item["attention_judgement"] = judgement
            item["attention_resistance_check"] = {
                "status": space_status,
                "resistance_price": overhead.get("price"),
                "resistance_date": overhead.get("date"),
                "resistance_source": overhead.get("source"),
                "upside_to_resistance_R": (
                    round(reward_r, 2) if reward_r is not None else None),
                "distance_to_ma20_pct": ma20_distance,
                "chase_risk_high": bool(overheated),
                "note": (
                    "Top5按近期趋势→当前跟随信号→试错成本→量价排序；"
                    + "近期结构:" + top5_rank_details(row)["follow_signal"]
                    + "；观察风险:"
                    + top5_rank_details(row)["risk_basis"]
                    + "；未知R不计分；READY/WAIT及1.5R正式门槛独立执行"
                ),
            }
    return groups


def select_focus_watchlist(ready, wait, research, groups=None):
    """One best opportunity per theme, independent of yesterday's leader."""
    if groups is None:
        groups = dynamic_top5_by_theme(ready, wait, research)
    picks = []
    lookup = {row["code"]: row for row in ready + wait}
    for group in groups:
        theme = group["trend_name"]
        if not group["items"]:
            picks.append({"trend_name": theme, "status": "NO_CURRENT_BUY_OPPORTUNITY",
                          "trade_date": research["trade_date"], "code": None,
                          "reason": "本板块没有距离合理、非衰退且风险信息充分的近期买点候选"})
            continue
        first = group["items"][0]
        best = lookup[first["code"]]
        ref = first["reference"]
        blocks = []
        if best.get("market_state") != "趋势确认":
            blocks.append("板块趋势仍待确认")
        if not best.get("structure_confirmed"):
            blocks.append("个股标准趋势买点尚未确认")
        if ref.get("reference_zone") is None:
            blocks.append("尚缺可靠的近端结构保护位，仅供观察")
        if best.get("transmission") == "EARLY_EVIDENCE":
            blocks.append("相关业务仍属早期商业化证据")
        ctx = best.get("technical_context") or {}
        evidence = best.get("phase_evidence") or {}
        flags = {
            "volume_1d": (ctx.get("volume_ratio_1d_vs_20d") or 0) >= 1.1,
            "volume_5d": (ctx.get("volume_ratio_5d_vs_20d") or 0) >= 1.03,
            "relative_strength": (ctx.get("relative_strength_20d_vs_market_pct") or -100) >= 0,
            "ma20_turning": (ctx.get("ma20_slope_5d_pct") or -100) >= 0,
            "close_strength": (ctx.get("close_location_pct") or 0) >= 60,
            "higher_low": ctx.get("higher_low") is True
        }
        picks.append({
            "trend_name": theme,
            "status": "CURRENT_READY_FOCUS" if best["status"] == "READY" else "EARLY_FOCUS_NOT_READY",
            "trade_date": research["trade_date"],
            "code": best["code"], "company_name": best["company_name"],
            "current_price": best["current_price"], "market_state": best["market_state"],
            "source_wait_reason": best.get("wait_reason"),
            "trend_phase": best.get("trend_phase"), "phase_evidence": evidence,
            "transmission": best.get("transmission"),
            "standard_setup_confirmed": best.get("structure_confirmed") is True,
            "early_signal_count": sum(bool(v) for v in flags.values()),
            "early_signal_flags": flags,
            "reference": ref,
            "reference_trigger_distance_pct": (
                round(abs(ref["reference_trigger_price"]/best["current_price"]-1)*100, 2)
                if pos(ref.get("reference_trigger_price")) and pos(best.get("current_price"))
                else None),
            "decision_reason": "根据截至本轮收盘的最新买点成熟度、趋势阶段与入场距离动态选择",
            "remaining_blocks_to_ready": blocks,
            "not_buy_order": True
        })
    return picks


def generate(research, structure):
    if research.get("schema_version") != "trend_buy_research_v2":
        raise ValueError("invalid_research_contract")
    day = research.get("trade_date")
    if not isinstance(day,str) or len(day)!=10 or structure.get("reference_trade_date")!=day:
        raise ValueError("frozen_trade_date_mismatch")
    if research.get("coverage_complete") is not True:
        raise ValueError("incomplete_research_coverage")
    if structure.get("contract_id") != "a-share-low-risk-price-structure":
        raise ValueError("wrong_structure_contract")
    co=research.get("companies")
    if not isinstance(co,list) or not co:
        raise ValueError("missing_companies")
    ids=[str(x.get("code") or "").zfill(6) for x in co]
    if any(len(x)!=6 or not x.isdigit() for x in ids) or len(set(ids))!=len(ids):
        raise ValueError("invalid_or_duplicate_codes")
    if research.get("selected_company_count") != len(co):
        raise ValueError("selected_coverage_mismatch")
    rows=[evaluate_candidate(c, (structure.get("companies") or {}).get(code), day) for c,code in zip(co,ids)]
    formal = research.get("mode") == "FORMAL"
    audit = research.get("publication_audit") or {}
    if formal:
        required = ("fresh_company_research", "working_set_frozen",
                    "pre_screen_coverage", "company_research_coverage",
                    "structure_same_day", "no_future_evidence", "json_schema_valid")
        if any(audit.get(k) is not True for k in required):
            raise ValueError("formal_publication_gate_not_passed")
        if any(not isinstance(c.get("source_review"),str) or not c["source_review"].strip()
               for c in co):
            raise ValueError("formal_company_research_missing")
    for row in rows:
        if row["status"] not in STATES or (row["status"]=="WAIT" and row["wait_reason"] not in WAIT_REASONS):
            raise ValueError("invalid_final_status")
        if row["status"]=="READY" and (row["wait_reason"] is not None or not row["entry_zone"] or not pos(row["invalidation_price"])):
            raise ValueError("ready_lacks_trade_plan")
    # Fail closed if a VERIFIED, correctly sourced nearby pivot still bypasses
    # the READY risk/reward gate; never publish contradictory READY vs risk label.
    for row in rows:
        if (row["status"] == "READY" and val(row.get("upside_to_resistance_R"))
                and row["upside_to_resistance_R"] < MIN_UPSIDE_R):
            raise ValueError("ready_known_resistance_below_min_rr")
    ready=[x for x in rows if x["status"]=="READY"]
    wait=[x for x in rows if x["status"]=="WAIT"]
    uncertain=[x for x in rows if x["status"]=="UNCERTAIN"]
    drop=[x for x in rows if x["status"]=="DROP"]
    opportunity_groups = add_attention_priorities(
        dynamic_top5_by_theme(ready, wait, research), ready, wait, research)
    for i,x in enumerate(ready+wait,1):
        x["rank"]=i
    return {
        "schema_version":"trend_buy_result_v2",
        "run_id":research.get("run_id") or f"shadow-trend-buy-{day}",
        "result_kind":"a_share_trend_buy_result",
        "status":"COMPLETE", "trade_date":day, "mode":research.get("mode","SHADOW"),
        "structure_trade_date":structure["reference_trade_date"],
        "structure_contract":structure["contract_id"],
        "model_thresholds":{"max_entry_risk_pct":MAX_ENTRY_RISK_PCT,
                            "max_ma20_distance_pct":MAX_MA20_DISTANCE_PCT,
                            "min_resistance_reward_R":MIN_UPSIDE_R,
                            "status":"PROVISIONAL_LIVE_PARAMETERS_MONITOR_AND_REVISE"},
        "publication_audit":audit if formal else {"fresh_research":False},
        "coverage":{"selected":len(co),"judged":len(rows),"complete":True},
        "ready":ready,"wait":wait,"uncertain":uncertain,"drop":drop,
        "top5_by_theme": opportunity_groups,
        "focus_watchlist":select_focus_watchlist(ready, wait, research, opportunity_groups),
        "summary":{"ready":len(ready),"wait":len(wait),"uncertain":len(uncertain),"drop":len(drop)},
        "production_eligible":formal,
        "production_eligibility_reason":("fresh_complete_research_and_structure" if formal else
                                         "historical_or_incomplete_shadow_study")
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--research",required=True)
    ap.add_argument("--structure",required=True)
    ap.add_argument("--output",required=True)
    args=ap.parse_args()
    src=[Path(args.research).resolve(),Path(args.structure).resolve()]
    out=Path(args.output).resolve()
    if out in src or out.name in {"trend_buy_formal_result.json","trend_buy_handoff.json"}:
        raise ValueError("refuse_direct_publication_from_computation_stage")
    data=generate(json.loads(src[0].read_text(encoding="utf-8")),
                  json.loads(src[1].read_text(encoding="utf-8")))
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"trade_date":data["trade_date"],"summary":data["summary"],"production_eligible":False},ensure_ascii=False))


if __name__=="__main__":
    main()
