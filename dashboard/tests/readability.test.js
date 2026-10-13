import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const css=readFileSync(new URL('../src/styles.css',import.meta.url),'utf8');
const getLastToken=token=>{
 const matches=[...css.matchAll(new RegExp(token+'\\s*:\\s*(#[0-9a-fA-F]{6})','g'))];
 return matches.at(-1)?.[1]?.toLowerCase();
};
const luminance=hex=>{
 const rgb=[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)/255)
  .map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);
 return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;
};
const contrast=(a,b)=>{
 const x=luminance(a),y=luminance(b);
 return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);
};

test('readability colors retain at least 7:1 contrast on core dark surfaces',()=>{
 const foregrounds=['--read-primary','--read-secondary','--read-muted'];
 const backgrounds=['--bg','--surface','--surface2','#121617'];
 for(const fgToken of foregrounds){
  const foreground=getLastToken(fgToken);
  assert.ok(foreground,fgToken+' exists');
  for(const bgToken of backgrounds){
   const background=bgToken.startsWith('#')?bgToken:getLastToken(bgToken);
   assert.ok(background,bgToken+' exists');
   assert.ok(contrast(foreground,background)>=7,fgToken+' on '+bgToken+' has insufficient contrast');
  }
 }
});

test('historical cards are no longer dimmed at container level',()=>{
 assert.match(css,/\.trend-history-event,\.trend-history-event\.is-latest,\.crossday-card\{opacity:1\}/);
 assert.match(css,/\.new-home \.home-holding\s*\{/);
 assert.match(css,/\.new-home \.today-leader\s*\{/);
});
test('A-share up and down color meanings are unchanged',()=>{
 assert.equal(getLastToken('--market-up'),'#e68178');
 assert.equal(getLastToken('--market-down'),'#6fbd99');
 assert.match(css,/\.new-home \.decision-row-meta small\.intraday-breadth-change\.market-up/);
 assert.match(css,/\.new-home \.decision-row-meta small\.intraday-breadth-change\.market-down/);
});
