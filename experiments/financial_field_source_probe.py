#!/usr/bin/env python3
"""One-time, read-only probe for publicly available Eastmoney core earnings fields.

No write to data/latest.json, no formal buy recommendations or quote refresh.
Print field keys and non-null coverage only, without dumping full reports.
"""
import json
from collections import Counter
import requests
URL="https://datacenter-web.eastmoney.com/api/data/v1/get"
HEADERS={"User-Agent":"Mozilla/5.0","Referer":"https://quote.eastmoney.com/"}
SELECT=("KCFJCXSYJLR","KCFJCXSYJLRTZ","DEDUCT_PARENT_NETPROFIT",
        "DEDUCT_PARENT_NETPROFIT_YOY","EPSKCJB","DEDUCT_BASIC_EPS",
        "PARENTNETPROFIT","PARENTNETPROFITTZ","NOTICE_DATE","REPORTDATE")

def query(report, period, code=None):
    filt=f"(REPORTDATE='{period}')"
    if code:filt+=f"(SECURITY_CODE='{code}')"
    r=requests.get(URL,params={
        "sortColumns":"REPORTDATE,SECURITY_CODE","sortTypes":"-1,1",
        "pageSize":100,"pageNumber":1,
        "reportName":report,"columns":"ALL","filter":filt,
        "source":"WEB","client":"WEB"},
        headers=HEADERS,timeout=25)
    r.raise_for_status()
    payload=r.json()
    result=payload.get("result") or {}
    rows=result.get("data") or []
    return {"success":payload.get("success"),
            "pages":result.get("pages"),"count":len(rows),
            "field_keys":sorted(rows[0]) if rows else [],
            "field_coverage":{f:sum(item.get(f) is not None for item in rows)
                              for f in SELECT},
            "sample":[{"SECURITY_CODE":item.get("SECURITY_CODE"),
                        "selected":{f:item.get(f) for f in SELECT if item.get(f) is not None}}
                       for item in rows[:2]]}

if __name__=="__main__":
    reports=[
        ("RPT_LICO_FN_CPD","2026-09-30",None),
        ("RPT_LICO_FN_CPD","2025-09-30",None),
        ("RPT_LICO_FN_CPD","2026-09-30","000506"),
    ]
    for report,period,code in reports:
        try:
            result=query(report,period,code)
            print("CORE_PROFIT_SOURCE_PROBE "+json.dumps({
                "report":report,"period":period,"code":code,
                **result},ensure_ascii=False))
        except Exception as ex:
            print("CORE_PROFIT_SOURCE_PROBE_ERROR "+json.dumps({
                "report":report,"period":period,"code":code,
                "error":type(ex).__name__+":"+str(ex)[:300]},ensure_ascii=False))
