import test from 'node:test';
import assert from 'node:assert/strict';
import {summarizeTrades,extractRecords,latestMonitorRecords,fixed,validSnapshots,snapshotChange,rankedTrendRows,seriesDirection,statusTone,trendEvents,archivedDays,assessHoldingRisk,evaluateExitCondition,normalizeRiskPlans,attachRiskPlans,selectRepresentativeStocks} from '../src/model.js';

function row(code,kind,qty,price,day,extras={}) {return {'股票代码':code,'操作类型':kind,'实际成交股数':qty,'价格（元）':price,'交易日期':day,'交易标的': '测试股票',...extras};}
test('买入、加仓、卖出移动加权成本正确',()=>{
  const a=summarizeTrades([row('603659','首仓',500,22.1,'2026-10-08'),row('603659','加仓',200,21.94,'2026-10-09'),row('603659','卖出',300,22.30,'2026-10-10')]);
  assert.equal(a.positions[0].shares,400);
  assert.ok(Math.abs(a.positions[0].avgCost - (500*22.1+200*21.94)/700)<0.001);
});
test('同日买卖顺序模糊，不计算估算成本',()=>{
 const p=summarizeTrades([row('000001','买入',400,10,'2026-10-08'),row('000001','卖出',100,11,'2026-10-08')]).positions[0];
 assert.equal(p.shares,300);assert.equal(p.avgCost,null);
});
test('股数冲突需标待核验，不能推断已清仓',()=>{
 const p=summarizeTrades([row('000001','买入',100,10,'2026-10-08'),row('000001','卖出',150,11,'2026-10-09')]).positions[0];
 assert.equal(p.verified,false);assert.equal(p.shares,null);
});
test('不认识的操作和缺日期均不推断空仓',()=>{
 const p=summarizeTrades([row('000002','未知',100,10,'2026-10-08')]).positions[0];assert.equal(p.verified,false);
});
test('完整清仓不列为在持',()=>{
 const p=summarizeTrades([row('000001','买入',100,10,'2026-10-08'),row('000001','卖出',100,11,'2026-10-09')]);assert.equal(p.positions.length,0);
});
test('记录代码不合规不作为持仓',()=>{const p=summarizeTrades([row('abc','买入',100,10,'2026-10-08')]);assert.equal(p.invalidCount,1)});
test('监测字典及数组结构都可展开',()=>{assert.deepEqual(extractRecords({gold:{current_state:'正常'}}),[{current_state:'正常',key:'gold'}]);assert.equal(extractRecords([{a:1}]).length,1)});
test('缺失价格不产生假数值',()=>assert.equal(fixed(null),'—'));

test('重复监测仅呈现最新轮次',()=>{const rows=latestMonitorRecords({'固态电池':[{current_state:'分歧'},{current_state:'修复'}]});assert.equal(rows.length,1);assert.equal(rows[0].current_state,'修复')});


test('盘中绘图只采用同日 READY 扫描并按扫描时间排序',()=>{
 const rows=[
  {scan_at:'2026-10-12T10:40:00+08:00',data_quality:'READY',up_ratio:.3},
  {scan_at:'2026-10-11T14:30:00+08:00',data_quality:'READY',up_ratio:.8},
  {scan_at:'2026-10-12T09:40:00+08:00',data_quality:'READY',up_ratio:.5},
  {scan_at:'2026-10-12T11:40:00+08:00',data_quality:'DEGRADED',up_ratio:.1}
 ];
 const s=validSnapshots(rows,'2026-10-12');
 assert.equal(s.length,2);
 assert.equal(s[0].up_ratio,.5);
 assert.ok(Math.abs(snapshotChange(s,'up_ratio',100)+20)<1e-7);
 assert.equal(snapshotChange(s.slice(0,1),'up_ratio',100),null);
});
test('趋势顺序只认正式 rank，未上榜板块不虚构名次',()=>{
 const registry={trends:[{trend_name:'甲'},{trend_name:'乙'},{trend_name:'丙'}]};
 const handoff={signals:[{trend_name:'乙',rank:1},{trend_name:'丙',rank:2}]};
 const history={
  甲:[{scan_at:'2026-10-12T09:40:00+08:00',data_quality:'READY',up_ratio:.5},{scan_at:'2026-10-12T10:40:00+08:00',data_quality:'READY',up_ratio:.1}],
  乙:[{scan_at:'2026-10-12T09:40:00+08:00',data_quality:'READY',up_ratio:.4},{scan_at:'2026-10-12T10:40:00+08:00',data_quality:'READY',up_ratio:.6}]
 };
 const formal=rankedTrendRows(registry,handoff,history,'2026-10-12');
 assert.deepEqual(formal.map(x=>x.trend_name),['乙','丙','甲']);
 assert.equal(formal[2].priorityRank,null);
 const moving=rankedTrendRows(registry,handoff,history,'2026-10-12','change');
 assert.deepEqual(moving.map(x=>x.trend_name),['甲','乙','丙']);
 assert.equal(moving[0].intradayDelta,-40);
});


