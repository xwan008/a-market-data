import copy
import datetime as dt
import unittest
from unittest.mock import patch
from scripts import trend_buy_revision as r

DAY="2026-11-25"
def t(v): return dt.datetime.fromisoformat(v+"+08:00")
def pick(ind,status="INCOMPLETE",code=None):
    return {"industry_code":ind,"candidate_codes":[ind+"01"],"status":status,"top1_code":code}
class RevisionTest(unittest.TestCase):
    def setUp(self):
        self.old=[pick("S1"),pick("S2","COMPLETE","S201")]
        self.roster=[{"industry_code":p["industry_code"],"selected_codes":p["candidate_codes"]} for p in self.old]
        self.previous={"trade_date":DAY,"model_top1_selection":{"items":self.old},"python_top5_by_industry":self.roster,
                       "company_reviews":[{"code":"S201","fact":"protected"}],"top1_decisions":[{"industry_code":"S2","top1_code":"S201"}]}
        self.admission={"trade_date":DAY,"industries":self.roster,"fund_flow":{}}
        self.new={"top1_selection":{"items":[pick("S1","COMPLETE","S101"),copy.deepcopy(self.old[1])]},
                  "reviews":[{"code":"S201","fact":"protected"}]}
    def test_before_next_open(self):
        for now in ["2026-11-25T15:00:00","2026-11-25T23:59:00","2026-11-26T09:29:59"]:
            self.assertTrue(r.preopen_window(DAY,t(now)))
        with patch.object(r,"next_exchange_session",return_value=dt.date(2026,11,26)):
            self.assertFalse(r.preopen_window(DAY,t("2026-11-26T09:30:00")))
        self.assertFalse(r.preopen_window(DAY,t("2026-11-25T14:59:59")))
    def test_weekend_and_verified_holiday(self):
        self.assertTrue(r.preopen_window("2026-11-27",t("2026-11-30T09:29:59")))
        with patch.object(r,"next_exchange_session",return_value=dt.date(2026,12,1)):
            self.assertTrue(r.preopen_window("2026-11-27",t("2026-11-30T12:00:00")))
        with patch.object(r,"next_exchange_session",side_effect=ValueError("unavailable")):
            self.assertFalse(r.preopen_window("2026-11-27",t("2026-11-30T12:00:00")))
    def test_incomplete_correction_allowed(self):
        now=t("2026-11-25T20:00:00")
        self.assertEqual(r.retryable_groups(self.previous,DAY,now),{"S1"})
        r.validate_revision(self.previous,self.admission,self.new,now)
    def test_completed_group_immutable(self):
        self.new["top1_selection"]["items"][1]["top1_code"]="wrong"
        with self.assertRaisesRegex(ValueError,"COMPLETED_GROUP_SELECTION"):
            r.validate_revision(self.previous,self.admission,self.new,t("2026-11-25T20:00:00"))
    def test_no_selection_is_final(self):
        self.previous["model_top1_selection"]["items"]=[pick("S1","NO_SELECTION")]
        self.assertFalse(r.retryable_groups(self.previous,DAY,t("2026-11-25T20:00:00")))
    def test_protected_risk(self):
        r.validate_protected_outputs(self.previous,{"trade_date":DAY,"top1_decisions":self.previous["top1_decisions"]})
        with self.assertRaisesRegex(ValueError,"COMPLETED_GROUP_RISK"):
            r.validate_protected_outputs(self.previous,{"trade_date":DAY,"top1_decisions":[{"industry_code":"S2","top1_code":"different"}]})
    def test_roster_and_deadline(self):
        self.new["top1_selection"]["items"][0]["candidate_codes"]=["different"]
        with self.assertRaisesRegex(ValueError,"ROSTER"):
            r.validate_revision(self.previous,self.admission,self.new,t("2026-11-25T20:00:00"))
        with patch.object(r,"next_exchange_session",return_value=dt.date(2026,11,26)):
            with self.assertRaisesRegex(ValueError,"NEXT_SESSION_OPEN"):
                r.validate_revision(self.previous,self.admission,self.new,t("2026-11-26T09:30:00"))
    def test_manual_full_rerun_explicit_pair_and_fresh_ids(self):
        self.previous["run_id"]="old"
        request={"mode":"USER_AUTHORIZED_FULL_RERUN","request_id":"one","reason":"user requested",
                 "trade_date":DAY,"supersedes_run_id":"old","supersedes_formal_blob_sha":"f",
                 "supersedes_handoff_blob_sha":"h","requested_at":"2026-11-25T19:30:00+08:00"}
        now=t("2026-11-25T20:00:00")
        with patch.object(r,"next_exchange_session",return_value=dt.date(2026,11,26)):
            auth=r.authorize_manual_request(self.previous,request,"f","h",now)
            with self.assertRaisesRegex(ValueError,"PREVIOUS_PAIR_CHANGED"):
                r.authorize_manual_request(self.previous,request,"wrong","h",now)
            with self.assertRaisesRegex(ValueError,"OUTSIDE_PREOPEN_WINDOW"):
                r.authorize_manual_request(self.previous,request,"f","h",t("2026-11-26T09:30:00"))
            self.new["top1_selection"]["items"][1]["top1_code"]="changed"
            with self.assertRaisesRegex(ValueError,"FRESH_INPUT_REQUIRED"):
                r.validate_revision(self.previous,self.admission,self.new,now,manual_request=auth)
            self.admission["manual_rerun_request_id"]="one"
            self.new["manual_rerun_request_id"]="one"
            r.validate_revision(self.previous,self.admission,self.new,now,manual_request=auth)
            r.validate_protected_outputs(self.previous,{"trade_date":DAY,"top1_decisions":[]},manual_request=auth)
            with self.assertRaisesRegex(ValueError,"COMPLETED_GROUP_SELECTION"):
                r.validate_revision(self.previous,self.admission,self.new,now)
            self.previous["run_id"]="new"
            self.assertIsNone(r.authorize_manual_request(self.previous,request,"f","h",now))
    def test_manual_calendar_failure_blocks(self):
        self.previous["run_id"]="old"
        request={"mode":"USER_AUTHORIZED_FULL_RERUN","request_id":"one","reason":"user requested",
                 "trade_date":DAY,"supersedes_run_id":"old","supersedes_formal_blob_sha":"f",
                 "supersedes_handoff_blob_sha":"h","requested_at":"2026-11-25T19:30:00+08:00"}
        with patch.object(r,"next_exchange_session",side_effect=ValueError("unavailable")):
            with self.assertRaisesRegex(ValueError,"EXCHANGE_CALENDAR_UNVERIFIED"):
                r.authorize_manual_request(self.previous,request,"f","h",t("2026-11-25T20:00:00"))
