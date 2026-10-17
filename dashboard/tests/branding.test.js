import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read=path=>readFileSync(new URL('../'+path,import.meta.url),'utf8');
const brandFiles=[
 'index.html','src/App.jsx','src/styles.css','README.md',
 'public/favicon.svg','public/wordmark.svg',
];
const formerName='\u8fa8\u52bf';

test('识势 is the only Chinese product name in all brand surfaces',()=>{
 for(const path of brandFiles){
  const source=read(path);
  assert.ok(!source.includes(formerName),path+' still includes former product name');
 }
 assert.match(read('index.html'),/<title>识势<\/title>/);
 assert.match(read('index.html'),/name="application-name" content="识势"/);
 assert.match(read('index.html'),/property="og:site_name" content="识势"/);
 assert.match(read('src/App.jsx'),/className="breadcrumb-muted">识势/);
 assert.match(read('src/App.jsx'),/className="login-editorial-brandname"><strong>识势/);
 assert.match(read('src/App.jsx'),/w\.x\. · 识势/);
 assert.match(read('README.md'),/^# 识势 · A 股决策中心/m);
});

test('brand artwork remains w.x. but accessible logo names say 识势',()=>{
 for(const path of ['public/favicon.svg','public/wordmark.svg']){
  const svg=read(path);
  assert.match(svg,/aria-label="识势 w\.x\."/);
 }
 assert.match(read('src/App.jsx'),/alt="识势 w\.x\."/);
});

test('refresh loading screen has one w.x. wordmark without separate W icon',()=>{
 const source=read('src/App.jsx');
 const boot=source.match(/if\(authenticated===null\)return <div className="boot-screen">([^\n]+)<\/div>;/)?.[1]||'';
 assert.match(boot,/className="brand-wordmark" src="\/wordmark\.svg"/);
 assert.match(boot,/className="spinner"/);
 assert.doesNotMatch(boot,/className="brand-mark"/);
 assert.doesNotMatch(boot,/src="\/favicon\.svg"/);
 assert.match(read('index.html'),/rel="icon"[^>]+href="\/favicon\.svg"/);
});
