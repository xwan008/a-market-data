"""Point-in-time continuous research-quality evidence for the sole formal buy list.

Uses only the already Python-admitted company set, verified as-of F10 fields,
and completed as-of price-history shards. It is a *provisional proxy* for
profitability/cash-flow and medium-term peer continuity, not an inferred
probability, model ordinal, extra stock selector, or a substitute for issuer
research / independent READY risk gates.
"""
from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path

import trend_buy_prescreen_core as history
from prepare_trend_buy_candidates import F10_SOURCE


def number(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


def clamp(value):
    return max(0.0,min(1.0,value))


def verified_quality_for_selected(selected,finance,trade_date,signals,root):
    """One deterministic score per selected company or a dated data-gap marker.

    Scores are numeric 0..100 based on evidence magnitudes, not theme-relative
    ordinal model_rank; the latter remains available for research explanation
    and final ties. No use of today's later bars or any formal-result JSON.
    """
    root=Path(root)
    theme_by_industry={code:s["trend_name"] for s in signals
                       for code in s["industry_codes"]}
    by_theme=defaultdict(list)
    output={}
    history_cache={}
    seen=set()
    for c in selected:
        code=c["code"]
        if code in seen:
            raise ValueError("DUPLICATE_QUALITY_RESEARCH_CODE:"+code)
        seen.add(code)
        theme=theme_by_industry.get(c.get("industry_code"))
        if not theme:
            raise ValueError("QUALITY_UNROUTED_SELECTED_STOCK:"+code)
        output[code]={"status":"INCOMPLETE_ASOF_RESEARCH_QUALITY",
                      "asof_date":trade_date,"score":None,
                      "source":"FROZEN_F10_AND_COMPLETED_HISTORY_V1"}
        f10=(finance.get("records") or {}).get(code) or {}
        source_dates=("report_date","notice_date","update_date")
        valid_finance=(
            f10.get("source_report")==F10_SOURCE
            and f10.get("report_date")==c.get("report_date")
            and all(isinstance(f10.get(k),str) and f10[k] and f10[k]<=trade_date
                    for k in source_dates)
        )
        growth=f10.get("deduct_net_profit_yoy")
        cashflow=c.get("operating_cashflow_per_share")
        if not (valid_finance and number(growth) and number(cashflow)):
            continue
        series,error=history.completed_history(
            history.history_for(root,code,history_cache),
            trade_date,c.get("price"))
        if error:
            continue
        returns=history.metrics(series)["returns_pct"]
        if not all(number(returns[h]) for h in ("10","20","60")):
            continue
        by_theme[theme].append((c,{"growth":float(growth),
                                  "ocf_ps":float(cashflow),"returns":returns,
                                  "report_date":f10["report_date"],
                                  "notice_date":f10["notice_date"],
                                  "update_date":f10["update_date"]}))
    for theme,group in by_theme.items():
        if len(group)<3:
            continue
        percentiles={}
        for days in ("10","20","60"):
            p=history.percentile([row["returns"][days] for _,row in group])
            if not all(number(value) for value in p):
                raise ValueError("QUALITY_INVALID_PEER_PERCENTILE:"+theme)
            percentiles[days]=p
        for n,(c,field) in enumerate(group):
            core_growth=clamp((field["growth"]+25.0)/75.0)
            cashflow=1.0 if field["ocf_ps"]>0 else 0.0
            continuity=(.20*percentiles["20"][n]
                        +.15*percentiles["60"][n]
                        +.05*percentiles["10"][n])
            # A negative OCF is explicit counterevidence, not converted to a
            # superior score just because price is near its MA.
            negative_cashflow_penalty=.15 if field["ocf_ps"]<=0 else 0.0
            evidence_score=clamp(
                .50*core_growth+.10*cashflow+continuity-negative_cashflow_penalty)
            output[c["code"]]={
                "status":"VERIFIED","asof_date":trade_date,
                "score":round(evidence_score*100.0,4),
                "source":"FROZEN_F10_AND_COMPLETED_HISTORY_V1",
                "components":{
                    "core_profit_yoy_pct":round(field["growth"],4),
                    "operating_cashflow_per_share":round(field["ocf_ps"],4),
                    "core_growth_component":round(core_growth,6),
                    "cashflow_component":cashflow,
                    "peer_percentiles":{
                        h:round(percentiles[h][n],6) for h in ("10","20","60")},
                    "negative_cashflow_penalty":negative_cashflow_penalty,
                    "score_is_provisional_not_probability":True,
                },
                "report_date":field["report_date"],
                "notice_date":field["notice_date"],
                "update_date":field["update_date"],
            }
    return output
