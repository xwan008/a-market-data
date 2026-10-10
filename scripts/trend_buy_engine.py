#!/usr/bin/env python3
"""A-share trend entry plan evaluator V2, offline, versioned and fail-closed.

Consumes an independently screened/researched current-date candidate JSON and
the existing full-market mechanical price-structure snapshot. No order placement.
Never writes/reads the legacy low-risk formal or handoff files.
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


def build_plan(kind, s, current, confirmed=False):
    ma20 = s.get("ma20")
    support = s.get("support_invalidation")
    breakout = s.get("breakout_level") or s.get("prior_60d_high")
    if not pos(current) or not pos(ma20) or not pos(support):
        return None
    if kind == "BREAKOUT":
        if not pos(breakout):
            return None
        entry_floor = (max(breakout * 1.002, current * .995)
                       if confirmed else breakout * 1.002)
        entry_ceiling = (min(breakout * 1.025, current * (1 + MAX_ENTRY_SLIPPAGE_PCT / 100))
                         if confirmed else breakout * 1.025)
        # Failure: recapture below former resistance, with structural stop below it.
        invalid = max(support, breakout * .985)
        trigger = "收盘站稳前60日压力位且放量/收盘位置确认；下一交易日仅在计划价格内执行"
    elif kind == "PULLBACK":
        entry_floor = (max(ma20, current * .995) if confirmed else ma20 * .995)
        entry_ceiling = (current * (1 + MAX_ENTRY_SLIPPAGE_PCT / 100)
                         if confirmed else ma20 * 1.018)
        invalid = min(support, ma20 * .985)
        trigger = "上升结构回踩MA20附近，日内触及支撑后收盘重新站上MA20且出现积极承接"
    else:
        raise ValueError("unknown_setup")
    zone = pair(entry_floor, entry_ceiling)
    if zone is None or invalid >= zone[0]:
        return None
    risk_pct = (zone[1] - invalid) / zone[1] * 100
    resistance = s.get("first_effective_resistance")
    overhead = resistance.get("price") if isinstance(resistance, dict) else None
    expected_r = ((overhead - zone[1]) / (zone[1] - invalid)
                  if pos(overhead) and overhead > zone[1] else None)
    return {
        "setup_type": kind,
        "entry_zone": zone,
        "max_entry_price": zone[1],
        "entry_trigger": trigger,
        "invalidation_price": price(invalid),
        "invalidation_rule": "计划价格结构失效；以有效收盘确认优先，跳空/重大突发风险需即时再评估，不能保证按止损价成交",
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
    if not structure or structure.get("data_status") != "verified" or structure.get("data_date") != trade_date or structure.get("history_points", 0) < 120:
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
    if current < ma60 and structure.get("structure_type") == "damaged":
        result.update(status="DROP", decision_reason="中期价格结构已破坏")
        return result
    if current < ma60:
        result.update(status="WAIT", wait_reason="WAIT_CONFIRMATION",decision_reason="尚未重新站上MA60；不靠低位直接买入")
        return result
    # A direct business link is enough to study trend setups; early pre-revenue
    # does NOT get upgraded to commercially SUPPORTED by a price breakout.
    is_early = st == "EARLY_EVIDENCE"
    shape = structure.get("structure_type")
    breakout_confirmed = bool(structure.get("breakout_confirmed") and shape == "breakout")
    pullback_confirmed = bool(
        shape == "pullback" and structure.get("higher_low")
        and pos(structure.get("current_day_low"))
        and structure["current_day_low"] <= ma20 * 1.02
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
    plan = build_plan(kind, structure, current, confirmed=(breakout_confirmed or pullback_confirmed))
    if plan is None:
        result.update(status="UNCERTAIN",decision_reason="无法建立可验证入场区或结构失效价")
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
        # An overheated BREAKOUT must NEVER publish a breakout-price zone while
        # telling the trader to WAIT for a pullback. Rebuild around real MA20
        # support, otherwise publish no conditional buy range.
        revised = build_plan("PULLBACK", structure, current, confirmed=False)
        if revised is None:
            result.update(status="UNCERTAIN", wait_reason=None,
                          setup_type=None, entry_zone=None, max_entry_price=None,
                          entry_trigger=None, invalidation_price=None,
                          invalidation_rule=None, initial_risk_pct=None,
                          upside_to_resistance_R=None, exit_plan=None,
                          decision_reason="短期追高风险高，但尚无可验证的回调支撑/失效结构")
        else:
            result.update(revised)
            if revised["initial_risk_pct"] > MAX_ENTRY_RISK_PCT:
                result.update(status="WAIT", wait_reason="WAIT_RISK_REWARD",
                              decision_reason="等待回调至MA20但可计算结构风险仍超过6%")
            else:
                result.update(status="WAIT", wait_reason="WAIT_PULLBACK",
                              decision_reason="短期明显偏离MA20；只能等待真正回调承接确认")
    elif is_early and not c.get("early_evidence_risk_review_passed"):
        result.update(status="WAIT",wait_reason="WAIT_CONFIRMATION",decision_reason="早期主题关联已有，但未完成特定早期业务风险审查")
    elif breakout_confirmed or pullback_confirmed:
        result.update(status="READY",decision_reason="截至收盘的技术确认通过；仅为下一交易日有条件入场计划")
    else:
        result.update(status="WAIT",
                      wait_reason="WAIT_BREAKOUT" if kind=="BREAKOUT" else "WAIT_PULLBACK",
                      decision_reason="公司筛选通过，尚未形成有效突破或回踩承接确认")
    return result



FOCUS_MAX_DISTANCE_PCT = 5.0  # provisional proximity gate, not a verified return predictor


def select_focus_watchlist(ready, wait, research):
    """Identify one NEAR-EXECUTABLE WAIT per sector, or explicitly abstain.

    Proximity to MA60 alone is NEVER an entry signal. A far-away hypothetical
    breakout is not a useful entry focus merely because it has a price plan.
    WATCH_ONLY does not change WAIT or authorize intraday buying.
    """
    if ready:
        return []
    sectors = sorted({str(c.get("trend_name") or "") for c in research.get("companies", [])
                      if c.get("trend_name")})
    audit = research.get("screen_audit") or {}
    scores = {str(x.get("code")): x["score"] for x in
              audit.get("pre_screen_selected", [])
              if val(x.get("score"))}
    picks = []
    for sector in sectors:
        candidates = [x for x in wait if x.get("trend_name") == sector]
        if not candidates:
            picks.append({"trend_name":sector, "status":"NO_QUALIFIED_WAIT",
                          "trade_date":research["trade_date"],
                          "code":None, "company_name":None,
                          "reason":"本板块没有合格WAIT，不能从UNCERTAIN或DROP凑数"})
            continue

        def viable(x):
            zone, p, stop, risk = (x.get("entry_zone"), x.get("current_price"),
                                  x.get("invalidation_price"), x.get("initial_risk_pct"))
            if (not isinstance(zone,list) or len(zone)!=2 or
                not all(pos(v) for v in zone) or zone[0]>zone[1] or
                not pos(p) or not pos(stop) or stop>=zone[0] or
                not pos(risk) or risk>MAX_ENTRY_RISK_PCT or
                x.get("setup_type") not in {"BREAKOUT","PULLBACK"} or
                x.get("wait_reason") == "WAIT_RISK_REWARD"):
                return None
            gap = max(zone[0]-p, 0., p-zone[1])/p*100
            if gap>FOCUS_MAX_DISTANCE_PCT:
                return None
            # An unconfirmed industry can be watched only after the individual
            # setup really confirmed; otherwise waiting for two independent
            # confirmations is NOT an imminent buyable opportunity.
            if (x.get("market_state") != "趋势确认"
                and x.get("structure_confirmed") is not True):
                return None
            return round(gap, 4)

        eligible = [(x,viable(x)) for x in candidates]
        eligible = [(x,gap) for x,gap in eligible if gap is not None]
        if not eligible:
            picks.append({"trend_name":sector,"status":"NO_NEAR_TERM_SETUP",
                          "trade_date":research["trade_date"],"code":None,
                          "company_name":None,
                          "reason":"WAIT候选当前均缺可核实的近端买点，或距观察区过远/仅接近MA60；不能强行推荐买入",
                          "near_entry_distance_threshold_pct":FOCUS_MAX_DISTANCE_PCT,
                          "wait_count":len(candidates)})
            continue

        # Confirmed price setup > proximity to validated trigger > business
        # substantiation > initial stop risk > company pre-screen score.
        eligible.sort(key=lambda z:(
            -(1 if z[0].get("structure_confirmed") is True else 0),
            z[1],
            -(1 if z[0].get("transmission")=="SUPPORTED" else 0),
            z[0]["initial_risk_pct"],
            -scores.get(z[0]["code"],.5),
            z[0]["code"],
        ))
        best, gap=eligible[0]
        blocks=[]
        if best.get("market_state")!="趋势确认":
            blocks.append("上游板块尚未趋势确认")
        if best.get("structure_confirmed") is not True:
            blocks.append("个股入场形态尚未确认")
        if best.get("transmission")=="EARLY_EVIDENCE":
            blocks.append("商业传导仍为早期证据，需再次复核经营风险")
        if not blocks:
            blocks.append("属于WAIT；必须重新运行全部买点和执行Gate，不可直接买入")
        picks.append({
            "trend_name":sector,"status":"WATCH_ONLY",
            "trade_date":research["trade_date"],
            "code":best["code"],"company_name":best["company_name"],
            "market_state":best.get("market_state"),
            "transmission":best.get("transmission"),
            "source_wait_reason":best["wait_reason"],
            "structure_confirmed":best.get("structure_confirmed") is True,
            "setup_type":best.get("setup_type"),
            "current_price":best["current_price"],"entry_zone":best["entry_zone"],
            "invalidation_price":best["invalidation_price"],
            "initial_risk_pct":best["initial_risk_pct"],
            "distance_to_entry_zone_pct":gap,
            "pre_screen_score":scores.get(best["code"]),
            "reason":"在已研究WAIT中具备最接近可验证入场计划的结构和风险条件，仍不是可执行买点",
            "blocking_conditions":blocks,
            "decision_policy":"仅为优先观察，不能替代正式READY；观察区非买入指令",
            "ranking_policy":"真实结构已确认>计划入场距离≤5%>有据可查的业务>结构风险>预筛分；无合格对象则明确空缺",
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
    ready=[x for x in rows if x["status"]=="READY"]
    wait=[x for x in rows if x["status"]=="WAIT"]
    uncertain=[x for x in rows if x["status"]=="UNCERTAIN"]
    drop=[x for x in rows if x["status"]=="DROP"]
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
        "focus_watchlist":select_focus_watchlist(ready, wait, research),
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
    if out in src or out.name in {"latest_formal_result.json","low_risk_handoff.json","trend_buy_handoff.json"}:
        raise ValueError("refuse overwrite formal/handoff")
    data=generate(json.loads(src[0].read_text(encoding="utf-8")),
                  json.loads(src[1].read_text(encoding="utf-8")))
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"trade_date":data["trade_date"],"summary":data["summary"],"production_eligible":False},ensure_ascii=False))


if __name__=="__main__":
    main()
