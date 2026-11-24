"""Offline-only external flow evidence collector. No ranking or production writes.

Input JSON: trade_date, calendar (ascending YYYY-MM-DD trading sessions),
industry_code, candidates [{code, close, change_pct}]. Frozen unadjusted
closes only. Optional per-candidate historical_closes mapping.
Output: per-stock evidence with source/time and group comparability flags.
"""
import argparse
import datetime as dt
import json
import math
from pathlib import Path
import time

SOURCE = "eastmoney_via_akshare.stock_fund_flow_individual_hist_em"
WINDOWS = (1, 5, 10, 20)


def finite(x):
    y = float(x)
    if not math.isfinite(y):
        raise ValueError("NONFINITE")
    return y


def expected_dates(packet):
    day = packet["trade_date"]
    cal = packet["calendar"]
    if cal != sorted(set(cal)) or day not in cal:
        raise ValueError("BAD_CALENDAR")
    days = [d for d in cal if d <= day][-20:]
    if len(days) != 20:
        raise ValueError("INSUFFICIENT_CALENDAR")
    return days


def normalize(flow_rows, quote_rows, dates, candidate):
    """Use actual trading turnover in yuan, never infer it from rounded net ratio."""
    def index(rows):
        out = {}
        for row in rows:
            d = str(row["日期"])[:10]
            if d not in dates:
                continue
            if d in out:
                raise ValueError("DUPLICATE_DATE")
            out[d] = row
        return out
    f, q = index(flow_rows), index(quote_rows)
    if set(f) != set(dates) or set(q) != set(dates):
        raise ValueError("MISSING_OR_STALE_SESSION")
    rows = []
    for d in dates:
        a, b = f[d], q[d]
        if str(b["股票代码"]).zfill(6) != candidate["code"]:
            raise ValueError("QUOTE_CODE_CONFLICT")
        close = finite(a["收盘价"])
        if abs(close - finite(b["收盘"])) > .011:
            raise ValueError("SOURCE_PRICE_CONFLICT")
        if abs(finite(a["涨跌幅"]) - finite(b["涨跌幅"])) > .11:
            raise ValueError("SOURCE_CHANGE_CONFLICT")
        expected = candidate.get("historical_closes", {}).get(d)
        if expected is not None and abs(close - finite(expected)) > .011:
            raise ValueError("FROZEN_HISTORY_CONFLICT")
        if d == dates[-1] and (abs(close - finite(candidate["close"])) > .011 or
                              abs(finite(a["涨跌幅"]) - finite(candidate["change_pct"])) > .11):
            raise ValueError("FROZEN_PRICE_CONFLICT")
        net, amount = finite(a["主力净流入-净额"]), finite(b["成交额"])
        big, huge = finite(a["大单净流入-净额"]), finite(a["超大单净流入-净额"])
        turnover, ratio = finite(b["换手率"]), finite(a["主力净流入-净占比"])
        if amount <= 0 or turnover < 0 or abs(net) > amount:
            raise ValueError("INVALID_AMOUNT_OR_TURNOVER")
        if abs(net - big - huge) > max(2, amount * .0002):
            raise ValueError("ORDER_SIZE_IDENTITY_CONFLICT")
        if abs(net / amount * 100 - ratio) > .15:
            raise ValueError("NET_RATIO_CONFLICT")
        rows.append(dict(date=d, close=close, net_yuan=net, amount_yuan=amount,
                         large_yuan=big, extra_large_yuan=huge, turnover_pct=turnover))
    windows = {}
    for n in WINDOWS:
        w = rows[-n:]
        net = sum(x["net_yuan"] for x in w)
        amount = sum(x["amount_yuan"] for x in w)
        windows[str(n)] = dict(net_yuan=net, amount_yuan=amount,
                               net_to_amount_pct=100 * net / amount,
                               positive_days=sum(x["net_yuan"] > 0 for x in w),
                               turnover_sum_pct=sum(x["turnover_pct"] for x in w))
    return dict(rows=rows, windows=windows)


def fetch(candidate, dates):
    import akshare as ak
    code = candidate["code"]
    if not (len(code) == 6 and code.isdigit() and code[0] in "036"):
        raise ValueError("UNSUPPORTED_CODE")
    market = "sh" if code[0] == "6" else "sz"
    flow = ak.stock_fund_flow_individual_hist_em(symbol=code, market=market)
    quotes = ak.stock_zh_a_hist_em(symbol=code, period="daily",
                               start_date=dates[0].replace("-", ""),
                               end_date=dates[-1].replace("-", ""), adjust="")
    return flow.to_dict("records"), quotes.to_dict("records"), ak.__version__


def collect(packet, fetcher=fetch):
    dates = expected_dates(packet)
    candidates = packet["candidates"]
    codes = [x["code"] for x in candidates]
    if not 1 <= len(codes) <= 5 or len(set(codes)) != len(codes):
        raise ValueError("INVALID_CANDIDATE_ROSTER")
    items = []
    for c in candidates:
        result = None
        for i in range(2):
            try:
                f, q, version = fetcher(c, dates)
                evidence = normalize(f, q, dates, c)
                result = dict(code=c["code"], status="VERIFIED", adapter_version=version,
                              source=SOURCE, source_url="https://data.eastmoney.com/zjlx/" + c["code"] + ".html",
                              evidence=evidence)
                break
            except Exception as e:
                status = "CONFLICT" if "CONFLICT" in str(e) else "UNKNOWN"
                result = dict(code=c["code"], status=status, reason=str(e)[:250],
                              source=SOURCE)
                if i == 0:
                    time.sleep(.5)
        result["retrieved_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        items.append(result)
    good = all(x["status"] == "VERIFIED" for x in items)
    versions = {x.get("adapter_version") for x in items}
    return dict(research_only=True, production_eligible=False,
                trade_date=packet["trade_date"], industry_code=packet["industry_code"],
                source=SOURCE, coverage=sum(x["status"] == "VERIFIED" for x in items),
                expected=len(items), comparable=good and len(versions)==1,
                point_in_time_verified=False, items=items)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    out = Path(a.output)
    if not out.name.startswith("top1_flow_research_") or out.suffix != ".json":
        raise ValueError("RESEARCH_OUTPUT_ONLY")
    result = collect(json.loads(Path(a.input).read_text(encoding="utf-8")))
    with out.open("x", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
    print("coverage", result["coverage"], "/", result["expected"])


if __name__ == "__main__":
    main()
