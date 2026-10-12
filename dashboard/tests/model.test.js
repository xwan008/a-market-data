import test from 'node:test';
import assert from 'node:assert/strict';
import {summarizeTrades,extractRecords,latestMonitorRecords,fixed,validSnapshots,snapshotChange,rankedTrendRows,seriesDirection,statusTone,trendEvents,archivedDays,assessHoldingRisk,evaluateExitCondition,extractExitLevels} from '../src/model.js';

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


function holding(code='600988',conditions=['趋势失效条件暂未设置，待结合日K及风险预算确认。']) {
 return {code,shares:400,verified:true,avgCost:40.475,conditions};
}
function monitoring(price=39.28,options={}) {
 const day='2026-10-12';
 return {result_kind:'a_share_intraday_monitor_state',trade_date:day,
  stock_history:{'600988':[{
   scan_at:day+'T14:39:54+08:00',data_quality:'READY',price,
   price_behavior:'转弱',change_pct:-5.07,relative_to_industry_pct:-0.81,
   latest_low:{price:36.83},trend_name:'黄金/贵金属',entry_action:'等待',holding_action:null,
   ...options
  }]},
  industry_history:{'黄金/贵金属':[{scan_at:day+'T14:39:54+08:00',
    data_quality:'READY',current_state:'衰退预警'}]}
 };
}
test('已持有 WAIT 股票用真实净持仓和当日快照进行风险观察，不把空仓等待冒充持仓意见',()=>{
 const result=assessHoldingRisk(holding(),monitoring(),'2026-10-12');
 assert.equal(result.state,'watch');
 assert.match(result.label,/盘中走弱/);
 assert.equal(result.rule.state,'unconfirmed');
 assert.equal(result.last.price,39.28);
 assert.ok(result.evidence.some(x=>x.includes('相对所属行业')));
 assert.ok(result.evidence.some(x=>x.includes('历史结构低点')));
 assert.ok(result.evidence.some(x=>x.includes('衰退预警')));
 assert.equal(result.evidence.some(x=>x.includes('卖出建议')),false);
});
test('没有明确退出线不能拿买点计划或历史结构低点自动做卖出阈值',()=>{
 const r=assessHoldingRisk(holding(),monitoring(35,{history_break_state:'broken',
  trend_entry_plan:{invalidation_price:51.21}}),'2026-10-12');
 assert.equal(r.rule.state,'unconfirmed');
 assert.notEqual(r.state,'triggered');
 assert.ok(r.evidence.some(x=>x.includes('低于历史结构低点')));
});
test('盘中低于用户设定的收盘退出线，也只能等待有效收盘确认',()=>{
 const r=assessHoldingRisk(holding('600988',['收盘价跌破40元时止损']),monitoring(39.28),'2026-10-12');
 assert.equal(r.state,'pending');
 assert.equal(r.rule.state,'close_pending');
 assert.match(r.rule.detail,/收盘确认/);
});
test('只有明确的盘中硬止损规则被有效盘中快照跌破时才标示触及',()=>{
 const rule=['盘中跌破40元立即止损'];
 const touched=assessHoldingRisk(holding('600988',rule),monitoring(39.28),'2026-10-12');
 assert.equal(touched.rule.state,'intraday_touched');
 assert.equal(touched.state,'triggered');
 const safe=assessHoldingRisk(holding('600988',rule),monitoring(40.2),'2026-10-12');
 assert.equal(safe.rule.state,'intraday_not_touched');
 assert.notEqual(safe.state,'triggered');
 assert.match(touched.rule.detail,/不代表已成交/);
});
test('不明确时间口径、多个退出价格和文字条件均不生成确定退出信号',()=>{
 assert.equal(evaluateExitCondition(['跌破40元止损'],39.1).state,'review');
 assert.equal(evaluateExitCondition(['盘中跌破40元止损，收盘确认再执行'],39.1).state,'review');
 assert.equal(evaluateExitCondition(['盘中跌破40元止损，涨到45元止盈'],39.1).state,'review');
 assert.equal(evaluateExitCondition(['盘中低于40元观察'],39.1).state,'review');
 assert.equal(evaluateExitCondition(['盘中跌破40元止损','收盘跌破39元止损'],38).state,'review');
});
test('旧日快照、失效扫描、未覆盖股票和未核实股数都不能伪造持仓判断',()=>{
 const old=monitoring();old.trade_date='2026-10-09';
 assert.equal(assessHoldingRisk(holding(),old,'2026-10-12').state,'stale');
 const degraded=monitoring();degraded.stock_history['600988'][0].data_quality='DEGRADED';
 assert.equal(assessHoldingRisk(holding(),degraded,'2026-10-12').state,'not_covered');
 assert.equal(assessHoldingRisk(holding('600985'),monitoring(),'2026-10-12').state,'not_covered');
 assert.equal(assessHoldingRisk({...holding(),verified:false},monitoring(),'2026-10-12').state,'unverified');
});

