import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const css=readFileSync(new URL('../src/neutral-ink-v2.css',import.meta.url),'utf8');
const refreshCss=readFileSync(new URL('../src/experience-refresh.css',import.meta.url),'utf8');
const app=readFileSync(new URL('../src/App.jsx',import.meta.url),'utf8');
const lastRule=selector=>[...css.matchAll(new RegExp(selector+'\\s*\\{([^}]+)\\}','g'))].at(-1)?.[1]||'';

test('login uses a designed two-layer card while keeping the existing left artwork',()=>{
 const login=app.slice(app.indexOf('function Login({'),app.indexOf('export default function App()'));
 assert.match(login,/className="login-minimal"/);
 assert.ok(login.indexOf('className="login-minimal-visual"')<login.indexOf('className="login-minimal-panel"'));
 assert.match(login,/className="login-minimal-art"/);
 assert.match(login,/className="login-minimal-tagline"/);
 assert.match(login,/辨趋势之真伪，<br\/><strong>顺市场之大势。<\/strong>/);
 assert.match(login,/className="login-minimal-card"/);
 assert.match(login,/className="login-minimal-cardvisual"/);
 assert.match(login,/className="login-minimal-cardbody"/);
 assert.match(login,/className="login-minimal-cardvisual-seal"/);
 assert.doesNotMatch(login,/login-screen--terminal|login-editorial|login-market|login-visual/);
 assert.match(refreshCss,/\.login-minimal\{[\s\S]*?grid-template-columns:minmax\(0,58%\) minmax\(0,42%\)/);
 assert.match(refreshCss,/@media\(max-width:820px\)\{[\s\S]*?\.login-minimal-visual\{display:none\}/);
 assert.match(login,/<h1 id="login-title">欢迎回来<\/h1>/);
 assert.doesNotMatch(login,/私人研究空间/);
 assert.doesNotMatch(login,/登录识势，继续研究。|识势 · W\.X\./);
 assert.match(refreshCss,/\.login-minimal-content::before\{[\s\S]*?radial-gradient\(ellipse at 50% 49%,rgba\(111,138,197,\.18\)/);
 assert.match(refreshCss,/\.login-minimal-card\{[\s\S]*?border-radius:25px;[\s\S]*?rgba\(100,127,188,\.11\)/);
 assert.match(refreshCss,/\.login-minimal-cardvisual\{[\s\S]*?height:155px;[\s\S]*?linear-gradient/);
 assert.match(refreshCss,/\.login-minimal-cardbody\{[\s\S]*?margin-top:-13px;[\s\S]*?border-radius:20px/);
 assert.doesNotMatch(login,/研究有据|决策有序|识别市场结构|坚持决策纪律/);
});

test('new login form preserves password authentication and accessible states',()=>{
 const login=app.slice(app.indexOf('function Login({'),app.indexOf('export default function App()'));
 assert.match(login,/onSubmit=\{e=>\{e\.preventDefault\(\);login\(password\)\}\}/);
 assert.match(login,/autoComplete="current-password"/);
 assert.match(login,/type=\{showPassword\?'text':'password'\}/);
 assert.match(login,/aria-label=\{showPassword\?'隐藏密码':'显示密码'\}/);
 assert.match(login,/role="alert"/);
 assert.match(login,/disabled=\{loading\|\|!!setupError\}/);
 assert.match(refreshCss,/\.login-minimal-field:focus-within\{border-color:#6A80AB;background:#FFFFFF;box-shadow:none;outline:none\}/);
});

test('workspaces use equal 42px content gutters on desktop and retain mobile spacing',()=>{
 assert.match(css,/\.app-shell \.main-content\{\s*max-width:1740px;\s*padding-top:42px;\s*padding-left:42px;\s*padding-right:42px;/);
 assert.match(css,/@media\(max-width:1250px\)\{\s*\.app-shell \.main-content\{padding-left:42px;padding-right:42px\}/);
 assert.match(css,/@media\(max-width:760px\)\{[\s\S]*?\.app-shell \.main-content\{padding-top:24px;padding-left:14px;padding-right:14px\}/);
});

test('overview white parent card pads its full KPI and monitoring areas',()=>{
 assert.match(css,/\.app-shell \.new-home \.overview-brief\{\s*padding-left:18px;\s*padding-right:18px;/);
 assert.match(css,/\.app-shell \.new-home \.overview-brief-monitor\{\s*padding:12px 0;/);
 assert.match(css,/\.app-shell \.new-home \.overview-kpi:first-child\{\s*padding-left:0;/);
});

test('buy summary badge dot remains 4px and its label does not overlap the number',()=>{
 assert.match(css,/\.app-shell \.buy-summary \.badge \.badge-dot\{\s*flex:0 0 4px;\s*width:4px;\s*height:4px;/);
 assert.match(css,/\.app-shell \.buy-summary>div>strong\{\s*grid-column:2;/);
 assert.match(css,/\.app-shell \.buy-summary>div>span:last-child\{\s*grid-column:1\/-1;/);
});

test('actual refresh skeletons are neutral rather than legacy dark green',()=>{
 assert.match(css,/\.app-shell \.skeleton\{\s*background:linear-gradient\(95deg,#E8ECF3/);
 assert.match(app,/!payload\?<Skeleton\/>:/);
});

test('retain A-share red-up green-down semantics',()=>{
 assert.match(css,/--market-up:#C75852/);
 assert.match(css,/--market-down:#1C805B/);
});
