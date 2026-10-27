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


class TrendRegistryTests(unittest.TestCase):
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
        current["industry_assessments"][0]["benefit_level"] = "RELATED"
        self.assertIn("A#" + OLD + ":S630601:sw3_independent_evidence_missing",
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
