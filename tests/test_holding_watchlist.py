import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import holding_watchlist as h

def trade(code, name, action, qty, day):
    return {"createdTime":day+"T15:00:00Z","fields":{
        "股票代码":code,"交易标的":code+" "+name,
        "操作类型":action,"实际成交股数":qty,"交易日期":day}}

class HoldingWatchlistTests(unittest.TestCase):
    def test_only_verified_net_positive_positions(self):
        records=[
            trade("603659","璞泰来","首仓",700,"2026-10-08"),
            trade("603659","璞泰来","清仓",700,"2026-10-12"),
            trade("600988","赤峰黄金","首仓",400,"2026-10-12")]
        self.assertEqual(h.verified_holdings(records),
                         [{"code":"600988","company_name":"赤峰黄金"}])

    def test_duplicate_codes_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"test.json"
            p.write_text(json.dumps({"schema_version":1,
                "result_kind":"a_share_holding_watchlist","stocks":[
                    {"code":"600988","company_name":"赤峰黄金"},
                    {"code":"600988","company_name":"赤峰黄金"}]}))
            with self.assertRaisesRegex(ValueError,"DUPLICATE"):
                h.load_watchlist(p)

    def test_ambiguous_ledger_does_not_change_watchlist(self):
        with self.assertRaisesRegex(ValueError,"SELL_EXCEEDS"):
            h.verified_holdings([trade("600985","淮北矿业","卖出",500,"2026-10-12")])
        with patch.dict("os.environ", {}, clear=True):
            with tempfile.TemporaryDirectory() as folder:
                p=Path(folder)/"watchlist.json"
                p.write_text("original",encoding="utf-8")
                self.assertFalse(h.sync_from_airtable(p))
                self.assertEqual(p.read_text(encoding="utf-8"),"original")

if __name__ == "__main__":
    unittest.main()
