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

test('趋势与买点表格只强调表头，当前行仅用边缘标记；搜索输入框无内层聚焦描边',()=>{
 assert.match(refreshCss,/\.data-table tbody tr\.row-selected\{background:#FFF\}/);
 assert.match(refreshCss,/\.data-table tbody tr\.row-selected td:first-child\{[\s\S]*?box-shadow:inset 3px 0 0/);
 assert.match(refreshCss,/\.search,\.validation-search\):focus-within\{[\s\S]*?box-shadow:inset 0 0 0 1px/);
 assert.match(refreshCss,/\.search,\.validation-search\) input:focus-visible\{[\s\S]*?outline:none[\s\S]*?box-shadow:none/);
});

test('趋势买点详情改成跟随文档的粘性紧凑卡片，不再使用内部纵向滚动',()=>{
 const inspector=app.slice(app.indexOf('function BuyInspector({'),app.indexOf('function Buy({'));
 const buy=app.slice(app.indexOf('function Buy({'),app.indexOf('function Monitor({'));
 assert.match(inspector,/buy-inspector--compact/);
 assert.match(inspector,/buy-inspector-focus/);
 assert.match(inspector,/观察参考区间 · 非买点/);
 assert.match(inspector,/WAIT 不可作为入场或止损指令/);
 assert.match(inspector,/safeText\(item\.invalidation_rule\)/);
 assert.doesNotMatch(inspector,/className="invalidation"|className="disclaimer"/);
 assert.match(buy,/className="panel inspector inspector-tall buy-detail-pane"/);
 assert.doesNotMatch(buy,/独立滚动/);
 assert.match(refreshCss,/\.buy-workspace>\.buy-detail-pane\{[\s\S]*?position:sticky;top:88px[\s\S]*?max-height:none;overflow:visible/);
});

test('没有可靠区间的股票使用小字号提示，买点统计显示独立圆角卡片',()=>{
 const inspector=app.slice(app.indexOf('function BuyInspector({'),app.indexOf('function Buy({'));
 const buy=app.slice(app.indexOf('function Buy({'),app.indexOf('function Monitor({'));
 assert.match(inspector,/const hasZone=Array\.isArray\(zone\)/);
 assert.match(inspector,/hasZone\?'buy-inspector-zone':'buy-inspector-zone is-unavailable'/);
 assert.match(refreshCss,/\.buy-inspector-zone\.is-unavailable strong\{[\s\S]*?font-size:12px/);
 assert.match(buy,/className="buy-stat-card buy-stat-ready"/);
 assert.match(buy,/className="buy-stat-card buy-stat-wait"/);
 assert.match(buy,/className="buy-stat-card buy-stat-covered"/);
 assert.match(refreshCss,/\.buy-summary>div::before\{/);
 assert.match(refreshCss,/border:1px solid #DEE5F0;border-radius:13px/);
});

test('全站顶栏移除手动刷新按钮，但仍在登录成功时主动读取发布数据',()=>{
 const header=app.slice(app.indexOf('function Header({'),app.indexOf('function Sidebar({'));
 assert.doesNotMatch(header,/刷新数据|RefreshCw|onClick=\{refresh\}/);
 assert.match(header,/className="top-date"/);
 assert.match(header,/className="icon-button logout"/);
 assert.match(app,/if\(authenticated\)fetchData\(\)/);
 assert.match(app,/fetch\('\/api\/data',\{cache:'no-store'\}\)/);
});

test('板块趋势、买点、持仓和趋势验证的顶部指标统一采用紧凑、圆角的信息卡',()=>{
 const trends=app.slice(app.indexOf('function Trends({'),app.indexOf('function PageIntro({'));
 const portfolio=app.slice(app.indexOf('function Portfolio({'),app.indexOf('function Login({'));
 assert.match(trends,/className="buy-summary trend-summary"/);
 assert.match(trends,/今日盘中有值/);
 assert.match(trends,/来自正式趋势榜单名次/);
 assert.doesNotMatch(trends,/className="ranking-explainer"/);
 assert.match(portfolio,/className="portfolio-summary-strip"/);
 assert.match(portfolio,/portfolio-summary-cost/);
 assert.match(portfolio,/<ShieldAlert size=\{14\}\/>需要关注/);
 assert.match(validation,/className="validation-observations"/);
 assert.match(refreshCss,/\.buy-summary>div:last-child\{[\s\S]*?min-height:86px/);
 assert.match(refreshCss,/\.portfolio-summary-strip>div\{[\s\S]*?min-height:86px/);
 assert.match(refreshCss,/\.validation-observation\{[\s\S]*?min-height:86px/);
 assert.match(refreshCss,/\.buy-stat-value\{[\s\S]*?grid-column:2;grid-row:1\/3/);
});

test('移除导航冗余英文，五页标题共用字号与基线，右上角对齐内容边线',()=>{
 const sidebar=app.slice(app.indexOf('function Sidebar({'),app.indexOf('function Metric({'));
 const portfolio=app.slice(app.indexOf('function Portfolio({'),app.indexOf('function Login({'));
 assert.doesNotMatch(sidebar,/工作空间|PRIVATE INVESTOR DESK|side-footer|side-group-label/);
 assert.doesNotMatch(portfolio,/PORTFOLIO \/ RISK DESK/);
 assert.doesNotMatch(validation,/SIGNAL VALIDATION/);
 assert.match(refreshCss,/\.topbar\{padding-left:42px;padding-right:42px\}/);
 assert.match(refreshCss,/\.page-intro\{margin:0 0 20px\}/);
 assert.match(refreshCss,/\.portfolio-title-row h1\{margin:0 0 6px\}/);
 assert.match(refreshCss,/\.validation-page-heading h1\{margin:0\}/);
 assert.match(refreshCss,/\.page-intro h1,\.decision-heading h1,\.portfolio-title-row h1,\.validation-page-heading h1\)\{[\s\S]*?font-size:26px/);
 assert.match(refreshCss,/@media\(max-width:760px\)\{[\s\S]*?\.topbar\{padding-left:14px;padding-right:14px\}/);
});

test('趋势验证去除冗余英文小标题与副标题，所有页面共用简洁页脚',()=>{
 const validationHeading=validation.slice(validation.indexOf('<header className="validation-page-heading">'),validation.indexOf('{!ok?<section'));
 assert.match(validationHeading,/<h1>趋势验证<\/h1>/);
 assert.doesNotMatch(validationHeading,/<p>|eyebrow/);
 assert.doesNotMatch(validation,/AWAITING VERIFIED DATA|FORWARD PERFORMANCE|SIGNAL ARCHIVE/);
 assert.doesNotMatch(validation,/<div><span className="eyebrow">/);
 const footer=app.slice(app.indexOf('<footer className="main-footer">'),app.indexOf('</footer>')+'</footer>'.length);
 assert.match(footer,/w\.x\. · 识势/);
 assert.match(footer,/页面读取于/);
 assert.doesNotMatch(footer,/GitHub 文件和私有 Airtable 记录|仅供研究参考/);
 assert.match(refreshCss,/\.validation-section-head h2\{margin:0\}/);
});

test('板块趋势把当日盘中覆盖与历史研究池分开呈现，缺值不视为异常',()=>{
 const table=app.slice(app.indexOf('function TrendTable({'),app.indexOf('function holdingIntradayPresentation('));
 const trends=app.slice(app.indexOf('function Trends({'),app.indexOf('function PageIntro({'));
 assert.match(table,/盘中数值只覆盖当日候选/);
 assert.match(table,/hasBreadth\?<div className="trend-intraday-cell"/);
 assert.match(table,/className="trend-no-snapshot"/);
 assert.doesNotMatch(table,/未覆盖<\/small>|盘中上涨占比<\/th>|当日广度变化<\/th>/);
 assert.match(table,/className="trend-row-meta"/);
 assert.match(trends,/coveredCount=rows\.filter/);
 assert.match(trends,/hasPlot\?<div className="sector-chart-inset/);
 assert.match(trends,/本次没有盘中数值快照/);
 assert.match(trends,/onClick=\{\(\)=>setDetailView\('summary'\)\}/);
 assert.match(refreshCss,/\.trend-ranked-table\{table-layout:fixed;width:100%\}/);
});

test('关键标题、正文、表格及次级说明有一致的字号层级',()=>{
 assert.match(refreshCss,/\.page-intro p,\.portfolio-title-row p,\.validation-page-heading p\)\{[\s\S]*?font-size:13px/);
 assert.match(refreshCss,/\.data-table th\{font-size:11px/);
 assert.match(refreshCss,/\.data-table td\{font-size:13px/);
 assert.match(refreshCss,/\.portfolio-cell strong\{font-size:13px/);
 assert.match(refreshCss,/\.validation-record-name strong\{font-size:13px/);
});

test('新的桌面与移动布局主题加载在既有 neutral ink 之后',()=>{
 assert.match(main,/neutral-ink-v2\.css';\s*import '\.\/experience-refresh\.css'/);
 assert.match(refreshCss,/\.portfolio-grid-row/);
 assert.match(refreshCss,/\.validation-page-heading/);
 assert.match(refreshCss,/@media\(max-width:760px\)/);
});
