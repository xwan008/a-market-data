import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = path => readFileSync(new URL('../src/'+path,import.meta.url),'utf8');
const css = read('neutral-ink-v2.css');
const app = read('App.jsx');
const leader = read('components/TodayLeader.jsx');

test('A-share price colors stay red-up and green-down, while navigation stays neutral',()=>{
 assert.match(css,/--market-up:\s*#C75852\b/i);
 assert.match(css,/--market-down:\s*#1C805B\b/i);
 assert.match(css,/--mint:\s*#5266A8\b/i);
 assert.match(css,/\.app-shell \.plot-fall stop:first-child\{stop-color:var\(--market-down\)\}/);
 assert.match(css,/\.app-shell \.plot-line-fall\{stroke:var\(--market-down\)/);
 assert.match(css,/\.app-shell \.market-down/);
});

test('OHLC candle body/wick and falling intraday plots use market green',()=>{
 assert.match(app,/const x=16\+i\*17,rise=b\.close>=b\.open,color=rise\?'#C75852':'#1C805B'/);
 assert.match(app,/direction>0\?'#C75852':direction<0\?'#1C805B'/);
 assert.match(app,/direction==='rise'\?'#C75852':direction==='fall'\?'#1C805B'/);
 assert.match(leader,/change>0\?'#C75852':change<0\?'#1C805B'/);
});
