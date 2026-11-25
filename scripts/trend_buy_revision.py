"""Publication/recovery guard: a failed research group is not a locked decision."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from functools import lru_cache
import json
import subprocess
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")


@lru_cache(maxsize=4)
def next_exchange_session(day: date):
    # Only needed when the normal next-weekday cutoff has passed (holidays).
    # Never infer a holiday or extend the window if a calendar cannot be verified.
    import akshare as ak
    df = ak.tool_trade_date_hist_sina()
    sessions = sorted({date.fromisoformat(str(x)[:10]) for x in df["trade_date"]})
    if day not in sessions:
        raise ValueError("REFERENCE_SESSION_NOT_IN_CALENDAR")
    future = [x for x in sessions if x > day]
    if not future or (future[0]-day).days > 14:
        raise ValueError("NEXT_SESSION_NOT_VERIFIED")
    return future[0]


def preopen_window(trade_date, now=None):
    """From reference close to strictly before next session 09:30 Beijing."""
    day = date.fromisoformat(trade_date)
    now = (now or datetime.now(TZ)).astimezone(TZ)
    if now < datetime.combine(day,time(15),TZ):
        return False
    earliest = day+timedelta(days=1)
    while earliest.weekday() >= 5:
        earliest += timedelta(days=1)
    if now < datetime.combine(earliest,time(9,30),TZ):
        return True
    # After the earliest possible open, permit only a verified exchange holiday.
    try:
        actual = next_exchange_session(day)
    except Exception:
        return False
    return actual >= earliest and now < datetime.combine(actual,time(9,30),TZ)


def same_session_result(previous, day):
    return previous.get("trade_date")==day and isinstance(previous.get("model_top1_selection"),dict)


def retryable_groups(previous, day, now=None):
    if not same_session_result(previous,day) or not preopen_window(day,now):
        return set()
    return {p["industry_code"] for p in previous["model_top1_selection"]["items"]
            if p.get("status")=="INCOMPLETE" and p.get("top1_code") is None}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


MANUAL_REQUEST_PATH = "research/trend_buy_manual_rerun_request.json"

def authorize_manual_request(previous, request, formal_blob, handoff_blob, now=None):
    """A one-shot user-authorized revision bound to the exact existing pair."""
    now = (now or datetime.now(TZ)).astimezone(TZ)
    if not request or not same_session_result(previous, request.get("trade_date")):
        return None
    if request.get("supersedes_run_id") != previous.get("run_id"):
        return None  # consumed or stale request, not an authorization
    day = request["trade_date"]
    require(request.get("mode") == "USER_AUTHORIZED_FULL_RERUN"
            and request.get("request_id") and request.get("reason"),
            "MANUAL_RERUN_AUTHORIZATION_INVALID")
    require(request.get("supersedes_formal_blob_sha") == formal_blob
            and request.get("supersedes_handoff_blob_sha") == handoff_blob,
            "MANUAL_RERUN_PREVIOUS_PAIR_CHANGED")
    requested = datetime.fromisoformat(request["requested_at"])
    require(requested.tzinfo is not None and requested <= now
            and preopen_window(day, requested) and preopen_window(day, now),
            "MANUAL_RERUN_OUTSIDE_PREOPEN_WINDOW")
    # Unlike routine same-session runs, explicitly verify the exchange calendar.
    try:
        actual = next_exchange_session(date.fromisoformat(day))
    except Exception as exc:
        raise ValueError('MANUAL_RERUN_EXCHANGE_CALENDAR_UNVERIFIED') from exc
    require(now < datetime.combine(actual, time(9,30), TZ),
            "MANUAL_RERUN_NEXT_SESSION_OPEN")
    return request

def active_manual_request(previous, day, root=Path("."), now=None):
    path = root / MANUAL_REQUEST_PATH
    if not path.exists():
        return None
    request = json.loads(path.read_bytes())
    if request.get("trade_date") != day or request.get("supersedes_run_id") != previous.get("run_id"):
        return None
    def blob(path):
        return subprocess.check_output(["git","rev-parse","HEAD:"+path], cwd=root, text=True).strip()
    handoff = json.loads(subprocess.check_output(["git","show","HEAD:research/trend_buy_handoff.json"], cwd=root))
    formal_blob = blob("research/trend_buy_formal_result.json")
    require(handoff.get("source_formal_blob_sha") == formal_blob
            and handoff.get("source_run_id") == previous.get("run_id")
            and handoff.get("trade_date") == day, "MANUAL_RERUN_PRIOR_PAIR_INVALID")
    return authorize_manual_request(previous, request, formal_blob,
                                    blob("research/trend_buy_handoff.json"), now)

def validate_revision(previous, admission, evidence, now=None, manual_request=None):
    """Prior result is consulted only for publication safety, never as ranking input."""
    day=admission["trade_date"]
    require(preopen_window(day,now),"NEXT_SESSION_OPEN_OR_WINDOW_UNVERIFIED")
    if not same_session_result(previous,day):
        return
    if manual_request is not None:
        require(manual_request["trade_date"] == day
                and manual_request["supersedes_run_id"] == previous.get("run_id"),
                "MANUAL_RERUN_AUTHORIZATION_MISMATCH")
        request_id = manual_request["request_id"]
        require(admission.get("manual_rerun_request_id") == request_id
                and evidence.get("manual_rerun_request_id") == request_id,
                "MANUAL_RERUN_FRESH_INPUT_REQUIRED")
        require("fund_flow" in admission, "MANUAL_RERUN_FROZEN_FUND_REQUIRED")
        # Full program admission and model evidence are validated independently
        # by the production gate; no protected group is reused for this mode.
        return
    allowed=retryable_groups(previous,day,now)
    require(allowed,"NO_RETRYABLE_INCOMPLETE_GROUP")
    old=previous["model_top1_selection"]["items"]
    new=evidence["top1_selection"]["items"]
    require([(p["industry_code"],p["candidate_codes"]) for p in old]
            ==[(p["industry_code"],p["candidate_codes"]) for p in new],
            "REVISION_FROZEN_ROSTER_CHANGED")
    require(previous["python_top5_by_industry"]==admission["industries"],
            "REVISION_PYTHON_ADMISSION_CHANGED")
    protected={c for p in old if p["industry_code"] not in allowed for c in p["candidate_codes"]}
    old_reviews={r["code"]:r for r in previous["company_reviews"]}
    new_reviews={r["code"]:r for r in evidence["reviews"]}
    require(all(old_reviews.get(c)==new_reviews.get(c) for c in protected),
            "REVISION_COMPLETED_GROUP_REVIEW_CHANGED")
    for p,q in zip(old,new):
        if p["industry_code"] not in allowed:
            require(p==q,"REVISION_COMPLETED_GROUP_SELECTION_CHANGED")
    require("fund_flow" in admission,"REVISION_FROZEN_FUND_SNAPSHOT_REQUIRED")


def validate_protected_outputs(previous, result, manual_request=None):
    if manual_request is not None:
        require(manual_request['supersedes_run_id'] == previous.get('run_id')
                and manual_request['trade_date'] == result['trade_date'], 'MANUAL_RERUN_AUTHORIZATION_MISMATCH')
        return
    if not same_session_result(previous,result["trade_date"]):
        return
    locked={p["industry_code"] for p in previous["model_top1_selection"]["items"]
            if p["status"]!="INCOMPLETE"}
    old={p["industry_code"]:p for p in previous["top1_decisions"]}
    new={p["industry_code"]:p for p in result["top1_decisions"]}
    require(all(old.get(i)==new.get(i) for i in locked),
            "REVISION_COMPLETED_GROUP_RISK_CHANGED")
