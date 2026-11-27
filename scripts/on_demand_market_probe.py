"""Isolated public quote probe; no portfolio input or production writes."""
import concurrent.futures as cf
import datetime as dt
import json
import math
import re
import time
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")
SYMBOL = "sh601328"

def now():
    return dt.datetime.now(TZ)

def get(url, encoding="utf-8", referer="https://gu.qq.com/"):
    errors = []
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0", "Referer": referer,
                "Cache-Control": "no-cache", "Pragma": "no-cache"})
            with urllib.request.urlopen(req, timeout=6) as res:
                return res.read(4_000_000).decode(encoding), now()
        except Exception as exc:
            errors.append(type(exc).__name__)
            if not attempt:
                time.sleep(.5)
    raise RuntimeError("HTTP_FAILED:" + ",".join(errors))

def number(value):
    v = float(value)
    if not math.isfinite(v):
        raise ValueError("NONFINITE")
    return v

def parse_tencent(text, symbol):
    match = re.search(r'v_'+symbol+r'="([^"]+)"', text)
    if not match:
        raise ValueError("QUOTE_SYMBOL_MISSING")
    f = match.group(1).split("~")
    if len(f) < 39 or f[2] != symbol[2:]:
        raise ValueError("QUOTE_SCHEMA")
    stamp = dt.datetime.strptime(f[30], "%Y%m%d%H%M%S").replace(tzinfo=TZ)
    p, prev = number(f[3]), number(f[4])
    if p <= 0 or prev <= 0:
        raise ValueError("QUOTE_PRICE")
    return {"source":"tencent","symbol":symbol,"name":f[1],"quote_at":stamp.isoformat(),
            "price":p,"prev_close":prev,"open":number(f[5]),"change_pct":(p/prev-1)*100,
            "high":number(f[33]),"low":number(f[34]),"turnover_pct":number(f[38]) if f[38] not in ("","-") else None,
            "volume_raw":f[36],"amount_raw":f[37],"raw_field_units_unverified":True}

def parse_sina(text, symbol):
    match = re.search(r'hq_str_'+symbol+r'="([^"]+)"', text)
    if not match:
        raise ValueError("QUOTE_SYMBOL_MISSING")
    f = match.group(1).split(",")
    if len(f)<32:
        raise ValueError("QUOTE_SCHEMA")
    stamp = dt.datetime.fromisoformat(f[30]+"T"+f[31]).replace(tzinfo=TZ)
    p, prev = number(f[3]), number(f[2])
    if p <= 0 or prev <= 0:
        raise ValueError("QUOTE_PRICE")
    return {"source":"sina","symbol":symbol,"name":f[0],"quote_at":stamp.isoformat(),
            "price":p,"prev_close":prev,"open":number(f[1]),"change_pct":(p/prev-1)*100,
            "high":number(f[4]),"low":number(f[5]),"volume_raw":f[8],"amount_raw":f[9],
            "raw_field_units_unverified":True}

def classify(stamp, received):
    if stamp.date()!=received.date() or stamp>received+dt.timedelta(seconds=2):
        return "STALE_OR_INVALID"
    hm=received.hour*60+received.minute
    age=(received-stamp).total_seconds()
    if 570<=hm<690 or 780<=hm<900:
        return "LIVE" if -2<=age<=60 else "STALE_OR_INVALID"
    if 690<=hm<780 and stamp.time()>=dt.time(11,29) and stamp.time()<=dt.time(11,30,59):
        return "LUNCH_LAST_QUOTE"
    if hm>=900 and dt.time(14,59)<=stamp.time()<=dt.time(15,1):
        return "CLOSE_TEST"
    return "STALE_OR_INVALID"

def quote(provider, symbol=SYMBOL):
    if provider=="tencent":
        txt, received=get("https://qt.gtimg.cn/q="+symbol,"gb18030")
        row=parse_tencent(txt,symbol)
    else:
        txt, received=get("https://hq.sinajs.cn/list="+symbol,"gb18030","https://finance.sina.com.cn/")
        row=parse_sina(txt,symbol)
    stamp=dt.datetime.fromisoformat(row["quote_at"])
    row.update(received_at=received.isoformat(),age_seconds=(received-stamp).total_seconds(),quality=classify(stamp,received))
    return row