test('A 股折线只按同指标首末有效点判断红涨绿跌',()=>{
 assert.equal(seriesDirection([{value:20},{value:21}]),'rise');
 assert.equal(seriesDirection([{value:20},{value:19}]),'fall');
 assert.equal(seriesDirection([{value:20},{value:20}]),'neutral');
 assert.equal(seriesDirection([{value:20}]),'neutral');
 assert.equal(seriesDirection([{value:null},{value:20}]),'neutral');
 assert.equal(seriesDirection([{ratio:.43},{ratio:.61}],'ratio'),'rise');
});
test('研究状态分别对应确认、候选、观察、扩散和衰弱语义',()=>{
 assert.equal(statusTone('趋势确认'),'rise');
 assert.equal(statusTone('趋势扩散'),'rise');
 assert.equal(statusTone('候选趋势'),'candidate');
 assert.equal(statusTone('观察'),'watch');
 assert.equal(statusTone('分歧'),'caution');
 assert.equal(statusTone('减弱'),'fall');
 assert.equal(statusTone('READY'),'ready');
 assert.equal(statusTone('WAIT'),'neutral');
});


test('近五次趋势核验按交易日排序、不补缺失日期、末次同日记录优先',()=>{
 const rows=trendEvents({state_history:[
 {trade_date:'2026-10-09',to:'观察',reason:'收盘维持'},
 {trade_date:'2026-09-30',to:'趋势确认'},
 {trade_date:'2026-10-09',to:'候选趋势',reason:'最新核验'},
 {trade_date:'invalid',to:'趋势确认'},
 {trade_date:'2026-10-08',to:'候选趋势'}]},5);
 assert.deepEqual(rows.map(x=>x.trade_date),['2026-09-30','2026-10-08','2026-10-09']);
 assert.equal(rows.at(-1).market_state,'候选趋势');
 assert.equal(rows.at(-1).reason,'最新核验');
});
test('跨日快照仅使用真实的归档最后扫描，同日盘中覆盖同日归档',()=>{
 const archive={result_kind:'a_share_intraday_crossday_archive',days:[
  {trade_date:'2026-10-08',trends:{'煤炭':{scan_at:'2026-10-08T14:36:00+08:00',up_ratio:.48}}},
  {trade_date:'2026-10-09',trends:{'煤炭':{scan_at:'2026-10-09T14:36:00+08:00',up_ratio:.52}}},
  {trade_date:'2026-10-12',trends:{'煤炭':{scan_at:'2026-10-12T09:45:00+08:00',up_ratio:.1}}}
 ]};
 const monitor={result_kind:'a_share_intraday_monitor_state',trade_date:'2026-10-12',industry_history:{'煤炭':[
  {scan_at:'2026-10-12T09:46:00+08:00',up_ratio:.43,data_quality:'READY'},
  {scan_at:'2026-10-12T10:45:00+08:00',up_ratio:.29,data_quality:'READY'}
 ]}};
 const rows=archivedDays(archive,monitor,'煤炭');
 assert.deepEqual(rows.map(x=>x.trade_date),['2026-10-08','2026-10-09','2026-10-12']);
 assert.equal(rows.at(-1).up_ratio,.29);
 assert.equal(rows.at(-1).source,'today_scans');
 assert.equal(rows[1].source,'archived_last_scan');
 assert.deepEqual(archivedDays({result_kind:'unexpected',days:archive.days},null,'煤炭'),[]);
});
test('空跨日归档仅有今日真实监测，不捏造历史交易日',()=>{
 const rows=archivedDays({result_kind:'a_share_intraday_crossday_archive',days:[]},{result_kind:'a_share_intraday_monitor_state',trade_date:'2026-10-12',stock_history:{'600001':[{
 scan_at:'2026-10-12T10:10:00+08:00',data_quality:'READY',price:12.3
 }] }},'600001','stock');
 assert.equal(rows.length,1);
 assert.equal(rows[0].price,12.3);
});

