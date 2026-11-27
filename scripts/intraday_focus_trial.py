"""Focused read-only trial: real public quotes, private portfolio never printed."""
from __future__ import annotations
import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import threading
import urllib.parse
import urllib.request
import on_demand_market_probe as p
import focus_private_transport as transport
from trend_buy_handoff import validate_items, project
from validate_trend_publication_pair import validate as validate_pair

ROOT=Path(__file__).resolve().parents[1]
SLOTS=("09:37","10:37","13:17","14:27")
INDEXES={"sh000001":"上证指数","sz399001":"深证成指","sz399006":"创业板指","sz399986":"中证银行指数（板块代理）"}
FIELDS=("股票代码","持仓股数","数据状态","持仓状态")
EAST_LOCK=threading.BoundedSemaphore(2)
UT="bd1d9ddb04089700cf9c27f6f7426281"

def wrapped(fn):
    try:
        return {"status":"ok","data":fn()}
    except Exception as exc:
        # Exceptions from private records or HTTP responses must not disclose their contents.
        return {"status":"failed","error":type(exc).__name__+":"+str(exc)[:100] if isinstance(exc,ValueError) else (str(exc)[:100] if isinstance(exc,RuntimeError) and str(exc).startswith("HTTP_FAILED:") else type(exc).__name__)}

def symbol(code):
    if not isinstance(code,str) or not re.fullmatch(r"\d{6}",code):
        raise ValueError("INVALID_CODE")
    if code.startswith(("60","68")):
        return "sh"+code
    if code.startswith(("00","30")):
        return "sz"+code
    raise ValueError("UNSUPPORTED_EXCHANGE")

def confirmed_positions(records):
    by={}
    unknown=0
    for row in records:
        f=row.get("fields") or {}
        code=f.get("股票代码")
        try:
            sym=symbol(code)
        except ValueError:
            unknown+=1
            continue
        by.setdefault(sym,[]).append(f)
    good=[]
    bad=unknown
    for sym,rows in by.items():
        if len(rows)!=1:
            bad+=1
            continue
        f=rows[0]
        q=f.get("持仓股数")
        confirmed=f.get("数据状态")=="用户已确认"
        integral=type(q) in (int,float) and math.isfinite(q) and q==int(q)
        if confirmed and f.get("持仓状态")=="持仓中" and integral and q>0:
            good.append(sym)
        elif not (confirmed and f.get("持仓状态")=="已清仓" and integral and q==0):
            bad+=1
    return sorted(good),bad

def holdings():
    token=os.environ.get("AIRTABLE_TOKEN")
    base=os.environ.get("AIRTABLE_BASE_ID")
    table=os.environ.get("FOCUS_HOLDINGS_TABLE_ID")
    if not token or not base or not table:
        raise ValueError("PORTFOLIO_CREDENTIALS_MISSING")
    records=[]; offset=None; seen=set()
    for _ in range(50):
        args=[("pageSize","100")]+[("fields[]",f) for f in FIELDS]
        if offset:
            args.append(("offset",offset))
        req=urllib.request.Request("https://api.airtable.com/v0/"+base+"/"+table+"?"+urllib.parse.urlencode(args),headers={"Authorization":"Bearer "+token})
        with urllib.request.urlopen(req,timeout=7) as res:
            x=json.load(res)
        if not isinstance(x.get("records"),list):
            raise ValueError("PORTFOLIO_SCHEMA")
        records.extend(x["records"])
        offset=x.get("offset")
        if not offset:
            good,bad=confirmed_positions(records)
            return {"symbols":good,"unknown_count":bad,"complete":bad==0}
        if offset in seen:
            raise ValueError("PORTFOLIO_PAGINATION")
        seen.add(offset)
    raise ValueError("PORTFOLIO_PAGINATION")

def baseline(expected):
    def load(name):
        return json.loads((ROOT/"research"/name).read_text())
    h=load("trend_buy_handoff.json")
    fbytes=(ROOT/"research/trend_buy_formal_result.json").read_bytes()
    f=json.loads(fbytes)
    sha=hashlib.sha1(b"blob "+str(len(fbytes)).encode()+b"\0"+fbytes).hexdigest()
    reg=load("trend_registry.json")
    sector=load("trend_handoff.json")
    if validate_pair(reg,sector) or project(f,sha,shadow=False)!=h:
        raise ValueError("BASELINE_PAIR")
    if h.get("trade_date")!=expected or sector.get("trade_date")!=expected or h.get("shadow") is not False:
        raise ValueError("BASELINE_DATE")
    rows=validate_items(h)
    return {"trade_date":expected,"run_id":h["source_run_id"],"symbols":[symbol(x["code"]) for x in rows]}

def provider_stamp(value):
    if value is None or value in ("","-"):
        raise ValueError("PROVIDER_TIME_MISSING")
    v=str(value)
    if re.fullmatch(r"\d{12}|\d{14}",v):
        return dt.datetime.strptime(v,"%Y%m%d%H%M" if len(v)==12 else "%Y%m%d%H%M%S").replace(tzinfo=p.TZ)
    return dt.datetime.fromtimestamp(p.number(value),p.TZ)

