import React from 'react';
import {Crown,Clock3} from 'lucide-react';
import {fixed,fmtTime} from '../model.js';
import {selectTodayLeader} from '../todayLeader.js';

const periods=['上午①','上午②','下午①','下午②'];

function FourNodeChart({points,change}) {
 const rows=Array.isArray(points)?points:[];
 const prices=rows.map(p=>p.price),low=Math.min(...prices),high=Math.max(...prices);
 const pad=Math.max((high-low)*.18,high*.002,.001);
 const y=value=>10+(high+pad-value)/(high-low+pad*2)*72;
 const x=slot=>16+(slot-1)*105;
 const color=change>0?'#e68178':change<0?'#6cb897':'#b6c3bd';
 return <svg viewBox="0 0 348 96" preserveAspectRatio="xMidYMid meet" role="img" aria-label={'今日真实节点：'+rows.map(r=>fmtTime(r.scan_at)+' '+fixed(r.price)+'元').join('，')}>
  {[16,48,80].map(v=><line key={v} x1="8" x2="340" y1={v} y2={v} stroke="currentColor" strokeOpacity=".11" strokeDasharray="3 5"/>)}
  {rows.slice(1).map((p,i)=>{const prev=rows[i];return p.slot-prev.slot===1?
   <line key={p.slot} x1={x(prev.slot)} y1={y(prev.price)} x2={x(p.slot)} y2={y(p.price)} stroke={color} strokeWidth="2.6" strokeLinecap="round"/>:null})}
  {rows.map(p=><g key={p.slot}><circle cx={x(p.slot)} cy={y(p.price)} r="4" fill={color} stroke="#16201b" strokeWidth="1.4"/><title>{fmtTime(p.scan_at)+' · '+fixed(p.price)+'元'}</title></g>)}
 </svg>;
}
export default function TodayLeader({monitor,buy,portfolio,holdingCharts,holdingSnapshot,status,tradeDate}) {
 const {leader,poolCount,coveredCount,slot}=selectTodayLeader({monitor,buy,portfolio,holdingCharts,holdingSnapshot,status,tradeDate});
 const rate=leader?.last.change_pct;
 return <section className="today-leader" aria-label="今日领跑个股">
  <div className="today-leader-info">
   <div className="today-leader-heading"><Crown size={19} aria-hidden="true"/><strong>今日领跑个股</strong><small>持仓 ∪ 正式 Handoff</small></div>
   {leader?<div className="today-leader-result">
    <div className="today-leader-identity"><strong title={leader.name}>{leader.name}</strong><span>{leader.code} · {leader.trendName||'所属板块待映射'}</span>
     <small>{[leader.inHolding?'我的持仓':null,leader.inHandoff?'正式 Handoff':null].filter(Boolean).join(' / ')}</small></div>
    <div className={'today-leader-return '+(rate>0?'market-up':rate<0?'market-down':'')}><strong>{rate>0?'+':''}{fixed(rate,2)}%</strong><small>{rate<0?'相对领跑 · 仍下跌':'最新节点 · 相对昨收'}</small></div>
   </div>:<div className="today-leader-waiting">今日尚无可比较的有效个股节点</div>}
   <div className="today-leader-note">{leader?<><Clock3 size={13}/> {fmtTime(leader.last.scan_at)} · 第{slot}节点 · 同节点覆盖 {coveredCount}/{poolCount} 只</>:<>等待今日同节点有效报价 · 候选 {poolCount} 只</>}</div>
  </div>
  <div className="today-leader-visual">
   <div className="today-leader-plot-head"><strong>今日 4 节点走势</strong><span>{leader?leader.scans.length+'/4 · 实际快照':'0/4 · 待更新'}</span></div>
   {leader?<FourNodeChart points={leader.scans} change={rate}/>:<div className="today-leader-chart-empty">节点发布后自动显示，不使用历史价格代替</div>}
   <div className="today-leader-periods">{periods.map(p=><span key={p}>{p}</span>)}</div>
   <div className="today-leader-disclaimer">同一盘中节点比较涨跌幅；不补缺失点，不代表 READY 买点。</div>
  </div>
 </section>;
}
