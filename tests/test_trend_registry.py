import copy
import unittest
from scripts import trend_registry as engine
from scripts import validate_trend_state_migrations as gate
from scripts import validate_trend_publication_pair as pair

SHA="a"*40
OLD="2026-10-16"
DAY="2026-10-19"

def theme(name="A",status="候选趋势",first=OLD):
    return {"trend_name":name,"episode_id":engine.episode_key(name,first),
            "first_seen_trade_date":first,"trend_state":"T1","market_state":status,
            "lifecycle_status":"有效","industry_codes":["S630601"],
            "industry_names":["风电整机"],"in_new_position_priority":False,
            "state_history":[{"trade_date":first,"from":None,"to":status}],
            "supporting_evidence":[{"finding":"有来源可核实的产业及市场证据","source":"https://example.org"}]}

def fact(d,direction="COUNTER",impact="NORMAL",date=DAY):
    return {"dimension":d,"direction":direction,"impact":impact,"trade_date":date,
            "source":"https://example.org/report","finding":"有独立可靠来源且经本轮核对的行情和产业证据"}

def fixture():
    before={"schema_version":2,"result_kind":"a_share_trend_registry",
            "trade_date":OLD,"status":"COMPLETE","trends":[theme()]}
    after=copy.deepcopy(before)
    after["trade_date"]=DAY
    after["scan_audit"]={"full_market_scan_completed":True,"state_migration_gate":{
       "mode":"full_close","previous_registry_blob_sha":SHA,
       "previous_registry_trade_date":OLD,"current_trade_date":DAY,
       "reviews":[{"episode_id":"A#"+OLD,"decision":"HOLD",
           "previous_market_state":"候选趋势","proposed_market_state":"候选趋势",
           "previous_trend_state":"T1","proposed_trend_state":"T1",
           "reason":"当前证据支持保留候选，尚无充分新反证","evidence":[]}],
       "exits":[]}}
    return before,after

def exit_theme(after,facts=None):
    after["trends"]=[]
    audit=after["scan_audit"]["state_migration_gate"]
    audit["reviews"]=[]
    audit["exits"]=[{"episode_id":"A#"+OLD,"decision":"EXIT",
        "previous_market_state":"候选趋势","proposed_market_state":"高潮/衰退",
        "previous_trend_state":"T1","reason":"行情结构走弱和广度收缩经独立证据核实，进入衰退并退出有效跟踪",
        "evidence":facts if facts is not None else [
            fact("MARKET_STRUCTURE",impact="STRUCTURAL"),fact("MARKET_BREADTH")]}]

def add_future_audit(after):
    """Prospective research metadata; old published days stay immutable."""
    day = after["trade_date"]
    for row in after["trends"]:
        row["confirmation_audit"] = {
            "asof_trade_date": day, "market_environment": "NORMAL",
            "market_environment_reason": "当日市场风险偏好保持正常，尚无异常宽基资金证据",
            "market_environment_source": "data/research/sector_discovery_audit.json",
            "driver_type": "COMMODITY" if row.get("trend_basis") == "COMMODITY"
                           else "INDUSTRIAL_GROWTH",
            "discovery_basis": "CONTINUING_STRUCTURE",
            "catalyst_kind": "SUSTAINED_DRIVER",
            "catalyst_fact": "产销及订单基础事实已在当日交易截止前得到验证",
            "catalyst_source": "https://example.org/official",
            "catalyst_available_at": day + "T16:00:00+08:00",
            "strongest_counter": "产业订单变化存在不确定性且需持续检查",
            "decision_reason": "综合实际价格结构与产业资料核对后保留状态",
            "decision_state": row["market_state"],
            "core_industry_codes": row["industry_codes"],
            "specific_blocker": "当前仍有未兑现的真实订单及趋势结构证据需跟踪",
            "first_sufficient_evidence_trade_date": day,
        }



def surge_session(day, supported=False):
    state = "SUPPORTED" if supported else "ASSESSED"
    dimensions = {
        label: {"status": state,
                "finding": "本交易日独立复核了真实市场行情、产业证据与关键反证信息",
                "source": "data/research/sector_discovery_audit.json"}
        for label in engine.SURGE_DIMENSIONS
    }
    dimensions["funding_strength"].update(
        measurement_basis="PRICE_VOLUME_PROXY",
        observation_window="近5个完整交易日")
    dimensions["breadth"].update(sample_size=6 if supported else None,
                                 advancing_count=5 if supported else None)
    return {"trade_date": day, "dimensions": dimensions}


def surge_audit(day, market="观察", discovery="ONE_DAY_SURGE"):
    return {
        "asof_trade_date": day, "market_environment": "MIXED",
        "market_environment_reason": "市场出现不同板块轮动，需要甄别宽基资金影响",
        "market_environment_source": "data/research/sector_discovery_audit.json",
        "driver_type": "INDUSTRIAL_GROWTH",
        "discovery_basis": discovery,
        "catalyst_kind": "EVENT",
        "catalyst_fact": "存在已经核验的政策与产业新闻但盈利传导仍待核对",
        "catalyst_source": "https://example.org/catalyst",
        "catalyst_available_at": day + "T16:00:00+08:00",
        "strongest_counter": "目前核心行业仍存在较强资金分歧与持续性未知风险",
        "decision_reason": "按收盘前可得客观数据评估核心三级行业状态",
        "decision_state": market, "core_industry_codes": ["S630601"],
        "specific_blocker": "板块资金强度与产业订单仍有具体待验证事实",
        "first_sufficient_evidence_trade_date": day
    }



