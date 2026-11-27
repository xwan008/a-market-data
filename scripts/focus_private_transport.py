"""Private, idempotent Airtable snapshot transport; no trade or holdings writes."""
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
import urllib.error
import time

CHUNK=20000

def encode(payload):
    text=json.dumps(payload,ensure_ascii=False,allow_nan=False,separators=(",",":"))
    digest=hashlib.sha256(text.encode("utf-8")).hexdigest()
    parts=[text[i:i+CHUNK] for i in range(0,len(text),CHUNK)]
    return text,digest,parts

def api(method,params=None,body=None):
    token=os.environ.get("AIRTABLE_TOKEN")
    base=os.environ.get("AIRTABLE_BASE_ID")
    table=os.environ.get("FOCUS_OUTPUT_TABLE_ID")
    if not all((token,base,table)):
        raise ValueError("PRIVATE_OUTPUT_NOT_CONFIGURED")
    url="https://api.airtable.com/v0/"+base+"/"+table
    if params:
        url+="?"+urllib.parse.urlencode(params)
    for attempt in range(2):
        try:
            req=urllib.request.Request(url,method=method,headers={"Authorization":"Bearer "+token,"Content-Type":"application/json"},
                data=None if body is None else json.dumps(body,ensure_ascii=False,allow_nan=False).encode("utf-8"))
            with urllib.request.urlopen(req,timeout=12) as res:
                return json.load(res)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429,500,502,503,504) or attempt:
                raise ValueError("PRIVATE_HTTP_"+str(exc.code)) from None
        except (TimeoutError,urllib.error.URLError):
            if attempt:
                raise ValueError("PRIVATE_NETWORK") from None
        time.sleep(1)

def row(key,run,day,part,text,digest):
    return {"fields":{"记录键":key,"运行ID":run,"交易日":day,"区段":part,"内容":text,"SHA256":digest}}

def upsert(rows):
    for i in range(0,len(rows),10):
        response=api("PATCH",body={"performUpsert":{"fieldsToMergeOn":["记录键"]},"records":rows[i:i+10]})
        if len(response.get("records",[]))!=len(rows[i:i+10]):
            raise ValueError("PRIVATE_WRITE_COUNT")

def read_run(run):
    if not re.fullmatch(r"\d+(?:-\d+)?",run):
        raise ValueError("PRIVATE_RUN_ID")
    out={}; seen=set(); offset=None
    for _ in range(50):
        params=[("pageSize","100"),("filterByFormula",'{运行ID}="'+run+'"')]
        if offset:
            params.append(("offset",offset))
        response=api("GET",params=params)
        if not isinstance(response.get("records"),list):
            raise ValueError("PRIVATE_READ_SCHEMA")
        for record in response["records"]:
            f=record["fields"]
            part=f.get("区段")
            if f.get("运行ID")!=run or part in out:
                raise ValueError("PRIVATE_READ_DUPLICATE")
            out[part]=f
        offset=response.get("offset")
        if not offset:
            return out
        if offset in seen:
            raise ValueError("PRIVATE_READ_PAGINATION")
        seen.add(offset)
    raise ValueError("PRIVATE_READ_PAGINATION")

def verify(rows,run):
    manifest=json.loads(rows["manifest"]["内容"])
    count=manifest["part_count"]
    expected={"manifest"}|{f"{i:04d}" for i in range(count)}
    if set(rows)!=expected:
        raise ValueError("PRIVATE_READ_PARTS")
    if any(x.get("SHA256")!=manifest["sha256"] or x.get("运行ID")!=run for x in rows.values()):
        raise ValueError("PRIVATE_READ_METADATA")
    text="".join(rows[f"{i:04d}"]["内容"] for i in range(count))
    if hashlib.sha256(text.encode("utf-8")).hexdigest()!=manifest["sha256"]:
        raise ValueError("PRIVATE_READ_HASH")
    return json.loads(text),manifest

def publish(payload):
    run=str(payload["run_id"])
    if not re.fullmatch(r"\d+(?:-\d+)?",run):
        raise ValueError("PRIVATE_RUN_ID")
    day=payload["trade_date"]
    text,digest,parts=encode(payload)
    rows=[row(run+":"+f"{i:04d}",run,day,f"{i:04d}",part,digest) for i,part in enumerate(parts)]
    upsert(rows)
    manifest={"run_id":run,"trade_date":day,"part_count":len(parts),"sha256":digest}
    upsert([row(run+":manifest",run,day,"manifest",json.dumps(manifest,ensure_ascii=False,separators=(",",":")),digest)])
    recovered,actual=verify(read_run(run),run)
    if recovered!=payload or actual!=manifest:
        raise ValueError("PRIVATE_READBACK_MISMATCH")
    return {"status":"PUBLISHED_AND_VERIFIED","part_count":len(parts),"sha256":digest}
