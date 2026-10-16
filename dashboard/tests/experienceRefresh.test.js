import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const app=readFileSync(new URL('../src/App.jsx',import.meta.url),'utf8');
const validation=readFileSync(new URL('../src/components/TrendValidation.jsx',import.meta.url),'utf8');
const refreshCss=readFileSync(new URL('../src/experience-refresh.css',import.meta.url),'utf8');
const main=readFileSync(new URL('../src/main.jsx',import.meta.url),'utf8');

test('盘中监测不再占用独立导航，完整记录保留在概览中按需展开',()=>{
 const nav=app.slice(app.indexOf('const sections ='),app.indexOf('const tone ='));
 assert.doesNotMatch(nav,/id:'monitor'/);
 assert.match(app,/monitorExpanded&&<section className="overview-monitor-expanded"/);
 assert.match(app,/<Monitor monitor={monitor} archive={archive} status={status}/);
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
