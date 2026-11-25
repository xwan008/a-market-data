#!/usr/bin/env python3
"""Freeze per-SW3 comparable fund-flow evidence after Python admission.

No rankings, model calls, trade plans or formal publication. All amounts CNY.
Tencent first; Eastmoney whole-group fallback. No cross-provider fund rows.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import datetime as dt
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

try:
    from . import trend_buy_prescreen_core as pre
except ImportError:
    import trend_buy_prescreen_core as pre

TZ = ZoneInfo("Asia/Shanghai")
QQ = "https://proxy.finance.qq.com/cgi/cgi-bin/fundflow/hsfundtab"
QQ_QUOTE = "https://qt.gtimg.cn/q="
EM = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
SINA_QUOTE = "https://finance.sina.com.cn/realstock/company/"
PROVIDERS = ("tencent", "eastmoney")
DEFINITIONS = {
    "tencent": "主力=超大单+大单；腾讯逐笔分类，成交金额≥20万元或成交量≥6万股",
    "eastmoney": "主力=超大单+大单；东方财富自身成交分类口径",
}
WINDOWS = (1, 5, 10, 20)


def require(ok, why):
    if not ok:
        raise ValueError(why)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def numeric(v):
    require(not isinstance(v, bool), "INVALID_NUMERIC")
    v = float(v)
    require(math.isfinite(v), "NONFINITE_NUMERIC")
    return v


def symbol(code):
    require(isinstance(code, str) and re.fullmatch(r"[036]\d{5}", code), "UNSUPPORTED_MARKET")
    return ("sh" if code.startswith("6") else "sz") + code


def stamp():
    return dt.datetime.now(TZ).isoformat(timespec="seconds")


def get(url, ref, encoding="utf-8"):
    last = None
    for n in range(2):
        try:
            p = subprocess.run(
                ["curl", "-fsSL", "--max-time", "12", "-A", "Mozilla/5.0", "-e", ref, url],
                capture_output=True, timeout=15, check=True)
            return p.stdout.decode(encoding)
        except (OSError, subprocess.SubprocessError, UnicodeError) as e:
            last = str(e)
            if n == 0:
                time.sleep(1.5)
    raise RuntimeError("SOURCE_UNAVAILABLE:" + str(last)[:350])


def qq_url(code, typ):
    return QQ + "?" + urlencode({"code":symbol(code), "type":typ, "klineNeedDay":20})


def qq_data(code, typ):
    url = qq_url(code, typ)
    obj = json.loads(get(url, "https://gu.qq.com/"))
    require(obj.get("code") == 0, "TENCENT_RESPONSE_ERROR:" + typ)
    data = (obj.get("data") or {}).get(typ)
    require(isinstance(data, dict), "TENCENT_EMPTY:" + typ)
    return data, url


def actual_quotes(code, dates):
    # Separate unadjusted daily quotation, not a second fund provider.
    # Isolated subprocess provides a hard timeout even if vendor HTTP stalls.
    worker = """import akshare as ak,sys