def parse_minute(text, received, symbol):
    body=json.loads(text)
    block=body["data"][symbol]["data"]
    date=dt.datetime.strptime(str(block["date"]).replace("-",""),"%Y%m%d").date()
    if date!=received.date():
        raise ValueError("MINUTE_DATE_MISMATCH")
    rows=[]
    excluded_postclose=[]
    for s in block["data"]:
        f=s.split()
        if len(f)<3 or not re.fullmatch(r"\d{4}",f[0]):
            raise ValueError("MINUTE_SCHEMA")
        hhmm=dt.datetime.strptime(f[0],"%H%M").time()
        if hhmm>dt.time(15,0) and received.time()>=dt.time(15,0) and hhmm<=received.time():
            excluded_postclose.append(f[0])
            continue
        if not (dt.time(9,30)<=hhmm<=dt.time(11,30) or dt.time(13,0)<=hhmm<=dt.time(15,0)):
            raise ValueError("MINUTE_SESSION_INVALID:" + f[0])
        stamp=dt.datetime.combine(date,hhmm,TZ)
        if stamp>received+dt.timedelta(seconds=2):
            raise ValueError("MINUTE_FUTURE")
        p,v=number(f[1]),number(f[2])
        a=number(f[3]) if len(f)>3 else None
        if p<=0 or v<0 or (a is not None and a<0):
            raise ValueError("MINUTE_VALUE_INVALID")
        if rows and (f[0]<=rows[-1]["time"] or v<rows[-1]["cumulative_volume_raw"] or
                     (a is not None and rows[-1]["cumulative_amount_raw"] is not None and a<rows[-1]["cumulative_amount_raw"])):
            raise ValueError("MINUTE_SEQUENCE_INVALID")
        rows.append({"time":f[0],"price":p,"cumulative_volume_raw":v,"cumulative_amount_raw":a})
    if not rows:
        raise ValueError("MINUTE_EMPTY")
    stamp=dt.datetime.combine(date,dt.datetime.strptime(rows[-1]["time"],"%H%M").time(),TZ)
    expected=[]
    for begin,end in [(570,690),(780,900)]:
        for hm in range(begin+1,end+1):
            t=dt.datetime.combine(date,dt.time(hm//60,hm%60),TZ)
            if t<=received.replace(second=0,microsecond=0)-dt.timedelta(minutes=1):
                expected.append(t.strftime("%H%M"))
    present={r["time"] for r in rows}
    missing=[t for t in expected if t not in present]
    return {"source":"tencent","trade_date":str(date),"received_at":received.isoformat(),"last_minute_at":stamp.isoformat(),
            "quality":classify(stamp,received),"unit_conversion_verified":False,
            "expected_completed_minutes":len(expected),"missing_minutes":missing,
            "excluded_postclose_times":excluded_postclose,"points":rows}

def minute(symbol=SYMBOL):
    txt, received=get("https://web.ifzq.gtimg.cn/appstock/app/minute/query?code="+symbol)
    return parse_minute(txt,received,symbol)

def daily(symbol=SYMBOL):
    url="https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param="+urllib.parse.quote(symbol+",day,,,40,qfq",safe=",")
    txt, received=get(url)
    block=json.loads(txt)["data"][symbol]
    # Never silently substitute an unadjusted series for qfq.
    if "qfqday" not in block:
        raise ValueError("ADJUSTMENT_UNCONFIRMED")
    rows=[]
    for f in block["qfqday"]:
        day=dt.date.fromisoformat(f[0])
        if day>=received.date():
            continue
        o,c,h,l,v=map(number,f[1:6])
        if min(o,c,h,l)<=0 or h<max(o,c,l) or l>min(o,c,h) or v<0 or (rows and f[0]<=rows[-1]["date"]):
            raise ValueError("DAILY_INVALID")
        rows.append({"date":f[0],"open":o,"close":c,"high":h,"low":l,"volume_raw":v})
    if len(rows)<30:
        raise ValueError("DAILY_INCOMPLETE")
    return {"source":"tencent","adjustment":"qfq","received_at":received.isoformat(),"bars":rows[-30:]}


def eastmoney_flow(symbol=SYMBOL):
    params={"secid":("1." if symbol.startswith("sh") else "0.")+symbol[2:],"klt":"1","lmt":"300","fields1":"f1,f2,f3,f7","fields2":"f51,f52,f53,f54,f55,f56,f57"}
    txt,received=get("https://push2.eastmoney.com/api/qt/stock/fflow/kline/get?"+urllib.parse.urlencode(params),referer="https://quote.eastmoney.com/")
    body=json.loads(txt)
    block=body.get("data")
    if body.get("rc")!=0 or not isinstance(block,dict) or str(block.get("code"))!=symbol[2:]:
        raise ValueError("FLOW_SCHEMA_OR_SYMBOL")
    rows=[]
    for line in block.get("klines") or []:
        f=line.split(",")
        if len(f)<6:
            raise ValueError("FLOW_COLUMNS")
        stamp=dt.datetime.fromisoformat(f[0]).replace(tzinfo=TZ)
        if stamp.date()!=received.date() or stamp>received+dt.timedelta(seconds=2):
            raise ValueError("FLOW_DATE")
        if not (dt.time(9,30)<=stamp.time()<=dt.time(11,30) or dt.time(13,0)<=stamp.time()<=dt.time(15,0)):
            continue
        if rows and stamp<=dt.datetime.fromisoformat(rows[-1]["time"]):
            raise ValueError("FLOW_ORDER")
        main,small,mid,large,superlarge=map(number,f[1:6])
        if abs(main-large-superlarge)>max(100,abs(main)*.001):
            raise ValueError("FLOW_MAIN_RECONCILIATION")
        rows.append({"time":stamp.isoformat(),"main_net":main,"small_net":small,"mid_net":mid,"large_net":large,"super_net":superlarge})
    if not rows:
        raise ValueError("FLOW_EMPTY")
    stamp=dt.datetime.fromisoformat(rows[-1]["time"])
    return {"source":"eastmoney","received_at":received.isoformat(),"quality":classify(stamp,received),
            "unit":"CNY_candidate","cumulative_semantics_verified":False,"points":rows}

def five_day_history(symbol=SYMBOL):
    txt,received=get("https://web.ifzq.gtimg.cn/appstock/app/day/query?code="+symbol)
    block=json.loads(txt)["data"][symbol]["data"]
    if not isinstance(block,list):
        raise ValueError("FIVE_DAY_SCHEMA")
    sessions=[]
    for item in block:
        date=dt.datetime.strptime(str(item["date"]).replace("-",""),"%Y%m%d").date()
        if date>=received.date():
            continue
        rows=[]
        for line in item["data"]:
            f=line.split()
            if len(f)<3:
                raise ValueError("HISTORY_COLUMNS")
            t=dt.datetime.strptime(f[0],"%H%M").time()
            if not (dt.time(9,30)<=t<=dt.time(11,30) or dt.time(13,0)<=t<=dt.time(15,0)):
                continue
            p,v=number(f[1]),number(f[2])
            a=number(f[3]) if len(f)>3 else None
            if p<=0 or v<0 or (rows and (f[0]<=rows[-1]["time"] or v<rows[-1]["volume_raw"])):
                raise ValueError("HISTORY_SEQUENCE")
            rows.append({"time":f[0],"price":p,"volume_raw":v,"amount_raw":a})
        if rows:
            sessions.append({"date":str(date),"points":rows})
    sessions.sort(key=lambda row:row["date"])
    if len(sessions)<3 or len({r["date"] for r in sessions})!=len(sessions):
        raise ValueError("HISTORY_INSUFFICIENT")
    return {"source":"tencent","received_at":received.isoformat(),"sessions":sessions,"volume_semantics_verified":False}


def main():
    start=now()
    calls={"tencent_quote":lambda:quote("tencent"),"sina_quote":lambda:quote("sina"),"minute":minute,"daily":daily,"fund_flow":eastmoney_flow,"same_time_history":five_day_history}
    result={"schema_version":1,"result_kind":"public_on_demand_probe","symbol":SYMBOL,"started_at":start.isoformat(),"components":{}}
    with cf.ThreadPoolExecutor(max_workers=6) as pool:
        futures={pool.submit(fn):name for name,fn in calls.items()}
        for future in cf.as_completed(futures):
            name=futures[future]
            try:
                result["components"][name]={"status":"ok","data":future.result()}
            except Exception as exc:
                result["components"][name]={"status":"failed","error":str(exc)[:200]}
    result["finished_at"]=now().isoformat()
    components=result["components"]
    result["component_errors"]=[k for k,v in components.items() if v["status"]!="ok"]
    result["live_probe_passed"]=(not result["component_errors"] and
        any(components[k]["data"].get("quality")=="LIVE" for k in ("tencent_quote","sina_quote")) and
        components["minute"]["data"].get("quality")=="LIVE" and
        not components["minute"]["data"].get("missing_minutes"))
    result["probe_status"]="LIVE_ENDPOINTS_VALIDATED" if result["live_probe_passed"] else "NOT_LIVE_VALIDATED"
    print(json.dumps(result,ensure_ascii=False,allow_nan=False,separators=(",",":")))
    # Probe only: no trade recommendation, no portfolio, no production mutation.
    return result

if __name__=="__main__":
    main()
