import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const css=readFileSync(new URL('../src/neutral-ink-v2.css',import.meta.url),'utf8');
const app=readFileSync(new URL('../src/App.jsx',import.meta.url),'utf8');
const lastRule=selector=>[...css.matchAll(new RegExp(selector+'\\s*\\{([^}]+)\\}','g'))].at(-1)?.[1]||'';

test('login keeps original colorful artwork on desktop and mobile',()=>{
 assert.match(css,/\.login-screen--terminal \.login-visual\{\s*filter:none;\s*opacity:1;/);
 assert.match(css,/@media\(max-width:1080px\)[\s\S]*?\.login-screen--terminal \.login-visual\{\s*filter:none;\s*opacity:\.73;/);
 assert.match(css,/linear-gradient\(113deg,#A8C9CE 0%,#6A9EAD 55%,#3E7181 100%\)/);
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
