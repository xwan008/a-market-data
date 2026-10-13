import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {validSnapshots,snapshotChange} from '../src/model.js';

const overview=readFileSync(new URL('../src/App.jsx',import.meta.url),'utf8');

test('正式趋势优先榜在第一轮有效快照出现时就渲染真实节点',()=>{
 const scans=validSnapshots([
  {scan_at:'2026-10-13T09:43:15+08:00',data_quality:'READY',up_ratio:.1538,current_state:'分歧'}
 ],'2026-10-13');
 assert.equal(scans.length,1);
 assert.equal(scans[0].up_ratio,.1538);
 assert.equal(snapshotChange(scans,'up_ratio',100),null);
 assert.match(overview,/className="home-mini-chart">\{scans\.length>=1\?<SnapshotPlot rows=\{scans\} field="up_ratio"/);
 assert.match(overview,/d==null\?\(scans\.length===1\?'首轮':'—'\)/);
});

test('尚无有效节点时保持等待，不混入其他交易日或异常扫描',()=>{
 const scans=validSnapshots([
  {scan_at:'2026-10-12T09:40:00+08:00',data_quality:'READY',up_ratio:.5},
  {scan_at:'2026-10-13T09:43:15+08:00',data_quality:'DEGRADED',up_ratio:.2}
 ],'2026-10-13');
 assert.equal(scans.length,0);
 assert.equal(snapshotChange(scans,'up_ratio',100),null);
 assert.match(overview,/scans\.length>=1\?<SnapshotPlot[^\n]+<span className="plot-unavailable">等待盘中扫描<\/span>/);
});

test('两轮后才产生实际广度变化，不能将首轮变化虚构为零',()=>{
 const first={scan_at:'2026-10-13T09:43:15+08:00',data_quality:'READY',up_ratio:.1538};
 const second={scan_at:'2026-10-13T10:41:00+08:00',data_quality:'READY',up_ratio:.22};
 const scans=validSnapshots([second,first],'2026-10-13');
 assert.equal(scans.length,2);
 assert.ok(Math.abs(snapshotChange(scans,'up_ratio',100)-6.62)<1e-9);
});

test('概览持仓展示紧凑盘中状态、红涨绿跌，并保留退出规则在详情页',()=>{
 const holding=overview.slice(overview.indexOf('<h2>我的持仓</h2>'),overview.indexOf('<h2>正式趋势优先榜</h2>'));
 assert.match(overview,/const behaviorTone=\/转弱\|走弱/);
 assert.match(overview,/changeTone=change>0\?'market-up':change<0\?'market-down'/);
 assert.match(holding,/className=\{'holding-risk-brief '\+intraday\.tone\}/);
 assert.match(holding,/className="holding-intraday-meta"/);
 assert.match(holding,/\{intraday\.time\}/);
 assert.match(holding,/pct\(intraday\.change\)/);
 assert.doesNotMatch(holding,/\{intraday\.detail\}/);
 assert.doesNotMatch(holding,/assessment\.label/);
 const styles=readFileSync(new URL('../src/styles.css',import.meta.url),'utf8');
 assert.match(styles,/holding-risk-brief\.market-up/);
 assert.match(styles,/holding-risk-brief\.market-down/);
 assert.match(styles,/holding-intraday-change\.market-up/);
 assert.match(styles,/holding-intraday-change\.market-down/);
});

test('概览持仓两张小图使用正中分隔线而非贴靠今日标签的左边框',()=>{
 const styles=readFileSync(new URL('../src/styles.css',import.meta.url),'utf8');
 assert.match(styles,/\.new-home \.home-holding \.home-holding-charts::before\{/);
 assert.match(styles,/content:"";position:absolute;left:50%;top:4px;bottom:4px;width:1px/);
 assert.match(styles,/\.new-home \.home-holding-chart\{[^}]*align-items:center;text-align:center/);
 assert.doesNotMatch(styles,/\.new-home \.home-holding-chart\+\.home-holding-chart\s*\{[^}]*border-left/);
 assert.match(styles,/@media\(max-width:560px\)\{[\s\S]*?\.home-holding \.home-holding-charts\{[\s\S]*?gap:12px/);
});
