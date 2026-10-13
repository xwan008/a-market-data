import test from 'node:test';
import assert from 'node:assert/strict';
import {selectTodayLeader} from '../src/todayLeader.js';
const day='2026-10-13',status={monitor:'OK',buyHandoff:'OK',airtable:'OK'};
const point=(n,pct,quality='READY')=>({scan_at:day+'T'+({1:'09:50',2:'10:45',3:'13:35',4:'14:30'}[n])+':00+08:00',price:10,change_pct:pct,data_quality:quality});

test('only rank in the most recent intraday slot, not an older spike',()=>{
 const r=selectTodayLeader({tradeDate:day,status,portfolio:{positions:[]},
  buy:{trade_date:'2026-10-12',items:[{code:'000001'},{code:'000002'}]},
  monitor:{result_kind:'a_share_intraday_monitor_state',trade_date:day,stock_history:{
   '000001':[point(1,9)],'000002':[point(4,-1)]}}});
 assert.equal(r.leader.code,'000002');assert.equal(r.coveredCount,1);assert.equal(r.poolCount,2);assert.equal(r.slot,4);
});
test('merge holdings and handoff once, score independent holding points against verified previous close',()=>{
 const r=selectTodayLeader({tradeDate:day,status,
  portfolio:{positions:[{code:'600001',name:'持仓甲',verified:true,shares:100},{code:'600002',verified:true,shares:0}]},
  buy:{trade_date:'2026-10-12',items:[{code:'600001',company_name:'持仓甲',trend_name:'黄金'},{code:'600003'}]},
  monitor:{result_kind:'a_share_intraday_monitor_state',trade_date:day,stock_history:{'600003':[point(4,1)]}},
  holdingSnapshot:{result_kind:'a_share_intraday_market_snapshot',trade_date:day,validation:{status:'passed'},captured_at:day+'T14:32:00+08:00',
   holding_stocks:{'600001':{code:'600001',source_scope:'holding_watchlist',confidence:'high',quote_time:day+'T14:31:00+08:00',prev_close:10,price:10.3}}},
  holdingCharts:{result_kind:'a_share_holding_charts',trade_date:day,stocks:{
   '600001':{intraday_points:[{slot:1,scan_at:day+'T09:48:00+08:00',price:10},{slot:4,scan_at:day+'T14:30:00+08:00',price:10.3}]}}}});
 assert.equal(r.poolCount,2);assert.equal(r.leader.code,'600001');
 assert.equal(r.leader.inHandoff,true);assert.equal(r.leader.inHolding,true);
 assert.deepEqual(r.leader.scans.map(p=>p.slot),[1,4]);
 assert.ok(Math.abs(r.leader.last.change_pct-3)<1e-9);
});
test('reject stale dates, unverified holdings, bad previous closes and degraded scans',()=>{
 const r=selectTodayLeader({tradeDate:day,status,buy:{trade_date:'2026-10-12',items:[]},
  portfolio:{positions:[{code:'600001',verified:true,shares:100},{code:'600002',verified:false,shares:100}]},
  holdingSnapshot:{result_kind:'a_share_intraday_market_snapshot',trade_date:day,validation:{status:'passed'},holding_stocks:{
   '600001':{code:'600001',prev_close:null,price:10,quote_time:day+'T09:50:00+08:00',source_scope:'holding_watchlist',confidence:'high'}}},
  holdingCharts:{result_kind:'a_share_holding_charts',trade_date:day,stocks:{
   '600001':{intraday_points:[{slot:1,scan_at:day+'T09:50:00+08:00',price:10}]}}}});
 assert.equal(r.poolCount,1);assert.equal(r.leader,null);
 const m=selectTodayLeader({tradeDate:day,status,portfolio:{positions:[]},buy:{trade_date:'2026-10-12',items:[{code:'000001'}]},
  monitor:{result_kind:'a_share_intraday_monitor_state',trade_date:day,stock_history:{'000001':[point(1,1),point(2,20,'DEGRADED'),point(4,2)]}}});
 assert.deepEqual(m.leader.scans.map(p=>p.slot),[1,4]);
 const stale=selectTodayLeader({tradeDate:day,status,portfolio:{positions:[]},buy:{trade_date:'2026-10-12',items:[{code:'000001'}]},
  monitor:{result_kind:'a_share_intraday_monitor_state',trade_date:'2026-10-12',stock_history:{'000001':[point(4,2)]}}});
 assert.equal(stale.leader,null);
});