s,b,e=sys.argv[1:]
x=ak.stock_zh_a_daily(symbol=s,start_date=b,end_date=e,adjust='')
x['date']=x.date.astype(str).str[:10]
print(x[['date','close','amount']].to_json(orient='records'))"""
    p = subprocess.run([sys.executable, "-c", worker, symbol(code),
                        dates[0].replace("-",""), dates[-1].replace("-","")],
                       capture_output=True, text=True, timeout=40, check=True)
    rows = json.loads(p.stdout.strip().splitlines()[-1])
    require(isinstance(rows,list) and len({r["date"] for r in rows})==len(rows),
            "QUOTE_DUPLICATE_SESSIONS")
    return {r["date"]: {"close":numeric(r["close"]), "amount":numeric(r["amount"])}
            for r in rows if r["date"] in dates}


def tencent_rows(code, dates, quotes, frozen):
    day = dates[-1]
    today, u1 = qq_data(code, "todayFundFlow")
    trend, u2 = qq_data(code, "todayFundTrend")
    history, u3 = qq_data(code, "historyFundFlow")
    require(today.get("stockCode") == trend.get("stockCode") == symbol(code),
            "TENCENT_SECURITY_MISMATCH")
    require("主力=超大单+大单" in today.get("desc","") and "20万元" in today["desc"]
            and "6万股" in today["desc"], "TENCENT_DEFINITION_CHANGED")
    mins = trend.get("minList") or []
    times = [x.get("time","") for x in mins]
    require(times and times == sorted(set(times)) and all(t.startswith(day.replace("-","")) for t in times)
            and times[-1] == day.replace("-","")+"1500", "TENCENT_NOT_DATED_CLOSE")
    end = mins[-1]
    main = numeric(today["mainNetIn"])
    require(main == numeric(end["MainNetInflow"]), "TENCENT_CLOSE_SUMMARY_CONFLICT")
    require(abs(main-numeric(today["superFlow"])-numeric(today["bigFlow"]))<=2
            and abs(main-numeric(today["mainIn"])+numeric(today["mainOut"]))<=2
            and abs(main+numeric(today["normalFlow"])+numeric(today["smallFlow"]))<=2,
            "TENCENT_CLASSIFICATION_CONFLICT")
    price = numeric(end["Price"])
    require(abs(price-frozen)<0.005, "TENCENT_CURRENT_PRICE_CONFLICT")
    # Exact same-session amount and identity from Tencent closing quotation.
    u4 = QQ_QUOTE + symbol(code)
    q = get(u4,"https://gu.qq.com/",encoding="gb18030").split("~")
    require(len(q)>35 and q[2]==code and q[30].startswith(day.replace("-",""))
            and q[30][8:12]>="1500", "TENCENT_QUOTE_DATE_OR_IDENTITY")
    amount = numeric(q[35].split("/")[-1])
    require(amount>0 and abs(numeric(q[3])-frozen)<0.005, "TENCENT_QUOTE_PRICE")
    require(day in quotes and abs(quotes[day]["close"]-frozen)<0.005
            and abs(amount/quotes[day]["amount"]-1)<=0.001, "TENCENT_QUOTE_AMOUNT_CONFLICT")
    buy = numeric(today["mainIn"])+numeric(today["retailIn"])
    sell = numeric(today["mainOut"])+numeric(today["retailOut"])
    # Diagnostic tolerance for minor supplier aggregation/auction differences.
    require(max(abs(buy/amount-1),abs(sell/amount-1))<=0.01, "TENCENT_TRADE_TOTAL_CONFLICT")
    hist = history.get("oneDayKlineList") or []
    hd = [r["date"] for r in hist]
    require(hd and hd==sorted(set(hd)) and hd[-1]<=day, "TENCENT_HISTORY_DATE_CONFLICT")
    mapping = {}
    for r in hist:
        d=r["date"]
        if d not in dates or d not in quotes:
            continue
        qd=quotes[d]
        require(abs(numeric(r["price"])-qd["close"])<0.005, "TENCENT_HISTORY_IDENTITY:"+d)
        mapping[d] = {"date":d,"main_net_cny":numeric(r["mainNetIn"]),
                      "amount_cny":qd["amount"]}
    if day in mapping:
        require(abs(mapping[day]["main_net_cny"]-main)<=2, "TENCENT_HISTORY_CLOSE_REVISION_CONFLICT")
    mapping[day] = {"date":day,"main_net_cny":main,"amount_cny":amount,
                    "super_net_cny":numeric(today["superFlow"]),"big_net_cny":numeric(today["bigFlow"])}
    return mapping, [u1,u2,u3,u4,SINA_QUOTE+symbol(code)+"/"]


def eastmoney_rows(code, dates, quotes, frozen):
    secid=("1." if symbol(code).startswith("sh") else "0.")+code
    url=EM+"?"+urlencode({"secid":secid,"fields1":"f1,f2,f3,f7",
         "fields2":"f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63",
         "lmt":20,"klt":101,"ut":"b2884a393a59ad64002292a3e90d46a5"})
    response=json.loads(get(url,"https://data.eastmoney.com/"))
    require(response.get("rc")==0, "EASTMONEY_RESPONSE_ERROR")
    data=response.get("data") or {}
    require(data.get("code")==code and data.get("market")==int(secid[0]),"EASTMONEY_SECURITY_MISMATCH")
    rows=[r.split(",") for r in (data.get("klines") or [])]
    rd=[r[0] for r in rows]
    require(rd and rd==sorted(set(rd)) and rd[-1]==dates[-1], "EASTMONEY_NOT_DATED_CLOSE")
    mapping={}
    for r in rows:
        d=r[0]
        if d not in dates or d not in quotes:
            continue
        net,small,mid,big,xl,pct,sp,mp,bp,xp,close,change=map(numeric,r[1:])
        q=quotes[d]
        amount=q["amount"]
        require(amount>0 and abs(net-big-xl)<=1
                and abs(net+small+mid)<=max(64,amount*1e-7),
                "EASTMONEY_CLASSIFICATION_CONFLICT:"+d)
        require(abs(pct-net/amount*100)<=0.0051 and abs(close-q["close"])<0.005,
                "EASTMONEY_QUOTE_CONFLICT:"+d)
        if d==dates[-1]:
            require(abs(close-frozen)<0.005,"EASTMONEY_CURRENT_PRICE_CONFLICT")
        mapping[d]={"date":d,"main_net_cny":net,"amount_cny":amount,
                    "super_net_cny":xl,"big_net_cny":big}
    return mapping,[url,SINA_QUOTE+symbol(code)+"/"]


def metrics(rows):
    out={}
    for n in WINDOWS:
        if len(rows)<n:
            out[str(n)]={"status":"UNKNOWN","reason":"WINDOW_NOT_COMPLETE"}
            continue
        w=rows[-n:]
        net=sum(x["main_net_cny"] for x in w)
        amount=sum(x["amount_cny"] for x in w)
        out[str(n)]={"status":"VERIFIED","net_cny":net,"amount_cny":amount,
                     "net_pct":100*net/amount,"positive_days":sum(x["main_net_cny"]>0 for x in w)}
    return out


def collect_stock(code, dates, frozen, provider, quotes):
    require(dates[-1] in quotes and quotes[dates[-1]]["amount"]>0, "EXACT_QUOTE_AMOUNT_MISSING")
    fn=tencent_rows if provider=="tencent" else eastmoney_rows
    mapping,urls=fn(code,dates,quotes,frozen)
    rows=[]
    # Contiguous suffix only; no missing session filled with zero.
    for d in reversed(dates):
        if d not in mapping:
            break
        r=mapping[d]
        amount=numeric(r["amount_cny"])
        require(amount>0 and abs(numeric(r["main_net_cny"]))<=amount,"FUND_AMOUNT_INVALID:"+d)
        rows.insert(0,r)
    require(len(rows)>=5, "CORE_FIVE_SESSIONS_MISSING")
    return {"code":code,"provider":provider,"trade_date":dates[-1],"queried_at":stamp(),
            "sources":urls,"daily":rows,"windows":metrics(rows),
            "turnover_amount_source":"sina_unadjusted_daily_exact_cny; tencent close quote crosscheck when applicable"}


def build(root, admission):
    day=admission["trade_date"]
    now=dt.datetime.now(TZ)
    require(now.date().isoformat()==day and now.hour>=15,"FUND_COLLECTION_REQUIRES_CURRENT_CLOSED_SESSION")
    index=read(root/"data/low_risk/index.json")
    require(index.get("trade_date")==day,"FROZEN_INDEX_DATE_MISMATCH")
    all_groups=[]
    cache={}
    for g in admission["industries"]:
        industry=g["industry_code"]; codes=g["selected_codes"]
        frozen={x["code"]:x for x in pre.frozen_industry_rows(root,index,industry,day)}
        inputs={}
        for code in codes:
            h=pre.history_for(root,code,cache).get("history") or []
            dates=sorted({r["date"] for r in h if isinstance(r.get("date"),str) and r["date"]<=day})[-20:]
            require(len(dates)>=5 and dates[-1]==day,"FROZEN_HISTORY_MISSING:"+code)
            inputs[code]=(dates,numeric(frozen[code]["price"]))
        def qjob(code):
            try:
                return actual_quotes(code,inputs[code][0]),None
            except Exception as e:
                return {},str(e)[:500]
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            qs=dict(zip(codes,ex.map(qjob,codes)))
        attempts=[]
        chosen=None
        for provider in PROVIDERS:
            def job(code):
                dates,price=inputs[code]
                quotes,error=qs[code]
                try:
                    require(not error,"EXACT_QUOTE_UNAVAILABLE:"+str(error))
                    return collect_stock(code,dates,price,provider,quotes),None
                except Exception as e:
                    return None,str(e)[:600]
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
                got=dict(zip(codes,ex.map(job,codes)))
            failed={c:e for c,(_,e) in got.items() if e is not None}
            attempts.append({"provider":provider,"queried_at":stamp(),"errors":failed})
            if not failed:
                chosen={"industry_code":industry,"candidate_codes":codes,"status":"VERIFIED",
                        "provider":provider,"definition":DEFINITIONS[provider],
                        "stocks":{c:got[c][0] for c in codes},"attempts":attempts}
                break
        all_groups.append(chosen or {"industry_code":industry,"candidate_codes":codes,
                          "status":"INCOMPLETE","provider":None,"stocks":{},"attempts":attempts})
    result={"trade_date":day,"collected_at":stamp(),"groups":all_groups}
    validate(admission,result)
    return result


def validate(admission, snapshot):
    require(isinstance(snapshot,dict) and snapshot.get("trade_date")==admission["trade_date"],
            "FUND_SNAPSHOT_DATE_MISMATCH")
    day=admission["trade_date"]
    collected=dt.datetime.fromisoformat(snapshot["collected_at"]).astimezone(TZ)
    require(collected.date().isoformat()==day and collected.hour>=15,"FUND_SNAPSHOT_TIME_INVALID")
    groups=snapshot.get("groups") or []
    roster=admission["industries"]
    require(len(groups)==len(roster),"FUND_GROUP_SCOPE_MISMATCH")
    for g,expected in zip(groups,roster):
        codes=expected["selected_codes"]
        require(g["industry_code"]==expected["industry_code"] and g["candidate_codes"]==codes,
                "FUND_ROSTER_MISMATCH")
        require(isinstance(g.get("attempts"),list) and g["attempts"],"FUND_ATTEMPT_MISSING")
        if g["status"]=="INCOMPLETE":
            require(g["provider"] is None and not g["stocks"]
                    and [x["provider"] for x in g["attempts"]]==list(PROVIDERS)
                    and all(x.get("errors") for x in g["attempts"]),"FUND_INCOMPLETE_INVALID")
            continue
        provider=g["provider"]
        require(g["status"]=="VERIFIED" and provider in PROVIDERS and g["definition"]==DEFINITIONS[provider]
                and set(g["stocks"])==set(codes),"FUND_PROVIDER_OR_SCOPE_INVALID")
        require([x["provider"] for x in g["attempts"]]==list(PROVIDERS[:PROVIDERS.index(provider)+1])
                and not g["attempts"][-1]["errors"],"FUND_PROVIDER_ATTEMPT_ORDER")
        for code in codes:
            s=g["stocks"][code]; rows=s["daily"]
            require(s["code"]==code and s["provider"]==provider and s["trade_date"]==day,
                    "FUND_STOCK_IDENTITY")
            ts=dt.datetime.fromisoformat(s["queried_at"]).astimezone(TZ)
            require(ts.date().isoformat()==day and ts.hour>=15 and ts<=collected,"FUND_STOCK_TIME")
            require(s.get("sources") and all(x.startswith("https://") for x in s["sources"]),
                    "FUND_SOURCE_MISSING")
            dates=[r["date"] for r in rows]
            require(5<=len(rows)<=20 and dates==sorted(set(dates)) and dates[-1]==day,
                    "FUND_DAILY_COVERAGE")
            for r in rows:
                amount=numeric(r["amount_cny"]); net=numeric(r["main_net_cny"])
                require(amount>0 and abs(net)<=amount,"FUND_DAILY_VALUE")
            require(s["windows"]==metrics(rows),"FUND_AGGREGATE_MISMATCH")
    return {g["industry_code"]:g["status"] for g in groups}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--admission",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    admission=read(a.admission)
    admission["fund_flow"]=build(root,admission)
    a.output.write_text(json.dumps(admission,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    result=read(a.output)
    statuses=validate(result,result["fund_flow"])
    print("FROZEN_FUND_FLOW",json.dumps(statuses,ensure_ascii=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
