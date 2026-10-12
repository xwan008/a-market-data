import test from 'node:test';
import assert from 'node:assert/strict';
import {summarizeTrades,extractRecords,latestMonitorRecords,fixed} from '../src/model.js';

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
