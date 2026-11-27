"""Regression checks for the post-lock entry assessment (offline fixtures)."""
import unittest
from unittest.mock import patch
from scripts import trend_buy_entry_assessment as entry

DAY = "2026-11-30"

def fixture():
    structure = {"data_status":"verified", "data_date":DAY,
                 "current_price":20.98, "ma20":21.368, "ma60":30.8973,
                 "first_effective_resistance":{"price":21.48,"date":"2026-11-24"},
                 "phase_evidence":{"prior_5d_high":21.48}}
    review = {"code":"600105","as_of_date":DAY,"phase":"TRANSITION",
              "mode":"BREAKOUT","confirmation":"PENDING",
              "anchor_source":"first_effective_resistance.price","anchor_price":21.48,
              "entry_basis":"近端压力尚未突破","failure_basis":"突破失败",
              "confirmation_condition":"放量突破并收稳","avoid_condition":"放量滞涨"}
    return structure, review

class EntryAssessmentTest(unittest.TestCase):
    def test_yongding_nearby_pressure_not_ma60(self):
        s, review = fixture()
        row = {"code":"600105","status":"WAIT","wait_reason":"WAIT_CONFIRMATION"}
        with patch.object(entry.engine, "evaluate_candidate", return_value=row):
            result, ref = entry.evaluate({},s,DAY,review)
        self.assertEqual(result["status"],"WAIT")
        self.assertEqual(ref["reference_trigger_price"],21.48)
        self.assertEqual(ref["conditional_trigger"],"放量突破并收稳")
        self.assertIsNone(ref["reference_zone"])
        self.assertIsNone(ref["invalidation_price"])

    def test_invented_or_remote_price_rejected(self):
        s, review = fixture()
        for updates in ({"anchor_price":30.90},
                        {"anchor_source":"ma60","anchor_price":30.8973},
                        {"anchor_price":21.49},
                        {"as_of_date":"2026-11-27"},
                        {"code":"002913"},
                        {"mode":[]}, {"phase":[]}):
            self.assertIsNone(entry.validate_assessment(review | updates,s,"600105",DAY)[0])
        s["first_effective_resistance"]["price"] = 30.90
        self.assertEqual(entry.validate_assessment(review | {"anchor_price":30.90},s,"600105",DAY),
                         (None,"ENTRY_ANCHOR_TOO_DISTANT"))

    def test_model_cannot_upgrade_independent_wait(self):
        s, review = fixture()
        s["breakout_level"]=21.48
        review.update(anchor_source="breakout_level",confirmation="CONFIRMED")
        row={"code":"600105","status":"WAIT","wait_reason":"WAIT_CONFIRMATION"}
        with patch.object(entry.engine,"evaluate_candidate",return_value=row):
            result,_=entry.evaluate({},s,DAY,review)
        self.assertEqual(result["status"],"WAIT")

    def test_ready_requires_matching_confirmed_model_anchor(self):
        s, review = fixture()
        s["breakout_level"]=21.48
        base={"code":"600105","status":"READY","setup_type":"BREAKOUT",
              "setup_stop_evidence":{"anchor_price":21.48}}
        with patch.object(entry.engine,"evaluate_candidate",return_value=base.copy()):
            result,ref=entry.evaluate({},s,DAY,review)
        self.assertEqual(result["status"],"WAIT")
        self.assertIsNone(ref["reference_zone"])
        review.update(confirmation="CONFIRMED",anchor_source="breakout_level")
        with patch.object(entry.engine,"evaluate_candidate",return_value=base.copy()):
            result,ref=entry.evaluate({},s,DAY,review)
        self.assertEqual(result["status"],"READY")
        self.assertIsNone(ref)

    def test_missing_review_has_no_fallback(self):
        s,_=fixture()
        base={"code":"600105","status":"READY","setup_type":"BREAKOUT"}
        with patch.object(entry.engine,"evaluate_candidate",return_value=base):
            row,ref=entry.evaluate({},s,DAY,None)
        self.assertEqual(row["status"],"WAIT")
        self.assertIsNone(ref["reference_trigger_price"])
        self.assertEqual(ref["entry_assessment_verification"],"ENTRY_ASSESSMENT_MISSING")

    def test_actual_engine_yongding_wait(self):
        s,review=fixture()
        s.update(history_points=180,low_risk_eligible=True,trend_phase="TRANSITION")
        c={"code":"600105","asof_price":20.98,"transmission":"SUPPORTED",
           "theme_link_verified":True,"market_state":"趋势确认"}
        row,ref=entry.evaluate(c,s,DAY,review)
        self.assertEqual(row["status"],"WAIT")
        self.assertEqual(ref["reference_trigger_price"],21.48)

    def test_actual_engine_confirmed_breakout_preserves_risk_math(self):
        s,review=fixture()
        s.update(history_points=180,low_risk_eligible=True,trend_phase="REACCELERATING",
                 current_price=21.15,ma20=20.6,ma60=20.5,
                 structure_type="breakout",breakout_confirmed=True,breakout_level=21.0,
                 first_effective_resistance={"price":24.0,"date":"2026-11-24"},
                 distance_to_ma20_pct=2.67,chase_risk="low")
        review.update(phase="REACCELERATING",confirmation="CONFIRMED",
                      anchor_source="breakout_level",anchor_price=21.0)
        c={"code":"600105","asof_price":21.15,"transmission":"SUPPORTED",
           "theme_link_verified":True,"market_state":"趋势确认"}
        row,ref=entry.evaluate(c,s,DAY,review)
        self.assertEqual(row["status"],"READY")
        self.assertLess(row["invalidation_price"],row["entry_zone"][0])
        self.assertLessEqual(row["initial_risk_pct"],entry.engine.MAX_ENTRY_RISK_PCT)
        self.assertGreaterEqual(row["upside_to_resistance_R"],entry.engine.MIN_UPSIDE_R)
        self.assertIsNone(ref)

    def test_old_date_uses_legacy_path(self):
        base={"code":"600105","status":"WAIT"}
        with patch.object(entry.engine,"evaluate_candidate",return_value=base), \
             patch.object(entry.engine,"early_watch_reference",return_value={"legacy":True}):
            row,ref=entry.evaluate({},None,"2026-11-27",None)
        self.assertEqual(row,base)
        self.assertEqual(ref,{"legacy":True})

if __name__ == "__main__":
    unittest.main()
