// Read-only historical audit. No publication, no signal or trade state mutation.
// Run from repository root: node research/backtests/top5_continuation_audit_20261124.mjs
import fs from "node:fs";
import path from "node:path";
const read=p=>JSON.parse(fs.readFileSync(p,"utf8"));
const cutoff="2026-11-23";
const archive="validation/archive";
const dates=fs.readdirSync(archive).filter(d=>/^2026-\d{2}-\d{2}$/.test(d)&&d<cutoff).sort();
const outcomes=read("validation/results/stocks.json");
const key=(date,theme,code)=>[date,theme,code].join("|");
const byKey=new Map(outcomes.items.map(r=>[key(r.trade_date,r.trend_name,r.code),r]));
const finite=Number.isFinite;
const avg=a=>a.reduce((s,v)=>s+v,0)/a.length;
const groups=[],skips={};
const bump=k=>skips[k]=(skips[k]||0)+1;
for(const date of dates){
  const f=read(path.join(archive,date,"trend_buy_formal_result.json"));
  if(f.trade_date!==date||f.mode!=="FORMAL"||f.status!=="COMPLETE") {bump("invalid_archive");continue;}
  const source=new Map([...f.ready,...f.wait].map(r=>[key(date,r.trend_name,r.code),r]));
  for(const t of f.top5_by_theme||[]){
    const a=t.items.map((i,j)=>{
      const r=source.get(key(date,t.trend_name,i.code));
      if(!r||r.data_date!==date)return null;
      const p=r.phase_evidence||{},q=r.technical_context||{};
      // Missing average volume is zero contribution ONLY if corresponding day count is zero.
      const side=(days,ratio)=>days===0?0:finite(days)&&finite(ratio)?days*ratio:NaN;
      const up=side(p.positive_days_5d,p.up_day_volume_ratio_5d),down=side(p.negative_days_5d,p.down_day_volume_ratio_5d);
      return {code:i.code,official:j+1,status:r.status,confirmed:r.market_state==="趋势确认",
        features:[q.relative_strength_20d_vs_market_pct,p.return_5d_pct,p.volume_ratio_5d,up/(up+down),p.positive_days_5d,p.close_location_3d_avg_pct,p.max_close_drawdown_10d_pct],
        out:byKey.get(key(date,t.trend_name,i.code))};
    });
    if(a.length<3||a.length>5||a.some(r=>!r)||new Set(a.map(r=>r.code)).size!==a.length){bump("short_or_missing");continue;}
    if(a.some(r=>!r.features.every(finite))){bump("feature_gap");continue;}
    // All features oriented higher-is-stronger. Midrank handles exact ties.
    for(let k=0;k<7;k++)for(const r of a){
      r.pct??=[];
      r.pct[k]=avg(a.map(s=>s.features[k]<r.features[k]?1:s.features[k]===r.features[k]?0.5:0));
    }
    for(const r of a){
      r.relative=avg(r.pct.slice(0,2));
      r.volume=avg(r.pct.slice(2,4));
      r.structure=avg(r.pct.slice(4));
      r.continuation=avg([r.relative,r.volume,r.structure]);
    }
    groups.push({date,theme:t.trend_name,run:f.run_id,a});
  }
}
const order=(g,m)=>[...g.a].sort((a,b)=>m==="official"?a.official-b.official:b[m]-a[m]||a.official-b.official);
const methods=["official","continuation","relative","volume","structure","equal"];
const names=["top1","top3","top1_market_excess","top1_sector_excess","top1_vs_equal","winner_hit","pairwise_concordance_minus_discordance"];
const result={};
for(const [split,gs] of Object.entries({oct:groups.filter(g=>g.date<"2026-11"),nov:groups.filter(g=>g.date>="2026-11"),all:groups,confirmed5:groups.filter(g=>g.a.length===5&&g.a.every(r=>r.confirmed))})){
  result[split]={};
  for(const h of ["1","3","5"]){
    const eligible=gs.filter(g=>g.a.every(r=>{
      const x=r.out?.horizons?.[h];
      return x?.state==="matured"&&finite(x.return_pct)&&finite(x.excess_vs_market_pct)&&finite(x.excess_vs_sector_pct)&&r.out.source_run_id===g.run&&x.target_date>g.date;
    }));
    const out={groups:eligible.length,dates:new Set(eligible.map(g=>g.date)).size,rows:eligible.reduce((s,g)=>s+g.a.length,0)};
    for(const m of methods){
      const vals=eligible.map(g=>{
        const a=order(g,m),os=a.map(r=>r.out.horizons[h]),all=avg(os.map(x=>x.return_pct));
        const top=m==="equal"?os:os.slice(0,1),top3=m==="equal"?os:os.slice(0,3);
        const pairs=[];
        for(let i=0;i<os.length;i++)for(let j=i+1;j<os.length;j++)pairs.push(Math.sign(os[i].return_pct-os[j].return_pct));
        return [avg(top.map(x=>x.return_pct)),avg(top3.map(x=>x.return_pct)),avg(top.map(x=>x.excess_vs_market_pct)),avg(top.map(x=>x.excess_vs_sector_pct)),avg(top.map(x=>x.return_pct))-all,m==="equal"?null:Number(os[0].return_pct===Math.max(...os.map(x=>x.return_pct))),m==="equal"?null:avg(pairs)];
      });
      out[m]=vals.length?Object.fromEntries(names.map((n,i)=>[n,vals[0][i]===null?null:+avg(vals.map(v=>v[i])).toFixed(3)])):null;
    }
    result[split][h]=out;
  }
}
console.log(JSON.stringify({purpose:"READ_ONLY_HISTORICAL_RANK_AUDIT",cutoff,skips,result},null,2));