class TrendRegistryTests(unittest.TestCase):
    def _today_revision(self):
        from datetime import datetime
        today = datetime.now(engine.BEIJING).date().isoformat()
        before, after = fixture()
        before = copy.deepcopy(after)
        before["trade_date"] = today
        # Use a same-day earlier timestamp so the regression is time-of-day independent.
        before["generated_at"] = today + "T00:00:00+08:00"
        before["scan_audit"]["state_migration_gate"]["current_trade_date"] = today
        before["scan_audit"]["state_migration_gate"]["previous_registry_trade_date"] = OLD
        add_future_audit(before)
        before["trends"][0]["industry_assessments"] = [{
            "industry_code": "S630601", "industry_name": "风电整机",
            "benefit_level": "CORE", "market_state": "候选趋势",
            "evidence_trade_date": today,
            "benefit_reason": "核心产品受益链具有可核验的真实经营事实",
            "market_reason": "现有连续市场结构尚不足以完成趋势确认"}]
        after = copy.deepcopy(before)
        now = datetime.now(engine.BEIJING).isoformat(timespec="microseconds")
        after["generated_at"] = now
        row = after["trends"][0]
        row["market_state"] = "观察"
        row["change_reason"] = "重新核对行业真实受益和市场广度，原候选证据不充分，改为观察持续跟踪"
        row["confirmation_audit"]["decision_state"] = "观察"
        row["confirmation_audit"]["decision_reason"] = row["change_reason"]
        row["state_history"].append({
            "trade_date": today, "from": "候选趋势", "to": "观察",
            "event": "same_day_revision", "reason": row["change_reason"]})
        after["scan_audit"]["same_day_revisions"] = [{
            "previous_registry_blob_sha": SHA,
            "previous_generated_at": before["generated_at"],
            "revised_at": now,
            "reason": "复核后确认原候选中的受益链与市场广度证据尚不充分，修正原当日结论",
            "changes": [{
                "episode_id": row["episode_id"], "from": "候选趋势", "to": "观察",
                "reason": row["change_reason"],
                "evidence": [
                    fact("MARKET_STRUCTURE", "COUNTER", "NORMAL", today),
                    fact("INDUSTRY_FUNDAMENTALS", "COUNTER", "NORMAL", today)
                ]
            }]
        }]
        return before, after

    def test_same_day_evidence_backed_republication_allowed(self):
        before, after = self._today_revision()
        self.assertEqual(gate.validate(before, after, SHA), [])
        self.assertEqual(pair.validate(after, {
            "schema_version": 1, "result_kind": "a_share_trend_handoff",
            "trade_date": before["trade_date"], "signals": []}), [])

    def test_same_day_requires_revision_provenance(self):
        before, after = self._today_revision()
        after["scan_audit"].pop("same_day_revisions")
        self.assertIn("same_day_revision_audit_missing_or_rewritten",
                      gate.validate(before, after, SHA))

    def test_same_day_does_not_rewrite_original_close_or_reset_episode(self):
        before, after = self._today_revision()
        after["trends"][0]["first_seen_trade_date"] = after["trade_date"]
        self.assertIn("A#"+OLD+":same_day_identity_changed",
                      gate.validate(before, after, SHA))
        before, after = self._today_revision()
        after["scan_audit"]["state_migration_gate"]["previous_registry_trade_date"] = DAY
        self.assertIn("same_day_original_close_audit_rewritten",
                      gate.validate(before, after, SHA))

    def test_same_day_block_invalid_evidence_and_wrong_sha(self):
        before, after = self._today_revision()
        after["scan_audit"]["same_day_revisions"][-1]["changes"][0]["evidence"] = []
        self.assertIn("A#"+OLD+":same_day_revision_evidence_insufficient",
                      gate.validate(before, after, SHA))
        before, after = self._today_revision()
        self.assertIn("same_day_revision_baseline_sha_mismatch",
                      gate.validate(before, after, "b"*40))

    def test_same_day_cannot_be_backdated(self):
        before, after = self._today_revision()
        before["trade_date"] = "2026-10-19"
        after["trade_date"] = "2026-10-19"
        self.assertIn("same_day_revision_only_allowed_on_trade_date",
                      gate.validate(before, after, SHA))

    def test_new_one_day_surge_requires_visible_stage(self):
        row = theme("相对强势异动", "观察", "2026-10-28")
        row["confirmation_audit"] = surge_audit("2026-10-28")
        self.assertIn(row["episode_id"] + ":d123_stage_missing",
                      engine._d123_stage_errors(row, None, "2026-10-28"))

    def test_formal_registry_has_no_fake_d3_continuation(self):
        import json
        from pathlib import Path
        registry = json.loads((Path(__file__).resolve().parents[1] /
                               "research/trend_registry.json").read_text())
        if registry["trade_date"] != "2026-10-27":
            self.skipTest("historical regression only for the corrected close")
        assert len(registry["trends"]) == 5
        for row in registry["trends"]:
            self.assertIn(row["d123_stage"], {"D1", "D2", "D3"})
            self.assertIn(row["d123_decision"], {"PENDING", "CONFIRMED", "NOT_CONFIRMED"})
            if row["d123_stage"] == "D3":
                self.assertIn(row["d123_decision"], {"CONFIRMED", "NOT_CONFIRMED"})
        robot = next(x for x in registry["trends"] if x["trend_name"] == "工业自动化/机器人")
        self.assertEqual((robot["d123_stage"], robot["d123_decision"],
                          robot["d123_decision_trade_date"]),
                         ("D3", "NOT_CONFIRMED", "2026-10-22"))

    def test_d2_can_directly_confirm_and_close(self):
        first = theme("日内相对强势", "观察", "2026-10-27")
        first.update(d123_stage="D1", d123_trigger_trade_date="2026-10-27",
                     d123_decision="PENDING")
        second = copy.deepcopy(first)
        second.update(d123_stage="D2", market_state="趋势确认",
                      d123_decision="CONFIRMED",
                      d123_decision_trade_date="2026-10-28")
        self.assertEqual(engine._d123_stage_errors(second, first, "2026-10-28"), [])
        later = copy.deepcopy(second)
        later["market_state"] = "候选趋势"
        self.assertEqual(engine._d123_stage_errors(later, second, "2026-10-29"), [])
        later["d123_stage"] = "D3"
        self.assertIn(later["episode_id"] + ":d123_closed_stage_changed",
                      engine._d123_stage_errors(later, second, "2026-10-29"))

    def test_legacy_d3_verdict_requires_actual_published_state(self):
        row = theme("旧方向", "候选趋势", "2026-10-20")
        row["state_history"].extend([
            {"trade_date": "2026-10-21", "from": "候选趋势", "to": "候选趋势"},
            {"trade_date": "2026-10-22", "from": "候选趋势", "to": "候选趋势"}])
        row.update(d123_stage="D3", d123_trigger_trade_date="2026-10-20",
                   d123_decision="NOT_CONFIRMED",
                   d123_decision_trade_date="2026-10-22")
        self.assertIn(row["episode_id"] + ":d123_legacy_backfill_provenance_missing",
                      engine._d123_stage_errors(row, None, "2026-10-27"))
        row["d123_backfill_audit"] = {
            "asof_trade_date": "2026-10-27",
            "basis": "FORMAL_REGISTRY_SESSION_HISTORY",
            "first_formal_trade_date": "2026-10-20",
            "source": "research/trend_registry.json",
            "review_gap": "D3当日未有单独的完整八维矩阵，结论从正式候选状态核验",
            "d3_published_market_state": "候选趋势",
            "d3_registry_commit_sha": "a" * 40}
        self.assertEqual(engine._d123_stage_errors(row, None, "2026-10-27"), [])
        row["d123_decision"] = "UNVERIFIED"
        self.assertIn(row["episode_id"] + ":d123_decision_invalid",
                      engine._d123_stage_errors(row, None, "2026-10-27"))
        row["d123_decision"] = "NOT_CONFIRMED"
        row["d123_backfill_audit"]["d3_published_market_state"] = "趋势确认"
        self.assertIn(row["episode_id"] + ":d123_legacy_d3_verdict_unsubstantiated",
                      engine._d123_stage_errors(row, None, "2026-10-27"))

    def test_d123_stage_display_and_daily_progression(self):
        item = theme("电机", "观察", "2026-10-27")
        item.update(d123_stage="D1", d123_trigger_trade_date="2026-10-27",
                    d123_decision="PENDING")
        self.assertEqual(engine._d123_stage_errors(item, None, "2026-10-27"), [])
        second = copy.deepcopy(item)
        second["d123_stage"] = "D2"
        self.assertEqual(engine._d123_stage_errors(second, item, "2026-10-28"), [])
        third = copy.deepcopy(second)
        third["d123_stage"] = "D3"
        self.assertIn(third["episode_id"] + ":d123_final_decision_missing",
                      engine._d123_stage_errors(third, second, "2026-10-29"))
        third["d123_decision"] = "NOT_CONFIRMED"
        third["d123_decision_trade_date"] = "2026-10-29"
        self.assertEqual(engine._d123_stage_errors(third, second, "2026-10-29"), [])
        fourth = copy.deepcopy(third)
        self.assertEqual(engine._d123_stage_errors(fourth, third, "2026-10-30"), [])
        fourth["d123_stage"] = "POST_D3"
        self.assertIn(third["episode_id"] + ":d123_stage_invalid",
                      engine._d123_stage_errors(fourth, third, "2026-10-30"))
        second["d123_stage"] = "D1"
        self.assertIn(item["episode_id"] + ":d123_progression_invalid",
                      engine._d123_stage_errors(second, item, "2026-10-28"))

    def test_hold_pass(self):
        before,after=fixture()
        self.assertEqual(gate.validate(before,after,SHA),[])

    def test_old_schema_and_cutover_mode_rejected(self):
        before,after=fixture()
        before["schema_version"]=1
        self.assertIn("schema_version_mismatch",gate.validate(before,after,SHA))
        before["schema_version"]=2
        after["scan_audit"]["state_migration_gate"]["mode"]="v2_cutover"
        self.assertIn("invalid_close_mode",gate.validate(before,after,SHA))

    def test_evidence_backed_exit_no_archive(self):
        before,after=fixture()
        exit_theme(after)
        self.assertEqual(gate.validate(before,after,SHA),[])

    def test_unreviewed_exit_is_silent_delete(self):
        before,after=fixture()
        after["trends"]=[]
        self.assertIn("exit_review_coverage_mismatch",gate.validate(before,after,SHA))
        self.assertIn("A#"+OLD+":active_silently_removed",gate.validate(before,after,SHA))

    def test_exit_requires_market_counter_plus_breadth(self):
        before,after=fixture()
        exit_theme(after,[])
        self.assertIn("A#"+OLD+":exit_without_independent_market_counter",gate.validate(before,after,SHA))
        exit_theme(after,[fact("MARKET_STRUCTURE",impact="STRUCTURAL")])
        self.assertIn("A#"+OLD+":exit_without_independent_market_counter",gate.validate(before,after,SHA))
        exit_theme(after,[fact("MARKET_STRUCTURE",impact="STRUCTURAL",date=OLD),fact("MARKET_BREADTH",date=OLD)])
        self.assertIn("A#"+OLD+":exit_without_independent_market_counter",gate.validate(before,after,SHA))

    def test_future_evidence_and_missing_reason_rejected(self):
        before,after=fixture()
        exit_theme(after,[fact("MARKET_STRUCTURE",impact="STRUCTURAL",date="2026-10-20"),fact("MARKET_BREADTH")])
        self.assertIn("A#"+OLD+":exit_evidence_invalid",gate.validate(before,after,SHA))
        exit_theme(after)
        after["scan_audit"]["state_migration_gate"]["exits"][0]["reason"]=""
        self.assertIn("A#"+OLD+":exit_reason_missing",gate.validate(before,after,SHA))

    def test_exit_identity_and_target_rejected(self):
        before,after=fixture()
        exit_theme(after)
        x=after["scan_audit"]["state_migration_gate"]["exits"][0]
        x["previous_trend_state"]="T2"
        x["proposed_market_state"]="趋势确认"
        err=gate.validate(before,after,SHA)
        self.assertIn("A#"+OLD+":exit_review_state_mismatch",err)
        self.assertIn("A#"+OLD+":exit_target_not_inactive",err)

    def test_duplicate_exit_blocked(self):
        before,after=fixture()
        exit_theme(after)
        x=after["scan_audit"]["state_migration_gate"]["exits"][0]
        after["scan_audit"]["state_migration_gate"]["exits"].append(copy.deepcopy(x))
        self.assertIn("duplicate_exit_episode_id",gate.validate(before,after,SHA))

    def test_incomplete_scan_blocks_exits(self):
        before,after=fixture()
        exit_theme(after)
        after["scan_audit"]["full_market_scan_completed"]=False
        self.assertIn("full_market_scan_incomplete",gate.validate(before,after,SHA))

    def test_observation_continues_in_same_registry_and_cycle(self):
        before,after=fixture()
        after["trends"][0]["market_state"]="观察"
        after["trends"][0]["state_history"].append(
            {"trade_date":DAY,"from":"候选趋势","to":"观察"})
        review=after["scan_audit"]["state_migration_gate"]["reviews"][0]
        review.update(decision="CHANGE",proposed_market_state="观察",
                      reason="三级行业市场结构发生真实调整，观察继续跟踪",
                      evidence=[fact("MARKET_STRUCTURE",impact="STRUCTURAL"),
                                fact("MARKET_BREADTH")])
        self.assertEqual(gate.validate(before,after,SHA),[])
        after["trends"][0]["in_new_position_priority"]=True
        self.assertIn("A#"+OLD+":observation_in_priority",gate.validate(before,after,SHA))

    def test_history_immutable(self):
        before,after=fixture()
        after["trends"][0]["state_history"]=[]
        self.assertIn("A#"+OLD+":history_rewritten",gate.validate(before,after,SHA))

    def test_confirmation_requires_structure_breadth_relative(self):
        before,after=fixture()
        t=after["trends"][0]
        t["market_state"]="趋势确认"
        t["state_history"].append({"trade_date":DAY,"from":"候选趋势","to":"趋势确认"})
        r=after["scan_audit"]["state_migration_gate"]["reviews"][0]
        r.update(decision="CHANGE",proposed_market_state="趋势确认")
        r["evidence"]=[fact("MARKET_STRUCTURE","SUPPORT","STRUCTURAL"),fact("MARKET_BREADTH","SUPPORT")]
        self.assertIn("A#"+OLD+":market_change_without_independent_evidence",gate.validate(before,after,SHA))
        r["evidence"].append(fact("RELATIVE_STRENGTH","SUPPORT"))
        self.assertEqual(gate.validate(before,after,SHA),[])

    def test_industry_downgrade_requires_primary_counter(self):
        before,after=fixture()
        t=after["trends"][0]
        t["trend_state"]="T0"
        t["state_history"].append({"trade_date":DAY,"from":"T1","to":"T0"})
        r=after["scan_audit"]["state_migration_gate"]["reviews"][0]
        r.update(decision="CHANGE",proposed_trend_state="T0")
        r["evidence"]=[fact("MARKET_STRUCTURE",impact="STRUCTURAL")]
        self.assertIn("A#"+OLD+":industry_downgrade_without_primary_counter",gate.validate(before,after,SHA))
        r["evidence"].append(fact("INDUSTRY_FUNDAMENTALS",impact="STRUCTURAL"))
        self.assertEqual(gate.validate(before,after,SHA),[])

    def test_future_sw3_routing_requires_independent_benefit_and_market_evidence(self):
        before, after = fixture()
        after["trade_date"] = "2026-10-27"
        after["scan_audit"]["state_migration_gate"]["current_trade_date"] = "2026-10-27"
        add_future_audit(after)
        self.assertIn("A#" + OLD + ":sw3_assessments_missing",
                      gate.validate(before, after, SHA))
        current = after["trends"][0]
        current["industry_assessments"] = [{
            "industry_code": "S630601", "industry_name": "风电整机",
            "market_state": "候选趋势", "benefit_level": "CORE",
            "evidence_trade_date": "2026-10-27",
            "benefit_reason": "经核实具有直接相关的订单和利润传导关系",
            "market_reason": "本行业独立的强弱结构仍具备有效价格承接证据"
        }]
        self.assertEqual(gate.validate(before, after, SHA), [])
        # Peripheral/related industries may legitimately remain candidates.
        current["industry_assessments"][0]["benefit_level"] = "RELATED"
        self.assertEqual(gate.validate(before, after, SHA), [])
        # A confirmed SW3, however, must have a CORE/DIRECT benefit.
        current["industry_assessments"][0]["market_state"] = "趋势确认"
        self.assertIn("A#" + OLD + ":S630601:confirmed_without_direct_benefit",
                      gate.validate(before, after, SHA))

    def test_confirmation_requires_confirmed_core_sw3_not_entire_theme(self):
        before, after = fixture()
        after["trade_date"] = "2026-10-27"
        after["scan_audit"]["state_migration_gate"]["current_trade_date"] = "2026-10-27"
        trend = after["trends"][0]
        trend["market_state"] = "趋势确认"
        trend["state_history"].append({"trade_date": "2026-10-27",
                                       "from": "候选趋势", "to": "趋势确认"})
        review = after["scan_audit"]["state_migration_gate"]["reviews"][0]
        add_future_audit(after)
        trend["confirmation_audit"]["decision_state"] = "趋势确认"
        review.update(decision="CHANGE", proposed_market_state="趋势确认",
                      evidence=[fact("MARKET_STRUCTURE", "SUPPORT", "STRUCTURAL", "2026-10-27"),
                                fact("MARKET_BREADTH", "SUPPORT", "NORMAL", "2026-10-27"),
                                fact("RELATIVE_STRENGTH", "SUPPORT", "NORMAL", "2026-10-27")])
        trend["industry_assessments"] = [{
            "industry_code": "S630601", "industry_name": "风电整机",
            "market_state": "候选趋势", "benefit_level": "CORE",
            "evidence_trade_date": "2026-10-27",
            "benefit_reason": "经核实独立受益于真实产能订单和利润传导",
            "market_reason": "本三级行业处于结构改善且尚未突破的阶段"
        }]
        self.assertIn("A#" + OLD + ":confirmed_without_confirmed_sw3",
                      gate.validate(before, after, SHA))
        trend["industry_assessments"][0]["market_state"] = "趋势确认"
        self.assertEqual(gate.validate(before, after, SHA), [])

    def test_commodity_confirmation_without_a_share_breadth(self):
        before,after=fixture()
        row=after["trends"][0]
        row["trend_basis"]="COMMODITY"
        row["commodity_anchor"]={"instrument":"Brent futures",
            "trade_date":DAY,"price_basis":"2026-10-19 settlement",
            "source":"https://example.org/oil","trend_reason":"多日商品价格结构与原油供需证据交叉确认"}
        row["market_state"]="趋势确认"
        row["state_history"].append({"trade_date":DAY,"from":"候选趋势","to":"趋势确认"})
        review=after["scan_audit"]["state_migration_gate"]["reviews"][0]
        review.update(decision="CHANGE",proposed_market_state="趋势确认",
                      evidence=[fact("MARKET_STRUCTURE","SUPPORT","STRUCTURAL"),
                                fact("COMMODITY_ANCHOR","SUPPORT","STRUCTURAL"),
                                fact("SUPPLY_DEMAND","SUPPORT")])
        self.assertEqual(gate.validate(before,after,SHA),[])

    def test_observation_can_be_previous_and_current_state(self):
        before,after=fixture()
        before["trends"][0]["market_state"]="观察"
        after["trends"][0]["market_state"]="观察"
        review=after["scan_audit"]["state_migration_gate"]["reviews"][0]
        review["previous_market_state"]="观察"
        review["proposed_market_state"]="观察"
        self.assertEqual(gate.validate(before,after,SHA),[])

    def test_new_candidate_starts_new_cycle(self):
        before,after=fixture()
        after["trends"].append(theme("N",first=DAY))
        self.assertEqual(gate.validate(before,after,SHA),[])
        after["trends"][-1]["state_history"]=[]
        self.assertIn("N#"+DAY+":new_cycle_identity_or_date_invalid",gate.validate(before,after,SHA))

    def test_new_confirmation_requires_fresh_evidence(self):
        before,after=fixture()
        after["trends"].append(theme("N","趋势确认",DAY))
        self.assertIn("N#"+DAY+":new_confirmation_without_independent_evidence",gate.validate(before,after,SHA))
        after["scan_audit"]["state_migration_gate"]["new_confirmation_reviews"]=[{
            "episode_id":"N#"+DAY,"evidence":[fact("MARKET_STRUCTURE","SUPPORT","STRUCTURAL"),
                fact("MARKET_BREADTH","SUPPORT"),fact("RELATIVE_STRENGTH","SUPPORT")]}]
        self.assertEqual(gate.validate(before,after,SHA),[])

    def test_active_name_cannot_reset_episode(self):
        before,after=fixture()
        exit_theme(after)
        after["trends"].append(theme("A",first=DAY))
        self.assertIn("A#"+DAY+":active_cycle_restarted",gate.validate(before,after,SHA))

    def test_sha_snapshot_quality(self):
        before,after=fixture()
        self.assertIn("baseline_sha_or_date_not_frozen",gate.validate(before,after,"b"*40))
        self.assertIn("invalid_previous_blob_sha",gate.validate(before,after,"bad"))
        self.assertIn("snapshot_invalid",gate.validate(before,after,SHA,snapshot={"trade_date":OLD}))

    def test_future_catalyst_audit_cutoff_and_surge_cannot_confirm(self):
        before, after = fixture()
        after["trade_date"] = "2026-10-27"
        after["scan_audit"]["state_migration_gate"]["current_trade_date"] = "2026-10-27"
        add_future_audit(after)
        after["trends"][0]["industry_assessments"] = [{
            "industry_code": "S630601", "industry_name": "风电整机",
            "benefit_level": "CORE", "market_state": "候选趋势",
            "evidence_trade_date": "2026-10-27",
            "benefit_reason": "经过公告和产品对照具备直接经营受益证据",
            "market_reason": "自身多日结构尚未独立确认且仍需复核"
        }]
        self.assertEqual(gate.validate(before, after, SHA), [])
        audit = after["trends"][0]["confirmation_audit"]
        audit["catalyst_available_at"] = "2026-10-28T01:00:00+08:00"
        self.assertIn("A#" + OLD + ":catalyst_not_available_at_close",
                      gate.validate(before, after, SHA))
        audit["catalyst_available_at"] = "2026-10-27T16:00:00+08:00"
        audit["discovery_basis"] = "ONE_DAY_SURGE"
        self.assertIn("A#" + OLD + ":surge_alone_cannot_progress",
                      gate.validate(before, after, SHA))
        audit["discovery_basis"] = "CONTINUING_STRUCTURE"
        audit["market_environment_source"] = ""
        self.assertIn("A#" + OLD + ":environment_source_invalid",
                      gate.validate(before, after, SHA))
        audit["market_environment_source"] = "data/research/sector_discovery_audit.json"
        after["trends"][0]["in_new_position_priority"] = True
        self.assertIn("A#" + OLD + ":only_confirmed_priority",
                      gate.validate(before, after, SHA))

    def test_new_surges_stay_observation_only(self):
        before, after = fixture()
        after["trade_date"] = "2026-10-27"
        after["scan_audit"]["state_migration_gate"]["current_trade_date"] = "2026-10-27"
        new = theme("爆发行业", "观察", "2026-10-27")
        after["trends"].append(new)
        add_future_audit(after)
        new["confirmation_audit"]["discovery_basis"] = "ONE_DAY_SURGE"
        new["surge_followup"] = {
            "trigger_trade_date": "2026-10-27",
            "sessions": [surge_session("2026-10-27")],
            "decision": "PENDING", "decision_trade_date": None
        }
        self.assertIn("A#" + OLD + ":sw3_assessments_missing",
                      gate.validate(before, after, SHA))
        after["trends"][0]["industry_assessments"] = [{
            "industry_code": "S630601", "industry_name": "风电整机",
            "benefit_level": "CORE", "market_state": "候选趋势",
            "evidence_trade_date": "2026-10-27",
            "benefit_reason": "真实经营资料足以证明该行业存在直接受益",
            "market_reason": "多日股价结构仍在形成还没有完整确认"
        }]
        self.assertEqual(gate.validate(before, after, SHA), [])
        new["market_state"] = "候选趋势"
        new["confirmation_audit"]["decision_state"] = "候选趋势"
        self.assertIn(new["episode_id"] + ":one_day_surge_must_observe",
                      gate.validate(before, after, SHA))

    def test_commodity_downgrade_requires_commodity_not_equity_counter(self):
        before, after = fixture()
        after["trade_date"] = "2026-10-27"
        after["scan_audit"]["state_migration_gate"]["current_trade_date"] = "2026-10-27"
        anchor = {"instrument": "Brent future", "price_basis": "published settlement",
                  "trade_date": "2026-10-26", "source": "https://example.org/oil",
                  "trend_reason": "期货自身有效结构且报价日期与合约已经核验"}
        for theme_row in (before["trends"][0], after["trends"][0]):
            theme_row["trend_basis"] = "COMMODITY"
            theme_row["commodity_anchor"] = copy.deepcopy(anchor)
        after["trends"][0]["market_state"] = "观察"
        after["trends"][0]["state_history"].append(
            {"trade_date": "2026-10-27", "from": "候选趋势", "to": "观察"})
        review = after["scan_audit"]["state_migration_gate"]["reviews"][0]
        review.update(decision="CHANGE", proposed_market_state="观察",
                      evidence=[fact("MARKET_STRUCTURE", date="2026-10-27",
                                     impact="STRUCTURAL"),
                                fact("MARKET_BREADTH", date="2026-10-27")])
        add_future_audit(after)
        self.assertIn("A#" + OLD + ":market_change_without_independent_evidence",
                      gate.validate(before, after, SHA))
        review["evidence"].append(fact("COMMODITY_ANCHOR", impact="STRUCTURAL",
                                       date="2026-10-27"))
        self.assertEqual(gate.validate(before, after, SHA), [])

    def test_independent_confirmed_sw3_downgrade_needs_same_code_counter(self):
        before, after = fixture()
        after["trade_date"] = "2026-10-27"
        after["scan_audit"]["state_migration_gate"]["current_trade_date"] = "2026-10-27"
        assessment = {"industry_code": "S630601", "industry_name": "风电整机",
                      "benefit_level": "CORE", "market_state": "趋势确认",
                      "evidence_trade_date": "2026-10-27",
                      "benefit_reason": "确认该产品真实收入传导而非仅是题材概念",
                      "market_reason": "行业已有多日相对强度与有效承接"}
        before["trends"][0]["industry_assessments"] = [dict(assessment)]
        after["trends"][0]["industry_assessments"] = [dict(assessment,
                                                         market_state="候选趋势")]
        add_future_audit(after)
        self.assertIn("A#" + OLD + ":S630601:core_downgrade_without_own_counter",
                      gate.validate(before, after, SHA))
        review = after["scan_audit"]["state_migration_gate"]["reviews"][0]
        review["evidence"] = [dict(fact("MARKET_STRUCTURE", impact="STRUCTURAL",
                                        date="2026-10-27"), industry_code="S630601")]
        self.assertEqual(gate.validate(before, after, SHA), [])

    def test_single_day_surge_requires_first_review_with_full_matrix(self):
        obj = theme("新主题", "观察", "2026-10-27")
        obj["confirmation_audit"] = surge_audit("2026-10-27")
        missing = engine._surge_review_errors(obj, None, "2026-10-27")
        self.assertIn(obj["episode_id"] + ":surge_followup_missing", missing)
        obj["surge_followup"] = {
            "trigger_trade_date": "2026-10-27",
            "sessions": [surge_session("2026-10-27")],
            "decision": "PENDING", "decision_trade_date": None}
        self.assertEqual(engine._surge_review_errors(obj, None, "2026-10-27"), [])
        obj["surge_followup"]["sessions"][0]["dimensions"].pop("breadth")
        self.assertIn(obj["episode_id"] + ":surge_evidence_matrix_incomplete",
                      engine._surge_review_errors(obj, None, "2026-10-27"))

    def test_second_session_can_confirm_only_with_complete_independent_evidence(self):
        old = theme("机器人", "观察", "2026-10-27")
        old["confirmation_audit"] = surge_audit("2026-10-27")
        old["surge_followup"] = {
            "trigger_trade_date": "2026-10-27",
            "sessions": [surge_session("2026-10-27")],
            "decision": "PENDING", "decision_trade_date": None}
        now = copy.deepcopy(old)
        now["confirmation_audit"] = surge_audit(
            "2026-10-28", market="趋势确认", discovery="CONTINUING_STRUCTURE")
        now["market_state"] = "趋势确认"
        now["surge_followup"]["sessions"].append(surge_session("2026-10-28"))
        now["surge_followup"]["decision"] = "CONFIRMED"
        now["surge_followup"]["decision_trade_date"] = "2026-10-28"
        errs = engine._surge_review_errors(now, old, "2026-10-28")
        self.assertIn(now["episode_id"] + ":breadth:surge_confirmed_without_support", errs)
        now["surge_followup"]["sessions"][-1] = surge_session("2026-10-28", True)
        self.assertEqual(engine._surge_review_errors(now, old, "2026-10-28"), [])

    def test_money_strength_needs_provenance_and_breadth_needs_sample(self):
        item = theme("传感器", "观察", "2026-10-27")
        item["confirmation_audit"] = surge_audit("2026-10-27")
        item["surge_followup"] = {
            "trigger_trade_date": "2026-10-27",
            "sessions": [surge_session("2026-10-27", supported=True)],
            "decision": "PENDING", "decision_trade_date": None}
        evidence = item["surge_followup"]["sessions"][0]["dimensions"]
        evidence["funding_strength"]["measurement_basis"] = "UNVERIFIED"
        evidence["breadth"]["advancing_count"] = 9
        problems = engine._surge_review_errors(item, None, "2026-10-27")
        self.assertIn(item["episode_id"] + ":funding_strength_basis_invalid", problems)
        self.assertIn(item["episode_id"] + ":breadth_sample_invalid", problems)

    def test_etf_market_event_cannot_confirm_without_independent_sector_support(self):
        first = theme("科技链", "观察", "2026-10-27")
        first["confirmation_audit"] = surge_audit("2026-10-27")
        first["surge_followup"] = {
            "trigger_trade_date": "2026-10-27",
            "sessions": [surge_session("2026-10-27")],
            "decision": "PENDING", "decision_trade_date": None}
        current = copy.deepcopy(first)
        current["market_state"] = "趋势确认"
        current["confirmation_audit"] = surge_audit(
            "2026-10-28", market="趋势确认", discovery="CONTINUING_STRUCTURE")
        current["confirmation_audit"]["market_environment"] = "EVENT_LIQUIDITY_SHOCK"
        current["surge_followup"]["sessions"].append(surge_session("2026-10-28", True))
        current["surge_followup"]["decision"] = "CONFIRMED"
        current["surge_followup"]["decision_trade_date"] = "2026-10-28"
        self.assertIn(first["episode_id"] + ":surge_event_without_independent_sector_evidence",
                      engine._surge_review_errors(current, first, "2026-10-28"))
        current["surge_followup"]["event_independent_evidence"] = {
            "status": "SUPPORTED",
            "finding": "行业在资金冲击之前已经存在独立供需和核心价格结构",
            "source": "https://example.org/research"}
        self.assertEqual(engine._surge_review_errors(current, first, "2026-10-28"), [])

    def test_third_session_requires_yes_or_no_not_forced_confirmation(self):
        prior = theme("文化传媒", "观察", "2026-10-27")
        prior["confirmation_audit"] = surge_audit("2026-10-28", discovery="CONTINUING_STRUCTURE")
        prior["surge_followup"] = {
            "trigger_trade_date": "2026-10-27",
            "sessions": [surge_session("2026-10-27"), surge_session("2026-10-28")],
            "decision": "PENDING", "decision_trade_date": None}
        now = copy.deepcopy(prior)
        now["confirmation_audit"] = surge_audit("2026-10-29", discovery="CONTINUING_STRUCTURE")
        now["surge_followup"]["sessions"].append(surge_session("2026-10-29"))
        self.assertIn(now["episode_id"] + ":surge_third_close_decision_missing",
                      engine._surge_review_errors(now, prior, "2026-10-29"))
        now["surge_followup"]["decision"] = "NOT_CONFIRMED"
        now["surge_followup"]["decision_trade_date"] = "2026-10-29"
        self.assertEqual(engine._surge_review_errors(now, prior, "2026-10-29"), [])

        # Later new evidence can upgrade without rewriting the initial 3-session decision.
        later = copy.deepcopy(now)
        later["market_state"] = "趋势确认"
        later["confirmation_audit"] = surge_audit(
            "2026-11-02", market="趋势确认", discovery="CONTINUING_STRUCTURE")
        self.assertEqual(engine._surge_review_errors(later, now, "2026-11-02"), [])
        later["surge_followup"]["decision"] = "CONFIRMED"
        self.assertIn(now["episode_id"] + ":surge_final_judgement_rewritten",
                      engine._surge_review_errors(later, now, "2026-11-02"))

    def test_review_session_cannot_be_skipped_or_backdated(self):
        old = theme("测试异动", "观察", "2026-10-27")
        old["surge_followup"] = {
            "trigger_trade_date": "2026-10-27",
            "sessions": [surge_session("2026-10-27")],
            "decision": "PENDING", "decision_trade_date": None}
        current = copy.deepcopy(old)
        current["confirmation_audit"] = surge_audit("2026-10-28")
        self.assertIn(old["episode_id"] + ":surge_review_not_updated_this_close",
                      engine._surge_review_errors(current, old, "2026-10-28"))
        current["surge_followup"]["sessions"].append(surge_session("2026-10-27"))
        self.assertIn(old["episode_id"] + ":surge_review_trade_date_mismatch",
                      engine._surge_review_errors(current, old, "2026-10-28"))

    def test_new_d1_can_confirm_only_with_independent_structure_and_trigger(self):
        day = "2026-10-28"
        row = theme("新周期独立趋势", "趋势确认", day)
        row["confirmation_audit"] = surge_audit(
            day, market="趋势确认", discovery="CONTINUING_STRUCTURE")
        row.update(initial_discovery_basis="CONTINUING_STRUCTURE",
                   d123_stage="D1", d123_trigger_trade_date=day,
                   d123_decision="CONFIRMED", d123_decision_trade_date=day,
                   d123_trigger_evidence=fact(
                       "MARKET_STRUCTURE", "SUPPORT", "STRUCTURAL", day))
        self.assertEqual(engine._d123_stage_errors(row, None, day), [])
        row["initial_discovery_basis"] = "ONE_DAY_SURGE"
        self.assertIn(row["episode_id"] + ":d123_day_one_surge_cannot_confirm",
                      engine._d123_stage_errors(row, None, day))
        row["initial_discovery_basis"] = "CONTINUING_STRUCTURE"
        row.pop("d123_trigger_evidence")
        self.assertIn(row["episode_id"] + ":fresh_d1_trigger_missing",
                      engine._d123_stage_errors(row, None, day))

    def _d3_timeout_case(self, legacy=False):
        day = "2026-10-29"
        previous = theme("复核到期行业", "候选趋势", "2026-10-27")
        previous.update(d123_stage="D2", d123_decision="PENDING",
                        d123_trigger_trade_date="2026-10-27",
                        d123_decision_trade_date=None)
        verdict_day = day
        if legacy:
            previous.update(d123_stage="D3", d123_decision="NOT_CONFIRMED",
                            d123_decision_trade_date="2026-10-28")
            verdict_day = "2026-10-28"
        final = {
            "d123_stage": "D3", "d123_decision": "NOT_CONFIRMED",
            "d123_decision_trade_date": verdict_day,
            "d123_trigger_trade_date": "2026-10-27",
            "market_state": "候选趋势",
            "confirmation_audit": surge_audit(
                day, market="候选趋势", discovery="CONTINUING_STRUCTURE"),
            "dimensions": surge_session(day)["dimensions"],
        }
        review = {
            "exit_reason_code": "D3_NOT_CONFIRMED",
            "proposed_market_state": "失效",
            "d123_final_audit": final,
        }
        return previous, review, day

    def test_d3_timeout_is_audited_exit_without_fake_market_breakdown(self):
        previous, review, day = self._d3_timeout_case()
        self.assertEqual(engine._d123_terminal_exit_errors(review, previous, day), [])
        review["d123_final_audit"]["dimensions"].pop("breadth")
        self.assertIn(previous["episode_id"] + ":d3_timeout_eight_dimensions_missing",
                      engine._d123_terminal_exit_errors(review, previous, day))
        review["d123_final_audit"]["dimensions"] = surge_session(day)["dimensions"]
        review["d123_final_audit"]["d123_decision"] = "PENDING"
        self.assertIn(previous["episode_id"] + ":d3_timeout_verdict_invalid",
                      engine._d123_terminal_exit_errors(review, previous, day))

    def test_legacy_d3_not_confirmed_exits_without_changing_old_verdict(self):
        previous, review, day = self._d3_timeout_case(legacy=True)
        self.assertEqual(engine._d123_terminal_exit_errors(review, previous, day), [])
        review["d123_final_audit"]["d123_decision_trade_date"] = day
        self.assertIn(previous["episode_id"] + ":d3_timeout_legacy_verdict_rewritten",
                      engine._d123_terminal_exit_errors(review, previous, day))

    def test_full_gate_allows_d3_timeout_but_blocks_unreviewed_exit(self):
        before, after = fixture()
        before["trade_date"] = "2026-10-28"
        after["trade_date"] = "2026-10-29"
        gate_data = after["scan_audit"]["state_migration_gate"]
        gate_data["previous_registry_trade_date"] = "2026-10-28"
        gate_data["current_trade_date"] = "2026-10-29"
        prior, review, day = self._d3_timeout_case()
        before["trends"] = [prior]
        after["trends"] = []
        gate_data["reviews"] = []
        gate_data["exits"] = [{
            "episode_id": prior["episode_id"], "decision": "EXIT",
            "previous_market_state": "候选趋势",
            "proposed_market_state": "失效",
            "previous_trend_state": "T1",
            "reason": "本轮第三次真实有效收盘已经到期，但结构与产业证据不足确认",
            "evidence": [],
            **review
        }]
        self.assertEqual(gate.validate(before, after, SHA), [])
        gate_data["exits"][0].pop("d123_final_audit")
        self.assertIn(prior["episode_id"] + ":d3_timeout_final_audit_missing",
                      gate.validate(before, after, SHA))
        gate_data["exits"][0]["exit_reason_code"] = "MARKET_INVALIDATED"
        self.assertIn(prior["episode_id"] + ":exit_without_independent_market_counter",
                      gate.validate(before, after, SHA))

    def test_d3_not_confirmed_cannot_stay_in_current_registry(self):
        before, after = fixture()
        before["trade_date"] = "2026-10-28"
        after["trade_date"] = "2026-10-29"
        gate_data = after["scan_audit"]["state_migration_gate"]
        gate_data["previous_registry_trade_date"] = "2026-10-28"
        gate_data["current_trade_date"] = "2026-10-29"
        prior, _, day = self._d3_timeout_case(legacy=True)
        before["trends"] = [prior]
        after["trends"] = [copy.deepcopy(prior)]
        gate_data["reviews"][0].update(
            episode_id=prior["episode_id"])
        add_future_audit(after)
        after["trends"][0]["industry_assessments"] = [{
            "industry_code": "S630601", "industry_name": "风电整机",
            "benefit_level": "CORE", "market_state": "候选趋势",
            "evidence_trade_date": day,
            "benefit_reason": "本轮产业供应链真实受益存在可核实的经营数据",
            "market_reason": "本轮市场结构仍不足以确认，不能继续保留过期研究"}]
        self.assertIn(prior["episode_id"] + ":d3_not_confirmed_must_exit",
                      gate.validate(before, after, SHA))

    def test_handoff_contract_stable(self):
        before,after=fixture()
        after["trends"][0]["in_new_position_priority"]=True
        handoff={"schema_version":1,"result_kind":"a_share_trend_handoff","trade_date":DAY,
           "signals":[{"rank":1,"trend_name":"A","market_state":"候选趋势","trend_state":"T1",
                       "industry_codes":["S630601"],"industry_names":["风电整机"]}]}
        self.assertEqual(pair.validate(after,handoff),[])
        after["trends"][0]["market_state"]="观察"
        self.assertIn("observation_in_priority",pair.validate(after,handoff))

if __name__=="__main__":
    unittest.main()
