"""Versioned trend buy handoff and shadow isolation regression."""
from __future__ import annotations
import importlib.util
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("trend_handoff",ROOT/"scripts"/"trend_buy_handoff.py")
tool=importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def sample():
    row={"rank":1,"code":"600001","company_name":"合成","trend_name":"示例","industry_code":"S630702",
        "status":"READY","wait_reason":None,"market_state":"趋势确认","trend_state":"T1","setup_type":"BREAKOUT","entry_zone":[20.1,20.4],
        "max_entry_price":20.4,"entry_trigger":"确认突破之后仅限次日区间内买入",
        "invalidation_price":19.65,"invalidation_rule":"结构失败退出",
        "initial_risk_pct":3.7,"exit_plan":{"failed_setup":"退"},"transmission":"SUPPORTED"}
    return {"schema_version":"trend_buy_result_v2","status":"COMPLETE","trade_date":"2026-10-09",
            "run_id":"synthetic-run","ready":[row],"wait":[],"production_eligible":False,
            "top5_by_theme":[{"trend_name":"示例","items":[{"code":"600001"}]}]}


class ContractTests(unittest.TestCase):
    def test_ready_cannot_escape_industry_market_confirmation(self):
        h=tool.project(sample(),"testsha",shadow=True)
        h["items"][0]["market_state"]="候选趋势"
        with self.assertRaisesRegex(ValueError,"ready_requires_confirmed_sector"):
            tool.validate_items(h)

    def test_shadow_projection_and_validation(self):
        h=tool.project(sample(),"testsha",shadow=True)
        self.assertEqual(h["schema_version"],"trend_buy_handoff_v2")
        self.assertTrue(h["shadow"])
        self.assertEqual(len(tool.validate_items(h)),1)
        self.assertTrue(set(h["items"][0]).issubset(tool.ALLOWED_ITEM_FIELDS))

    def test_shadow_must_not_publish_live(self):
        with self.assertRaisesRegex(ValueError,"not_promoted"):
            tool.project(sample(),"testsha",shadow=False)

    def test_ready_without_stop_invalid(self):
        h=tool.project(sample(),"testsha",shadow=True)
        h["items"][0]["invalidation_price"]=None
        with self.assertRaisesRegex(ValueError,"invalid_structure_stop"):
            tool.validate_items(h)

    def test_wait_new_reason_only(self):
        s=sample()
        s["ready"][0]["status"]="WAIT"
        s["ready"][0]["wait_reason"]="WAIT_BREAKOUT"
        s["wait"]=s["ready"]
        s["ready"]=[]
        h=tool.project(s,"testsha",shadow=True)
        self.assertEqual(h["items"][0]["wait_reason"],"WAIT_BREAKOUT")
        self.assertIsNone(h["items"][0]["entry_zone"])
        h["items"][0]["wait_reason"]="WAIT_OTHER"
        with self.assertRaisesRegex(ValueError,"invalid_wait_reason"):
            tool.validate_items(h)

    def test_wait_observes_nearby_ma20_instead_of_remote_breakout(self):
        s=sample()
        row=s["ready"].pop()
        row.update(code="600988",company_name="赤峰黄金",status="WAIT",
                   wait_reason="WAIT_CONFIRMATION",market_state="候选趋势",
                   current_price=41.38,entry_zone=[52.094,53.29],
                   max_entry_price=53.29,invalidation_price=51.21)
        s["wait"]=[row]
        s["top5_by_theme"][0]["items"]=[{
            "code":"600988",
            "reference":{
                "stage":"PRE_TREND_WATCH","setup_mode":"MA20_RECOVERY",
                "reference_trigger_price":42.638,
                "reference_zone":[42.638,43.405],
                "invalidation_price":41.254,
                "estimated_price_risk_pct":4.96,
                "conditional_trigger":"收盘重新站上MA20且承接改善",
                "price_basis":"2026-10-09已完成收盘结构"
            }
        }]
        h=tool.project(s,"testsha",shadow=True)
        x=h["items"][0]
        self.assertEqual(x["status"],"WAIT")
        self.assertIsNone(x["entry_zone"])
        self.assertIsNone(x["invalidation_price"])
        self.assertIsNone(x["exit_plan"])
        self.assertEqual(x["watch_reference"]["reference_zone"],[42.638,43.405])
        self.assertEqual(x["watch_reference"]["reference_trigger_price"],42.638)
        self.assertEqual(len(tool.validate_items(h)),1)
        x["entry_zone"]=[52.094,53.29]
        with self.assertRaisesRegex(ValueError,"wait_has_executable_trade_plan"):
            tool.validate_items(h)
        x["entry_zone"]=None
        x["watch_reference"]["invalidation_price"]=44
        with self.assertRaisesRegex(ValueError,"invalid_watch_stop"):
            tool.validate_items(h)

    def test_undeclared_field_rejected(self):
        h=tool.project(sample(),"testsha",shadow=True)
        h["items"][0]["unexpected_trade_price"]=[10,12]
        with self.assertRaisesRegex(ValueError,"invalid_handoff_item_fields"):
            tool.validate_items(h)

    def test_formal_projection_only_after_gate(self):
        s=sample()
        s["production_eligible"]=True
        h=tool.project(s,"verifiedsha",shadow=False)
        self.assertFalse(h["shadow"])
        self.assertEqual(h["source_formal_blob_sha"],"verifiedsha")


if __name__=="__main__":
    unittest.main()
