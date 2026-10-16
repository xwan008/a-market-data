import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const app=readFileSync(new URL('../src/App.jsx',import.meta.url),'utf8');
const validation=readFileSync(new URL('../src/components/TrendValidation.jsx',import.meta.url),'utf8');
const selectMenu=readFileSync(new URL('../src/components/SelectMenu.jsx',import.meta.url),'utf8');
const refreshCss=readFileSync(new URL('../src/experience-refresh.css',import.meta.url),'utf8');
const main=readFileSync(new URL('../src/main.jsx',import.meta.url),'utf8');

test('概览盘中变化保留广度与强度双折线图，并移除买点机会和完整监测详情',()=>{
 const nav=app.slice(app.indexOf('const sections ='),app.indexOf('const tone ='));
 assert.doesNotMatch(nav,/id:'monitor'/);
 const overview=app.slice(app.indexOf('function Overview({'),app.indexOf('function Trends({'));
 const feature=overview.slice(overview.indexOf('<section className="decision-feature intraday-simple"'),overview.indexOf('<div className="decision-bottom">'));
 assert.match(feature,/aria-pressed=\{monitorUi\.tab==='sector'\}/);
 assert.match(feature,/aria-pressed=\{monitorUi\.tab==='stock'\}/);
 assert.match(feature,/<SelectMenu className="ui-select--intraday"/);
 assert.match(feature,/trendOptions\.map\(item=>\(\{value:item\.name,label:item\.name\}\)\)/);
 assert.match(feature,/stockOptions\.map\(item=>\(\{value:item\.code/);
 assert.match(feature,/<SnapshotPlot rows=\{active\.scans\} field="up_ratio"/);
 assert.match(feature,/<SnapshotPlot rows=\{active\.scans\} field="median_change_pct" label="盘中板块强度"/);
 assert.match(feature,/<SnapshotPlot rows=\{selectedStock\.scans\} field="price"/);
 assert.match(feature,/<SnapshotPlot rows=\{selectedStock\.scans\} field="relative_to_industry_pct"/);
 assert.equal((feature.match(/<SnapshotPlot/g)||[]).length,4,'两个互斥分支各两张折线图');
 assert.match(feature,/className="intraday-simple-charts"/);
 assert.match(overview,/stockOptions=Object\.entries\(monitorCurrent\?monitor\.stock_history/);
 assert.doesNotMatch(feature,/feature-caption|focus-switch|跨日追溯|详细监测/);
 assert.doesNotMatch(overview,/decision-panel decision-opportunity|正式买点机会/);
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

test('展开持仓以退出价格和计划动作为主，冗长规则与备注收进依据折叠区',()=>{
 const plan=app.slice(app.indexOf('function PortfolioPlan({'),app.indexOf('function PortfolioTrades({'));
 const portfolio=app.slice(app.indexOf('function Portfolio({'),app.indexOf('function Login({'));
 assert.match(plan,/portfolio-plan-compact/);
 assert.match(plan,/fixed\(line\.price,2\)/);
 assert.match(plan,/计划减仓/);
 assert.match(plan,/portfolio-plan-meta/);
 assert.match(plan,/portfolio-rule-description/);
 assert.match(portfolio,/规则依据与说明/);
 assert.doesNotMatch(portfolio,/剩余成本估算 \{fixed\(p\.costValue\)\}/);
 assert.doesNotMatch(portfolio,/portfolio-inline-foot/);
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
 assert.match(validation,/className="validation-page-heading"/);
 assert.doesNotMatch(validation,/className="validation-hero"|validation-hero-graphic|SIGNAL<\/span>/);
});

test('全站可见筛选统一使用有键盘交互的自定义菜单',()=>{
 assert.match(selectMenu,/aria-haspopup="listbox"/);
 assert.match(selectMenu,/role="option"/);
 assert.match(selectMenu,/ArrowDown/);
 assert.match(selectMenu,/Escape/);
 assert.match(selectMenu,/pointerdown/);
 assert.match(app,/className="ui-select--group"/);
 assert.match(validation,/<SelectMenu label="按信号状态筛选"/);
 assert.match(refreshCss,/\.ui-select-trigger:focus-visible[\s\S]*?outline:none/);
 assert.match(refreshCss,/\.new-home \.overview-brief-monitor\{background:transparent\}/);
 assert.match(refreshCss,/\.data-table thead,\.app-shell \.data-table th\{background:#E6ECF5/);
});

test('新的桌面与移动布局主题加载在既有 neutral ink 之后',()=>{
 assert.match(main,/neutral-ink-v2\.css';\s*import '\.\/experience-refresh\.css'/);
 assert.match(refreshCss,/\.portfolio-grid-row/);
 assert.match(refreshCss,/\.validation-page-heading/);
 assert.match(refreshCss,/@media\(max-width:760px\)/);
});
