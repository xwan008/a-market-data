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
        "status":"READY","wait_reason":None,"setup_type":"BREAKOUT","entry_zone":[20.1,20.4],
        "max_entry_price":20.4,"entry_trigger":"确认突破之后仅限次日区间内买入",
        "invalidation_price":19.65,"invalidation_rule":"结构失败退出",
        "initial_risk_pct":3.7,"exit_plan":{"failed_setup":"退"},"transmission":"SUPPORTED"}
    return {"schema_version":"trend_buy_result_v2","status":"COMPLETE","trade_date":"2026-10-09",
            "run_id":"synthetic-run","ready":[row],"wait":[],"production_eligible":False}


class ContractTests(unittest.TestCase):
    def test_shadow_projection_and_validation(self):
        h=tool.project(sample(),"testsha",shadow=True)
        self.assertEqual(h["schema_version"],"trend_buy_handoff_v2")
        self.assertTrue(h["shadow"])
        self.assertEqual(len(tool.validate_items(h)),1)
        self.assertNotIn("reasonable_buy_range",h["items"][0])
        self.assertNotIn("low_risk_buy_range",h["items"][0])

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
        h["items"][0]["wait_reason"]="WAIT_MARGIN"
        with self.assertRaisesRegex(ValueError,"invalid_wait_reason"):
            tool.validate_items(h)

    def test_legacy_value_zone_forbidden(self):
        h=tool.project(sample(),"testsha",shadow=True)
        h["items"][0]["low_risk_buy_range"]=[10,12]
        with self.assertRaisesRegex(ValueError,"legacy_value"):
            tool.validate_items(h)

    def test_formal_projection_only_after_gate(self):
        s=sample()
        s["production_eligible"]=True
        h=tool.project(s,"verifiedsha",shadow=False)
        self.assertFalse(h["shadow"])
        self.assertEqual(h["source_formal_blob_sha"],"verifiedsha")


if __name__=="__main__":
    unittest.main()