test('赤峰黄金的长文本规则应识别39.50元收盘退出线，不被日期和盘中短破说明干扰',()=>{
 const rule='【2026-10-12拟定｜日线收盘确认】核心退出线39.50元：若日线收盘价严格低于39.50元，退出全部400股。10/12页面列出收盘39.61元；若仅盘中跌破后收回，不算确认。下方38.25元为阶段支撑。';
 const p=holding('600988',[rule]);
 const result=assessHoldingRisk(p,monitoring(39.28),'2026-10-12');
 assert.equal(result.rule.state,'close_pending');
 assert.equal(result.rule.levels.length,1);
 assert.equal(result.rule.levels[0].price,39.5);
 assert.match(result.label,/39.50/);
 assert.match(result.label,/待收盘确认/);
 assert.equal(result.state,'pending');
});
test('淮北矿业双价格线：15.88预警线盘中低于，不把15.70收盘退出线当成已触发',()=>{
 const p=holding('600988',['【2026-10-12拟定｜日线收盘确认】预警线15.88元：本轮短线预警。首要退出线15.70元：若后续日线收盘严格低于15.70元，退出全部500股。15.57元是阶段底线。']);
 const r=assessHoldingRisk(p,monitoring(15.82),'2026-10-12');
 assert.equal(r.rule.state,'warning_only');
 assert.equal(r.rule.levels.length,2);
 assert.equal(r.rule.levels[0].kind,'warning');
 assert.equal(r.rule.levels[1].price,15.7);
 assert.equal(r.state,'warning');
 assert.match(r.label,/15.88/);
 assert.doesNotMatch(r.label,/盘中走弱/);
});
test('白银有色两级退出线在缺少冻结行情时仍显示Airtable规则，但不能认定已触发',()=>{
 const text='【2026-10-12拟定｜日线收盘确认】第一道退出线5.48元：若日线收盘价严格低于5.48元，计划减仓2000股。最终失效线5.35元：若收盘低于5.35元，余下仓位退出；仅盘中跌破不算确认。';
 const p={code:'601212',shares:4000,verified:true,avgCost:5.62,conditions:[text,text]};
 const r=assessHoldingRisk(p,monitoring(15.82),'2026-10-12');
 assert.equal(r.state,'not_covered');
 assert.equal(r.rule.state,'await_price');
 assert.deepEqual(r.rule.levels.map(x=>x.price),[5.48,5.35]);
 assert.match(r.label,/退出计划已记录/);
 assert.equal(r.rule.levels[0].observation,'no_quote');
 const old=monitoring(15.82);old.trade_date='2026-10-09';
 const stale=assessHoldingRisk(p,old,'2026-10-12');
 assert.equal(stale.state,'stale');
 assert.match(stale.rule.label,/退出计划已记录/);
});
test('两级用户退出线分别判断盘中价位，收盘要求不会降级成自动减仓',()=>{
 const plan=['【日线收盘确认】第一道退出线5.48元：若日线收盘价严格低于5.48元计划减仓；最终失效线5.35元：收盘低于5.35元退出。'];
 const p=holding('600988',plan);
 const r=assessHoldingRisk(p,monitoring(5.3),'2026-10-12');
 assert.equal(r.rule.state,'close_pending');
 assert.deepEqual(r.rule.levels.map(x=>x.observation),['below','below']);
 assert.notEqual(r.state,'triggered');
 assert.match(r.label,/5.48/);
 assert.match(r.label,/5.35/);
});
test('名称相同价格不一致或没有明确判断时点则不主动解释为触发',()=>{
 const inconsistent=['【日线收盘确认】核心退出线39.50元；旧版本核心退出线38.25元'];
 assert.equal(extractExitLevels(inconsistent).state,'conflict');
 const unknown=['核心退出线39.50元，但尚不确定用盘中或收盘'];
 assert.equal(extractExitLevels(unknown).state,'ambiguous');
 assert.equal(evaluateExitCondition(unknown,39.2).state,'review');
});