def east_request(path,params):
    params={**params,"ut":UT}
    url="https://push2.eastmoney.com/api/qt/"+path+"?"+urllib.parse.urlencode(params,safe="+:!,")
    with EAST_LOCK:
        txt,received=p.get(url,referer="https://quote.eastmoney.com/")
    body=json.loads(txt)
    if body.get("rc")!=0 or not isinstance(body.get("data"),dict):
        raise ValueError("EAST_RESPONSE_DATA_MISSING")
    return body["data"],received

def east_quote(sym):
    market="1" if sym.startswith("sh") else "0"
    fields="f57,f58,f43,f44,f45,f46,f60,f47,f48,f50,f168,f86,f127"
    d,received=east_request("stock/get",{"secid":market+"."+sym[2:],"fields":fields,"fltt":"2","invt":"2"})
    if str(d.get("f57"))!=sym[2:]:
        raise ValueError("EAST_QUOTE_ID")
    stamp=provider_stamp(d.get("f86"))
    def optional(key):
        return None if d.get(key) in (None,"-","") else p.number(d[key])
    return {"source":"eastmoney","quote_at":stamp.isoformat(),"received_at":received.isoformat(),"quality":p.classify(stamp,received),
            "price":optional("f43"),"prev_close":optional("f60"),"volume_lots_candidate":optional("f47"),
            "amount_cny_candidate":optional("f48"),"volume_ratio_candidate":optional("f50"),
            "turnover_pct_candidate":optional("f168"),"provider_industry":d.get("f127")}

def board_quotes():
    rows={}
    for page in range(1,5):
        d,received=east_request("clist/get",{"pn":page,"pz":100,"po":1,"np":1,"fltt":2,"fid":"f12","fs":"m:90+t:2+f:!50","fields":"f12,f14,f2,f3,f6,f62,f104,f105,f124"})
        items=d.get("diff")
        if isinstance(items,dict):
            items=list(items.values())
        if not isinstance(items,list):
            raise ValueError("BOARD_SCHEMA")
        for x in items:
            name=x.get("f14")
            if not isinstance(name,str) or name in rows:
                continue
            try:
                stamp=provider_stamp(x.get("f124"))
            except (ValueError,TypeError,OverflowError,OSError):
                stamp=None
            rows[name]={"source":"eastmoney","board_code":x.get("f12"),"name":name,
                        "change_pct_candidate":x.get("f3"),"amount_candidate":x.get("f6"),"main_flow_candidate":x.get("f62"),
                        "up":x.get("f104"),"down":x.get("f105"),"quote_at":stamp.isoformat() if stamp else None,
                        "quality":p.classify(stamp,received) if stamp else "TIME_UNVERIFIED"}
        if len(rows)>=d.get("total",len(rows)) or not items:
            break
    if not rows:
        raise ValueError("BOARD_EMPTY")
    return rows

def locked_flow(sym):
    with EAST_LOCK:
        return p.eastmoney_flow(sym)

def component_calls(sym):
    return {"tencent_quote":lambda:p.quote("tencent",sym),"sina_quote":lambda:p.quote("sina",sym),
            "minute":lambda:p.minute(sym),"daily":lambda:p.daily(sym),"fund_flow":lambda:locked_flow(sym),
            "same_time_history":lambda:p.five_day_history(sym),"east_quote":lambda:east_quote(sym)}

def data(c,key):
    return c.get(key,{}).get("data") or {}

def metrics(c):
    m=data(c,"minute"); h=data(c,"same_time_history"); q=data(c,"sina_quote"); tq=data(c,"tencent_quote")
    points=m.get("points") or []
    # Validate units on contemporaneous endpoints; do not assume historical or vendor flow semantics.
    units=False
    if points and q and tq:
        try:
            v=float(q["volume_raw"]); tv=float(tq["volume_raw"])*100; mv=points[-1]["cumulative_volume_raw"]*100
            a=float(q["amount_raw"]); ma=points[-1]["cumulative_amount_raw"]
            units=(v>0 and a>0 and abs(tv-v)/v<.02 and abs(mv-v)/v<.02 and abs(ma-a)/a<.02)
        except (ValueError,TypeError,KeyError,ZeroDivisionError):
            pass
    result={"volume_units_crosschecked":units,"same_time_volume_ratio":None,"same_time_sample_count":0}
    if not points or not units or m.get("missing_minutes"):
        return result
    last=points[-1]
    result["vwap_candidate"]=last["cumulative_amount_raw"]/(last["cumulative_volume_raw"]*100) if last["cumulative_volume_raw"] else None
    # Historical cumulative lots are checked against the same provider's last-day daily volume.
    daily={x["date"]:x["volume_raw"] for x in data(c,"daily").get("bars",[])}
    samples=[]
    for session in h.get("sessions",[]):
        ps=session["points"]
        end=ps[-1]
        hist=daily.get(session["date"])
        if len(ps)<240 or end["time"]!="1500" or not hist or abs(end["volume_raw"]-hist)/hist>.02:
            continue
        row=next((x for x in ps if x["time"]==last["time"]),None)
        if row and row["volume_raw"]>0:
            samples.append(row["volume_raw"])
    result["same_time_sample_count"]=len(samples)
    if len(samples)>=3:
        result["same_time_volume_ratio"]=last["cumulative_volume_raw"]/statistics.median(samples)
    return result

