import React from 'react';
import {Crown} from 'lucide-react';
import {fixed,fmtTime} from '../model.js';
import {selectTodayLeader} from '../todayLeader.js';

// 只画真实的四节点采样：节点缺失时不连跨节点虚线。
function FourNodeChart({points,change}) {
 const rows=Array.isArray(points)?points:[];
 const prices=rows.map(point=>point.price),low=Math.min(...prices),high=Math.max(...prices);
 const pad=Math.max((high-low)*.18,high*.002,.001);
 const x=slot=>10+(slot-1)*53;
 const y=price=>5+(high+pad-price)/(high-low+pad*2)*30;
 const color=change>0?'#C75852':change<0?'#416FB6':'#8490A5';
 return <svg viewBox="0 0 180 40" preserveAspectRatio="xMidYMid meet" role="img"
  aria-label={'今日四节点价格：'+rows.map(p=>fmtTime(p.scan_at)+' '+fixed(p.price)+'元').join('，')}>
  <line x1="8" y1="36" x2="172" y2="36" stroke="currentColor" strokeOpacity=".10"/>
  {rows.slice(1).map((point,i)=>{
   const previous=rows[i];
   return point.slot-previous.slot===1
    ?<line key={point.slot} x1={x(previous.slot)} y1={y(previous.price)} x2={x(point.slot)} y2={y(point.price)}
      stroke={color} strokeWidth="2.2" strokeLinecap="round"/>
    :null;
  })}
  {rows.map(point=><g key={point.slot}>
   <circle cx={x(point.slot)} cy={y(point.price)} r="3" fill={color} stroke="#273449" strokeWidth="1"/>
   <title>{fmtTime(point.scan_at)+' · '+fixed(point.price)+'元'}</title>
  </g>)}
 </svg>;
}

export default function TodayLeader({monitor,buy,portfolio,holdingCharts,holdingSnapshot,status,tradeDate}) {
 const {leader,poolCount,coveredCount,slot}=selectTodayLeader({
  monitor,buy,portfolio,holdingCharts,holdingSnapshot,status,tradeDate
 });
 const rate=leader?.last.change_pct;
 const source=leader?[leader.inHolding?'持仓':null,leader.inHandoff?'Handoff':null].filter(Boolean).join(' / '):'';
 return <section className="today-leader" aria-label="今日领跑个股">
  <div className="today-leader-heading"><Crown size={17} aria-hidden="true"/><strong>今日领跑</strong></div>
  {leader?<div className="today-leader-identity" title={leader.name+' · '+leader.code+' · '+source}>
   <strong>{leader.name}</strong>
   <small>{leader.code} · {leader.trendName||'板块待映射'}</small>
  </div>:<div className="today-leader-waiting">等待今日有效快照</div>}
  {leader&&<div className={'today-leader-return '+(rate>0?'market-up':rate<0?'market-down':'')}>
   <strong>{rate>0?'+':''}{fixed(rate,2)}%</strong>
   <small>相对昨收</small>
  </div>}
  <div className="today-leader-visual" title={leader?'第'+slot+'节点 · '+fmtTime(leader.last.scan_at)+' · 同节点覆盖 '+coveredCount+'/'+poolCount+'只 · '+source:'候选 '+poolCount+' 只，等待同日快照'}>
   <div className="today-leader-plot-head"><span>今日 4 节点走势</span><small>{leader?leader.scans.length:0}/4</small></div>
   {leader?<FourNodeChart points={leader.scans} change={rate}/>:<span className="today-leader-chart-empty">— · — · — · —</span>}
  </div>
 </section>;
}
