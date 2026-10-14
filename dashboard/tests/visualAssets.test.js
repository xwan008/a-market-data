import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = path => readFileSync(new URL('../' + path,import.meta.url),'utf8');

test('wordmark and favicon stroke gradients always resolve to a defined SVG id',()=>{
 for (const path of ['public/wordmark.svg','public/favicon.svg']) {
  const svg=read(path);
  const defs=new Set([...svg.matchAll(/<(?:linearGradient|radialGradient)\s+id="([^"]+)"/g)].map(match=>match[1]));
  const refs=[...svg.matchAll(/url\(#([^)]+)\)/g)].map(match=>match[1]);
  assert.ok(refs.length>0,path+' should render a visible gradient logo');
  for(const ref of refs) assert.ok(defs.has(ref),path+' has an undefined paint reference '+ref);
 }
});

test('neutral-ink count chips have a light background and readable text',()=>{
 const css=read('src/neutral-ink-v2.css');
 const rules=[...css.matchAll(/\.app-shell \.count-chip\s*\{([^}]+)\}/g)];
 assert.ok(rules.length>0,'missing neutral-ink count-chip override');
 const rule=rules.at(-1)[1];
 assert.match(rule,/background:\s*#EEF1F7\b/i);
 assert.match(rule,/color:\s*#455676\b/i);
 assert.match(rule,/border:\s*1px solid #DFE5EF\b/i);
});