test('高优先级风险状态和分歧不会与正常状态混用',()=>{
 assert.equal(statusTone('衰退预警'),'fall');
 assert.equal(statusTone('高潮/衰退'),'fall');
 assert.equal(statusTone('分歧'),'caution');
 assert.equal(statusTone('趋势确认'),'rise');
 assert.equal(statusTone('候选趋势'),'candidate');
});



const today='2026-10-12';
const sampleTrade=(code,quantity,price)=>row(code,'首仓',quantity,price,today);
const riskRow=(code,first,action='清仓剩余',extras={})=>({
 '股票代码':code,'股票名称':'测试股票','计划状态':{name:'生效'},'生效日期':today,
 '首道退出价格':first,'首道退出动作':{name:action},'触发依据':{name:'日线收盘'},...extras
});
function owned(code='600988',plans=[riskRow(code,39.50)],shares=400){
 const portfolio=summarizeTrades([sampleTrade(code,shares,40.475)]);
 return attachRiskPlans(portfolio,plans,'OK',today).positions[0];
}
function monitor(price=39.28,options={}){
 return {result_kind:'a_share_intraday_monitor_state',trade_date:today,
  stock_history:{'600988':[{
   scan_at:today+'T14:39:54+08:00',data_quality:'READY',price,
   price_behavior:'转弱',change_pct:-5.07,relative_to_industry_pct:-0.81,
   latest_low:{price:36.83},trend_name:'黄金/贵金属',
   entry_action:'等待',holding_action:null,...options
  }]},
  industry_history:{'黄金/贵金属':[{
   scan_at:today+'T14:39:54+08:00',data_quality:'READY',current_state:'衰退预警'
  }]}
 };
}
test('交易流水继续单独计算净持仓与加权成本，退出计划不改变持仓股数',()=>{
 const trade=summarizeTrades([
  sampleTrade('601212',2000,5.70),
  row('601212','加仓',2000,5.54,today)
 ]);
 const joined=attachRiskPlans(trade,[
  riskRow('601212',5.48,'减仓',{
   '首道减仓股数':2000,'最终退出价格':5.35,
   '最终退出动作':{name:'清仓剩余'}
  })
 ],'OK',today);
 assert.equal(joined.positions[0].shares,4000);
 assert.ok(Math.abs(joined.positions[0].avgCost-5.62)<0.0001);
 assert.equal(joined.positions[0].riskPlan.firstQuantity,2000);
});
test('赤峰黄金39.50元结构化收盘线优先，盘中走弱只是辅助证据',()=>{
 const p=owned();
 const result=assessHoldingRisk(p,monitor(),'2026-10-12');
 assert.equal(result.rule.state,'close_pending');
 assert.equal(result.rule.levels[0].price,39.5);
 assert.match(result.label,/39.50/);
 assert.match(result.label,/待收盘确认/);
 assert.equal(result.state,'pending');
 assert.ok(result.evidence.some(x=>x.includes('盘中走弱')));
 assert.ok(result.evidence.some(x=>x.includes('相对所属行业')));
});
test('淮北矿业预警价15.88与收盘退出线15.70分开处理',()=>{
 const p=owned('600988',[
  riskRow('600988',15.70,'清仓剩余',{'预警价格':15.88})
 ],500);
 const a=assessHoldingRisk(p,monitor(15.82),today);
 assert.equal(a.rule.state,'warning_only');
 assert.equal(a.rule.levels.length,2);
 assert.equal(a.rule.levels[0].kind,'warning');
 assert.equal(a.rule.levels[1].price,15.7);
 assert.equal(a.state,'warning');
 assert.doesNotMatch(a.label,/盘中走弱/);
});
test('白银有色多级退出计划直接用数字和股数，不从备注提取',()=>{
 const p=owned('601212',[
  riskRow('601212',5.48,'减仓',{
   '首道减仓股数':2000,'最终退出价格':5.35,
   '最终退出动作':'清仓剩余','策略说明':'备注写5.99元并不构成退出线。'
  })
 ],4000);
 assert.equal(p.riskPlan.firstQuantity,2000);
 const missing=assessHoldingRisk(p,monitor(5.3),today);
 assert.equal(missing.state,'not_covered');
 assert.equal(missing.rule.state,'await_price');
 assert.deepEqual(missing.rule.levels.map(x=>x.price),[5.48,5.35]);
 assert.equal(missing.rule.levels[0].quantity,2000);
 assert.ok(missing.rule.detail.includes('5.35'));
 assert.doesNotMatch(missing.rule.detail,/5\.99/);
});
test('两级价格盘中均低于时展示最终退出（但日线必须收盘确认）',()=>{
 const p=owned('600988',[riskRow('600988',5.48,'减仓',{
  '首道减仓股数':200,'最终退出价格':5.35,
  '最终退出动作':'清仓剩余'
 })],400);
 const r=assessHoldingRisk(p,monitor(5.30),today);
 assert.equal(r.rule.state,'close_pending');
 assert.deepEqual(r.rule.levels.map(x=>x.observation),['below','below']);
 assert.match(r.label,/最终退出价5.35/);
 assert.match(r.rule.detail,/拟清仓剩余/);
 assert.notEqual(r.state,'triggered');
});
test('只在明确选择盘中触发依据且存在有效READY快照时提示触及，不代表成交',()=>{
 const p=owned('600988',[riskRow('600988',40,'清仓剩余',{'触发依据':'盘中'})]);
 const result=assessHoldingRisk(p,monitor(39.28),today);
 assert.equal(result.rule.state,'intraday_touched');
 assert.equal(result.state,'triggered');
 assert.match(result.rule.detail,/不代表已委托或成交/);
 const safe=assessHoldingRisk(p,monitor(40.20),today);
 assert.equal(safe.rule.state,'intraday_not_touched');
});
test('规则缺失或结构化表不可用时，绝不回退到旧文字字段',()=>{
 const trade=summarizeTrades([sampleTrade('600988',400,40.475)].map(x=>({
  ...x,'失效条件':'【收盘确认】首道退出线39.50元，卖出400股'
 })));
 const missing=attachRiskPlans(trade,[],'OK',today).positions[0];
 assert.equal(missing.planState,'missing');
 assert.equal(evaluateExitCondition(missing,39.28).state,'no_plan');
 assert.match(assessHoldingRisk(missing,monitor(),today).label,/退出计划待录入/);
 const unavailable=attachRiskPlans(trade,null,'HTTP_500',today).positions[0];
 assert.equal(unavailable.planState,'unavailable');
 assert.match(assessHoldingRisk(unavailable,monitor(),today).label,/数据源不可用/);
});
test('同股票多条生效计划须拦截，不自动选择价格较低的一条',()=>{
 const trade=summarizeTrades([sampleTrade('600988',400,40.475)]);
 const plans=[riskRow('600988',39.5),riskRow('600988',37.2)];
 const p=attachRiskPlans(trade,plans,'OK',today).positions[0];
 assert.equal(p.planState,'invalid');
 assert.equal(p.riskPlan,null);
 assert.match(p.planIssue,/多条生效/);
});
test('超额减仓、首道已清仓仍配置最终退出、逆序阈值和无生效日期均拦截',()=>{
 const base=summarizeTrades([sampleTrade('601212',400,5.7)]);
 const check=extra=>attachRiskPlans(base,[riskRow('601212',5.48,'减仓',extra)],'OK',today).positions[0];
 assert.equal(check({'首道减仓股数':500}).planState,'invalid');
 assert.equal(check({'首道减仓股数':200,'最终退出价格':5.49,'最终退出动作':'清仓剩余'}).planState,'invalid');
 assert.equal(check({'首道减仓股数':200,'生效日期':''}).planState,'invalid');
 const p=attachRiskPlans(base,[riskRow('601212',5.48,'清仓剩余',{
  '最终退出价格':5.35,'最终退出动作':'清仓剩余'
 })],'OK',today).positions[0];
 assert.equal(p.planState,'invalid');
});
test('停用、待核验、未来生效计划不能用于正式风险判断',()=>{
 const base=summarizeTrades([sampleTrade('600988',400,40.475)]);
 for(const status of ['待核验','停用']){
  const p=attachRiskPlans(base,[riskRow('600988',39.5,'清仓剩余',{'计划状态':status})],'OK',today).positions[0];
  assert.equal(p.planState,'missing');
 }
 const future=attachRiskPlans(base,[riskRow('600988',39.5,'清仓剩余',{'生效日期':'2026-10-13'})],'OK',today).positions[0];
 assert.equal(future.planState,'invalid');
});
test('过期行情、DEGRADED采样、未覆盖池不会模拟当前退出触发',()=>{
 const p=owned();
 const old=monitor();old.trade_date='2026-10-09';
 assert.equal(assessHoldingRisk(p,old,today).state,'stale');
 const quality=monitor();quality.stock_history['600988'][0].data_quality='DEGRADED';
 assert.equal(assessHoldingRisk(p,quality,today).state,'not_covered');
 const noSymbol=owned('600985',[riskRow('600985',15.7)],500);
 assert.equal(assessHoldingRisk(noSymbol,monitor(),today).state,'not_covered');
 const verify=assessHoldingRisk({...p,verified:false},monitor(),today);
 assert.equal(verify.state,'unverified');
});

