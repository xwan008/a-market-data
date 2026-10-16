import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const app=readFileSync(new URL('../src/App.jsx',import.meta.url),'utf8');
const validation=readFileSync(new URL('../src/components/TrendValidation.jsx',import.meta.url),'utf8');
const refreshCss=readFileSync(new URL('../src/experience-refresh.css',import.meta.url),'utf8');
const main=readFileSync(new URL('../src/main.jsx',import.meta.url),'utf8');

test('概览的盘中变化只有趋势或个股选择与一张真实快照折线图，没有完整记录入口',()=>{
 const nav=app.slice(app.indexOf('const sections ='),app.indexOf('const tone ='));
 assert.doesNotMatch(nav,/id:'monitor'/);
 const overview=app.slice(app.indexOf('function Overview({'),app.indexOf('function Trends({'));
 const feature=overview.slice(overview.indexOf('<section className="decision-feature intraday-simple"'),overview.indexOf('<section className="decision-panel decision-opportunity"'));
 assert.match(feature,/aria-pressed=\{monitorUi\.tab==='sector'\}/);
 assert.match(feature,/aria-pressed=\{monitorUi\.tab==='stock'\}/);
 assert.match(feature,/select aria-label=\{monitorUi\.tab==='sector'\?'选择趋势':'选择个股'\}/);
 assert.match(feature,/trendOptions\.map\(item=><option/);
 assert.match(feature,/stockOptions\.map\(item=><option/);
 assert.match(feature,/<SnapshotPlot rows=\{active\.scans\} field="up_ratio"/);
 assert.match(feature,/<SnapshotPlot rows=\{selectedStock\.scans\} field="price"/);
 assert.equal((feature.match(/<SnapshotPlot/g)||[]).length,2,'两个互斥分支各一张折线图');
 assert.match(overview,/stockOptions=Object\.entries\(monitorCurrent\?monitor\.stock_history/);
 assert.doesNotMatch(feature,/feature-plot-grid|feature-caption|focus-switch|relative_to_industry_pct|median_change_pct/);
 assert.doesNotMatch(overview,/完整监测|完整记录|monitorExpanded|<Monitor/);
 assert.doesNotMatch(app,/section==='monitor'/);
});

test('持仓首页展示登记成本与风控状态，不推算未核验实时收益',()=>{
 const portfolio=app.slice(app.indexOf('function Portfolio({'),app.indexOf('function Login({'));
 assert.match(portfolio,/登记剩余成本估算/);
 assert.match(portfolio,/非市值或盈亏/);
 assert.match(portfolio,/assessment\.last\?\.price/);
 assert.match(portfolio,/assessment\.rule\?\.levels/);
 assert.match(portfolio,/portfolio-secondary-accordions/);
 assert.doesNotMatch(portfolio,/实时盈亏|浮动盈亏|盈亏率/);
});

test('趋势验证的强调数字仍来自发布结果，未成熟和断档不会冒充成功率',()=>{
 assert.match(validation,/summary\.horizon_stats\?\.\[horizon\]/);
 assert.match(validation,/matured\.trend_avg_excess_vs_market_pct/);
 assert.match(validation,/matured\.stock_avg_excess_vs_market_pct/);
 assert.match(validation,/result\.state === 'data_gap'/);
 assert.match(validation,/result\.state === 'pending'/);
 assert.match(validation,/state_timeline/);
 assert.match(validation,/尚无成熟结果/);
 assert.doesNotMatch(validation,/胜率[^。]*\d+%/);
});

test('新的桌面与移动布局主题加载在既有 neutral ink 之后',()=>{
 assert.match(main,/neutral-ink-v2\.css';\s*import '\.\/experience-refresh\.css'/);
 assert.match(refreshCss,/\.portfolio-grid-row/);
 assert.match(refreshCss,/\.validation-hero/);
 assert.match(refreshCss,/@media\(max-width:760px\)/);
});
