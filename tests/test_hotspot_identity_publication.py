"""Extra hotspot identity-first publication gate, before registry/pair validators."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from validate_hotspot_identity_publication import validate

DAY="2026-10-26"
def mock():
    discovery={
        "schema_version":1,"result_kind":"independent_hotspot_discovery_frozen",
        "trade_date":DAY,"discovery_stage":"FROZEN_BEFORE_HISTORICAL_REVIEW",
        "frozen_at":DAY+"T18:30:00+08:00"}
    identity={
        "schema_version":1,"result_kind":"hotspot_identity_snapshot",
        "trade_date":DAY,"market_scope":"SH_SZ_MAINBOARD_ONLY",
        "discovery_frozen_at":discovery["frozen_at"],
        "resolved_at":DAY+"T18:31:00+08:00",
        "identities":[{"hotspot_name":"人形机器人",
                       "mapping_status":"VERIFIED","board_type":"THEME",
                       "board_code":"886069","concept_code":"886069"}]}
    market={
        "result_kind":"mapped_hotspot_market_evidence","trade_date":DAY,
        "generated_at":DAY+"T18:32:00+08:00",
        "market_scope":"SH_SZ_MAINBOARD_ONLY",
        "may_assign_trend_or_market_state":False,
        "hotspots":[{"hotspot_name":"人形机器人",
                     "evaluation_status":"READY_FOR_INDEPENDENT_STATE_REVIEW",
                     "market_state":None,"trend_state":None}]}
    registry={"trade_date":DAY,"scan_audit":{
        "independent_discovery_frozen_at":discovery["frozen_at"]},
        "trends":[{"trend_name":"人形机器人","board_type":"THEME",
                   "board_code":"886069","trend_state":"T1",
                   "market_state":"候选趋势"}]}
    handoff={"result_kind":"a_share_trend_handoff","trade_date":DAY,
             "generated_at":DAY+"T18:34:00+08:00",
             "source":{"identity_verified_before_state":True},
             "signals":[{"trend_name":"人形机器人","board_type":"THEME",
                         "board_code":"886069","concept_code":"886069",
                         "trend_state":"T1","market_state":"候选趋势"}]}
    return discovery,identity,market,registry,handoff


class PublicationGateTest(unittest.TestCase):
    def test_valid_chronology_and_identity(self):
        records=mock()
        out=validate(*records)
        self.assertEqual(out["signals_verified"],1)

    def test_reject_identity_adjudicated_after_market_state(self):
        records=list(mock())
        records[1]["resolved_at"]=DAY+"T18:36:00+08:00"
        with self.assertRaisesRegex(ValueError,"AFTER_STATE"):
            validate(*records)

    def test_reject_late_market_evidence(self):
        records=list(mock())
        records[2]["generated_at"]=DAY+"T18:35:00+08:00"
        with self.assertRaisesRegex(ValueError,"AFTER_STATE"):
            validate(*records)

    def test_reject_board_code_in_registry_mismatch(self):
        records=list(mock())
        records[3]["trends"][0]["board_code"]="S640701"
        with self.assertRaisesRegex(ValueError,"BOARD_IDENTITY_CHANGED"):
            validate(*records)

    def test_reject_candidate_without_objective_quote_coverage(self):
        records=list(mock())
        records[2]["hotspots"][0]["evaluation_status"]="BLOCKED_QUOTE_COVERAGE_INSUFFICIENT"
        with self.assertRaisesRegex(ValueError,"FACTS_UNVERIFIED"):
            validate(*records)

    def test_reject_tainted_market_state_as_python_output(self):
        records=list(mock())
        records[2]["hotspots"][0]["market_state"]="趋势确认"
        with self.assertRaisesRegex(ValueError,"FACTS_UNVERIFIED"):
            validate(*records)

    def test_allow_independent_discoveries_beyond_actual_handoff(self):
        records=list(mock())
        records[1]["identities"].append({
            "hotspot_name":"仅供研究的其他热点","mapping_status":"MAPPING_UNRESOLVED",
            "board_type":None,"board_code":None})
        records[2]["hotspots"].append({"hotspot_name":"仅供研究的其他热点",
                                        "evaluation_status":"BLOCKED_IDENTITY_UNRESOLVED",
                                        "market_state":None,"trend_state":None})
        result=validate(*records)
        self.assertEqual(result["signals_verified"],1)
        self.assertEqual(result["identity_scope"],2)


if __name__=="__main__":
    unittest.main()