const sampleScan=(day,code,trend,rank,time='09:48',extra={})=>({
 scan_at:day+'T'+time+':00+08:00',data_quality:'READY',rank,code,trend_name:trend,
 company_name:'样本'+code,price:10,change_pct:0,relative_to_industry_pct:0,...extra
});
test('代表股每板块仅一只，以冻结正式顺位选取而不按盘中涨幅或强弱更换',()=>{
 const day='2026-10-12';
 const monitor={
  result_kind:'a_share_intraday_monitor_state',trade_date:day,
  industry_history:{煤炭:[sampleScan(day,'000001','煤炭',null)],黄金:[sampleScan(day,'000002','黄金',null)]},
  stock_history:{
   '600001':[sampleScan(day,'600001','煤炭',5,'09:48'),sampleScan(day,'600001','煤炭',999,'14:39',{change_pct:20})],
   '600002':[sampleScan(day,'600002','煤炭',2,'09:48'),sampleScan(day,'600002','煤炭',2,'14:39',{change_pct:-8})],
   '600003':[sampleScan(day,'600003','黄金',6)],
   '600004':[sampleScan(day,'600004','黄金',7,{change_pct:15})]
  }
 };
 const out=selectRepresentativeStocks(monitor,null,day);
 assert.equal(out.length,2);
 assert.equal(out.find(x=>x.trend_name==='煤炭').code,'600002');
 assert.equal(out.find(x=>x.trend_name==='黄金').code,'600003');
 assert.equal(out.find(x=>x.trend_name==='煤炭').rank,2);
 assert.equal(out[0].source,'frozen_monitor_pool');
});
test('代表股必须有同日READY个股与板块快照，缺失时不会扩池或借旧日数据',()=>{
 const day='2026-10-12';
 const valid=sampleScan(day,'600001','煤炭',1);
 const monitor={result_kind:'a_share_intraday_monitor_state',trade_date:day,
  industry_history:{煤炭:[valid],黄金:[valid]},
  stock_history:{
   '600001':[sampleScan(day,'600001','煤炭',1,'09:48',{data_quality:'DEGRADED'})],
   '600002':[sampleScan('2026-10-09','600002','煤炭',2)],
   '600003':[sampleScan(day,'600003','黄金',3)]
  }
 };
 assert.deepEqual(selectRepresentativeStocks(monitor,null,day).map(x=>x.code),['600003']);
 assert.deepEqual(selectRepresentativeStocks({...monitor,trade_date:'2026-10-09'},null,day),[]);
 assert.deepEqual(selectRepresentativeStocks(null,null,day),[]);
});
test('冻结名次不存在时按同板块正式结果回退，仍保持代码确定性',()=>{
 const day='2026-10-12';
 const monitor={result_kind:'a_share_intraday_monitor_state',trade_date:day,
  industry_history:{'固态电池':[sampleScan(day,'999999','固态电池',null)]},
  stock_history:{
   '000049':[sampleScan(day,'000049','固态电池',null)],
   '002125':[sampleScan(day,'002125','固态电池',null)]
  }};
 const buy={trade_date:'2026-10-09',items:[
  {code:'000049',trend_name:'固态电池',rank:4},
  {code:'002125',trend_name:'固态电池',rank:1}
 ]};
 assert.equal(selectRepresentativeStocks(monitor,buy,day)[0].code,'002125');
 assert.equal(selectRepresentativeStocks(monitor,null,day)[0].code,'000049');
});
