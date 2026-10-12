"""Independent holding quote watchlist. The formal trend-buy handoff is unchanged."""
from __future__ import annotations
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
WATCHLIST_PATH = ROOT / "research" / "holding_watchlist.json"

def load_watchlist(path: Path = WATCHLIST_PATH) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("result_kind") != "a_share_holding_watchlist" or payload.get("schema_version") != 1:
        raise ValueError("HOLDING_WATCHLIST_SCHEMA_INVALID")
    stocks = payload.get("stocks")
    if not isinstance(stocks, list):
        raise ValueError("HOLDING_WATCHLIST_STOCKS_MISSING")
    seen = set()
    result = []
    for item in stocks:
        if not isinstance(item, dict):
            raise ValueError("HOLDING_WATCHLIST_ITEM_INVALID")
        code, name = item.get("code"), item.get("company_name")
        if not isinstance(code, str) or not re.fullmatch(r"[0-9]{6}", code):
            raise ValueError("HOLDING_WATCHLIST_CODE_INVALID")
        if not isinstance(name, str) or not name.strip() or len(name) > 80 or code in seen:
            raise ValueError("HOLDING_WATCHLIST_NAME_OR_DUPLICATE_INVALID")
        seen.add(code)
        result.append({"code": code, "company_name": name.strip()})
    return result

def verified_holdings(records: list[dict]) -> list[dict]:
    """Sum actual trades; on any ambiguous ledger fail rather than inventing holdings."""
    by_code = {}
    for record in records:
        fields = record.get("fields") or {}
        code = str(fields.get("股票代码") or "").strip()
        if not re.fullmatch(r"[0-9]{6}", code):
            raise ValueError("AIRTABLE_TRADE_CODE_INVALID")
        by_code.setdefault(code, []).append(record)
    positions = []
    for code, trades in by_code.items():
        trades.sort(key=lambda row: (
            str(row.get("fields", {}).get("交易日期") or row.get("createdTime") or ""),
            str(row.get("createdTime") or "")
        ))
        shares, names = 0, []
        for trade in trades:
            fields = trade["fields"]
            action = fields.get("操作类型") or ""
            qty = fields.get("实际成交股数")
            day = fields.get("交易日期")
            if not day or isinstance(qty, bool) or not isinstance(qty, (int,float)) or int(qty) != qty or qty <= 0:
                raise ValueError(f"AIRTABLE_TRADE_AMBIGUOUS:{code}")
            if any(term in action for term in ("清仓","卖出","减仓","止盈","止损")):
                if qty > shares:
                    raise ValueError(f"AIRTABLE_SELL_EXCEEDS_HOLDINGS:{code}")
                shares -= int(qty)
            elif any(term in action for term in ("买入","加仓","建仓","首仓","补仓")):
                shares += int(qty)
            else:
                raise ValueError(f"AIRTABLE_TRADE_ACTION_UNKNOWN:{code}")
            if fields.get("交易标的"):
                names.append(str(fields["交易标的"]))
        if shares > 0:
            company_name = re.sub(r"^" + re.escape(code) + r"\s*", "", names[-1] if names else code).strip() or code
            positions.append({"code": code, "company_name": company_name})
    return sorted(positions, key=lambda item: item["code"])

def sync_from_airtable(path: Path = WATCHLIST_PATH) -> bool:
    """On configured actions, refresh the code/name-only list before price collection."""
    token = os.environ.get("AIRTABLE_TOKEN")
    base = os.environ.get("AIRTABLE_BASE_ID")
    table = os.environ.get("AIRTABLE_TABLE_ID")
    if not (token and base and table):
        print("HOLDING_SYNC_NOT_CONFIGURED: using checked-in watchlist")
        return False
    if not re.fullmatch(r"app[A-Za-z0-9]{14}", base) or not re.fullmatch(r"tbl[A-Za-z0-9]{14}", table):
        raise ValueError("AIRTABLE_SETTINGS_INVALID")
    records, seen, offset = [], set(), None
    while True:
        params = [("pageSize","100")] + [("fields[]", field) for field in
            ("股票代码","交易标的","操作类型","实际成交股数","交易日期")]
        if offset:
            params.append(("offset",offset))
        url = f"https://api.airtable.com/v0/{base}/{table}?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={"Authorization":"Bearer " + token})
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.load(response)
        if not isinstance(payload.get("records"), list):
            raise ValueError("AIRTABLE_RECORDS_INVALID")
        records.extend(payload["records"])
        offset = payload.get("offset")
        if not offset:
            break
        if offset in seen or len(seen) >= 50:
            raise ValueError("AIRTABLE_PAGINATION_UNSAFE")
        seen.add(offset)
    positions = verified_holdings(records)
    payload = {
        "schema_version":1,
        "result_kind":"a_share_holding_watchlist",
        "as_of_date":datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat(),
        "source":"airtable_trade_records_verified_net_positions",
        "stocks":positions
    }
    path.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("HOLDING_SYNC_OK: %d symbols" % len(positions))
    return True

if __name__ == "__main__":
    import sys
    if sys.argv[1:] != ["--sync-airtable"]:
        raise SystemExit("usage: python scripts/holding_watchlist.py --sync-airtable")
    sync_from_airtable()