def collect(symbols):
    out={sym:{} for sym in symbols}
    with cf.ThreadPoolExecutor(max_workers=12) as pool:
        tasks={pool.submit(wrapped,fn):(sym,k) for sym in symbols for k,fn in component_calls(sym).items()}
        for future in cf.as_completed(tasks):
            sym,k=tasks[future]; out[sym][k]=future.result()
    return {sym:{"components":c,"metrics":metrics(c)} for sym,c in out.items()}

def summary(row):
    cs=row["components"]
    return {"components":{k:v["status"] for k,v in cs.items()},
            "errors":{k:v.get("error") for k,v in cs.items() if v["status"]!="ok"},
            "quote_quality":[data(cs,k).get("quality") for k in ("tencent_quote","sina_quote")],
            "minute_points":len(data(cs,"minute").get("points",[])),
            "flow_points":len(data(cs,"fund_flow").get("points",[])),
            "daily_bars":len(data(cs,"daily").get("bars",[])),
            "metrics":row["metrics"]}

def main():
    start=p.now()
    expected=os.environ.get("EXPECTED_BASELINE_DATE")
    if not expected:
        raise SystemExit("EXPECTED_BASELINE_DATE_REQUIRED")
    with cf.ThreadPoolExecutor(max_workers=5) as pool:
        bf=pool.submit(wrapped,lambda:baseline(expected))
        hf=pool.submit(wrapped,holdings)
        boardf=pool.submit(wrapped,board_quotes)
        idxf={sym:pool.submit(wrapped,lambda sym=sym:p.quote("sina",sym)) for sym in INDEXES}
        b=bf.result(); h=hf.result()
        public=set(b.get("data",{}).get("symbols",[]))
        private=set(h.get("data",{}).get("symbols",[]))
        rows=collect(sorted(public|private))
        board=boardf.result()
        indexes={sym:f.result() for sym,f in idxf.items()}
    boards=board.get("data",{})
    # No portfolio identifiers, holdings counts per symbol, or private errors are printed.
    public_rows={sym:rows[sym] for sym in sorted(public)}
    related={}
    for sym,row in public_rows.items():
        name=data(row["components"],"east_quote").get("provider_industry")
        if not name and sym=="sh601328":
            name="银行"
        related[sym]={"taxonomy":"eastmoney_proxy_not_SW3","data":boards.get(name),"status":"ok" if name in boards else "UNRESOLVED"}
    result={"schema_version":1,"result_kind":"focus_pipeline_trial","mode":"CLOSE_TEST" if start.time()>=dt.time(15) else "TRIAL",
            "run_id":str(os.environ.get("GITHUB_RUN_ID"))+"-"+str(os.environ.get("GITHUB_RUN_ATTEMPT","1")),"started_at":start.isoformat(),"finished_at":p.now().isoformat(),
            "trade_date":str(start.date()),"baseline":b,"public_stocks":public_rows,
            "portfolio_status":h["status"],"portfolio_complete":h.get("data",{}).get("complete",False),
            "portfolio_confirmed_count":len(private),"portfolio_unresolved_count":h.get("data",{}).get("unknown_count"),
            "portfolio_collected_count":len(private&rows.keys()),
            "portfolio_all_components_ok_count":sum(all(v["status"]=="ok" for v in rows[s]["components"].values()) for s in private),
            "market_indexes":indexes,"board_source_status":board["status"],"board_source_error":board.get("error"),"public_related_boards":related,
            "status":"TRIAL_NOT_PRODUCTION"}
    # Private readback includes market quotes only, not costs or position quantities.
    private_payload={**result,"result_kind":"focus_pipeline_private_trial","stocks":rows}
    private_payload.pop("public_stocks",None)
    # Include each target provider industry proxy only inside the private output.
    private_payload["related_boards"]={sym:{"taxonomy":"eastmoney_proxy_not_SW3","data":boards.get(data(row["components"],"east_quote").get("provider_industry"))} for sym,row in rows.items()}
    pr=wrapped(lambda:transport.publish(private_payload))
    result["private_publication"]=pr
    # Public TOP1 market data only; no private stock symbols or record content.
    text=json.dumps(result,ensure_ascii=False,allow_nan=False,separators=(",",":"))
    Path("focus_trial_public.json").write_text(text,encoding="utf-8")
    assert json.loads(Path("focus_trial_public.json").read_text())==result
    print("FOCUS_TRIAL_SUMMARY "+json.dumps({k:v for k,v in result.items() if k not in ("public_stocks","market_indexes","public_related_boards")},ensure_ascii=False))
    print("FOCUS_TRIAL_COMPONENTS "+json.dumps({"public":{s:summary(r) for s,r in public_rows.items()},"indexes":{s:{"status":r["status"],"quality":r.get("data",{}).get("quality")} for s,r in indexes.items()},"boards":related},ensure_ascii=False))

if __name__=="__main__":
    main()
