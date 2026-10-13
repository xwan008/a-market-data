import React, {useCallback, useEffect, useMemo, useState} from 'react';
import {
 Activity, ArrowDownRight, ArrowLeft, ArrowRight, ArrowUpRight, BarChart3, CalendarDays,
 Check, ChevronDown, ChevronRight, CircleAlert, Clock3, Command, Database,
 ExternalLink, Eye, EyeOff, GitBranch, Layers, LockKeyhole, LogOut, Menu,
 RefreshCw, Search, ShieldCheck, ShieldAlert, SlidersHorizontal,
 Sparkles, Target, Wallet, X, Zap, PanelLeftClose, ListFilter
} from 'lucide-react';
import TodayLeader from './components/TodayLeader.jsx';
import TrendValidation from './components/TrendValidation.jsx';
import {asArray, latestMonitorRecords, fixed, fmtTime, formatSource, pct, safeText, shanghaiDay, summarizeTrades, validSnapshots, snapshotChange, rankedTrendRows, rankedBuyRows, seriesDirection, statusTone, trendEvents, archivedDays, assessHoldingRisk, attachRiskPlans, selectRepresentativeStocks} from './model.js';

const sections = [
 {id:'overview',icon:BarChart3,title:'市场总览',en:'Overview'},
 {id:'trends',icon:Layers,title:'板块趋势',en:'Trend Radar'},
 {id:'buy',icon:Target,title:'趋势买点',en:'Entry Signals'},
 {id:'monitor',icon:Activity,title:'盘中监测',en:'Live Monitor'},
 {id:'portfolio',icon:Wallet,title:'我的持仓',en:'Portfolio'},
 {id:'validation',icon:BarChart3,title:'趋势验证',en:'Signal Validation'}
];
const tone = statusTone;
const stageLabel = s => ({T1:'T1 · 早期趋势',T2:'T2 · 产业阶段',T3:'T3 · 成熟阶段'}[s]||safeText(s));
function Badge({children,variant}) {
 return <span className={`badge badge-${variant||tone(children)}`}><span className="badge-dot" aria-hidden="true"/>{children}</span>;
}
function ResearchState({value}) {
 const state=value||'—';
 return <span className={`research-state state-${tone(state)}`}><span className="state-dot" aria-hidden="true"/>{state}</span>;
}
function MiniDot({active=false}) {return <span className={`mini-dot ${active?'mini-dot-active':''}`}/>}
function PanelHead({title,aside,children}) {return <div className="panel-head"><div><h3>{title}</h3>{children}</div>{aside}</div>}
function Empty({title,detail,icon:Icon=CircleAlert}) {return <div className="empty"><div className="empty-icon"><Icon size={23}/></div><strong>{title}</strong><p>{detail}</p></div>}
function Skeleton(){return <div className="skeleton-page"><div className="skeleton skeleton-title"/><div className="skeleton-grid">{[1,2,3].map(n=><div className="skeleton skeleton-card" key={n}/>)}</div><div className="skeleton skeleton-panel"/></div>}
function Header({section,refresh,refreshing,data,openMenu,setOpenMenu,logout}) {
 const active=sections.find(x=>x.id===section)||sections[0];
 return <header className="topbar"><div className="top-left"><button className="icon-button mobile-menu" onClick={()=>setOpenMenu(!openMenu)} aria-label="打开导航"><Menu size={20}/></button><span className="breadcrumb-muted">识势</span><ChevronRight size={14} className="breadcrumb-chevron"/><strong>{active.title}</strong></div><div className="top-right"><div className="top-date"><CalendarDays size={15}/><span>{shanghaiDay()} · 北京时间</span></div><button type="button" className="header-btn" onClick={refresh} disabled={refreshing} aria-label={refreshing?"正在刷新数据":"手动刷新数据"} title="读取最新发布的数据"><RefreshCw size={15} className={refreshing?'spin':''}/><span>刷新数据</span></button><button type="button" className="icon-button logout" onClick={logout} title="退出登录" aria-label="退出登录"><LogOut size={18}/></button></div></header>;
}
function Sidebar({section,onSection,openMenu,setOpenMenu,status}){
 const navigate=id=>{onSection(id);setOpenMenu(false)};
 return <><div className={`sidebar-backdrop ${openMenu?'show':''}`} onClick={()=>setOpenMenu(false)}/><aside className={`sidebar ${openMenu?'open':''}`}><div className="brand"><button type="button" className="brand-home" onClick={()=>navigate('overview')} aria-label="返回市场总览"><div className="brand-identity"><img className="brand-wordmark" src="/wordmark.svg" alt="识势 w.x."/></div></button><button className="icon-button mobile-close" onClick={()=>setOpenMenu(false)}><X size={18}/></button></div><div className="side-group-label">工作空间</div><nav className="side-nav">{sections.map(item=><button key={item.id} className={`nav-item ${section===item.id?'selected':''}`} aria-current={section===item.id?'page':undefined} onClick={()=>navigate(item.id)}><item.icon size={18}/><span>{item.title}</span>{item.id==='monitor' && status?.monitor!=='OK' && <span className="nav-signal"/>}{section===item.id && <div className="nav-active-line"/>}</button>)}</nav><div className="sidebar-spacer"/><div className="side-status"><div className="side-status-head"><span className="live-indicator"/>系统状态 <span className="side-status-tag">只读</span></div><div className="side-status-row"><span>GitHub 研究数据</span><strong className={status?.registry==='OK'?'status-good':'status-dim'}>{formatSource(status?.registry)}</strong></div><div className="side-status-row"><span>Airtable 持仓</span><strong className={status?.airtable==='OK'?'status-good':'status-dim'}>{formatSource(status?.airtable)}</strong></div> </div><div className="side-footer"><ShieldCheck size={15}/> PRIVATE INVESTOR DESK <span>v1.0</span></div></aside></>;
}
function Metric({label,value,meta,icon:Icon,accent='blue',hint}) {return <div className="metric-card"><div className="metric-top"><span>{label}</span><span className={`metric-icon metric-${accent}`}><Icon size={18}/></span></div><div className="metric-number">{value}</div><div className="metric-meta">{hint && <span className="metric-hint">{hint}</span>}{meta}</div></div>}
function TrendFocus({item,rank}) {return <div className="focus-row"><div className="focus-rank">{String(rank).padStart(2,'0')}</div><div className="focus-details"><strong>{item.trend_name}</strong><div><span>{safeText(item.trend_state)}</span><span className="tiny-sep">·</span><span>{safeText(item.industry_names?.[0])}</span></div></div><ResearchState value={item.market_state}/></div>}

function HistoryStrip({events}){
 const list=trendEvents({state_history:events},5),today=shanghaiDay();
 if(!list.length)return <p className="muted">尚无可核验的历史状态事件。</p>;
 return <div className="trend-history">
  <div className="trend-history-rail">{list.map((e,i)=>{const isToday=e.trade_date===today;return <div key={e.trade_date} className={'trend-history-event '+(isToday?'is-today':'')+(i===list.length-1?' is-latest':'')}>
   <span className="trend-history-date">{e.trade_date.slice(5)}{isToday&&<b>今日</b>}</span>
   <span className="trend-history-state">{e.market_state?<ResearchState value={e.market_state}/>:<span className="muted">历史观察</span>}</span>
   <span className="trend-history-kind">{i===list.length-1?'最新记录':e.event==='market_state_change'||e.event==='market_downgrade'?'状态迁移':'已记录'}</span>
   {e.reason&&<details className="trend-history-reason"><summary>本轮依据</summary><p>{e.reason}</p></details>}
  </div>})}</div>
  <p className="history-disclaimer">近 {list.length} 次已发布核验事件 · 未记录交易日不补值 · 历史研究判断不等于今日行情</p>
 </div>;
}
function TrendInspector({item,view='all'}) {
 if(!item) return <Empty title="选择一个板块" detail="查看产业状态、支持证据与失效条件"/>;
 const evidence=asArray(item.supporting_evidence).slice(-2).reverse();
 const contrary=asArray(item.contrary_evidence).slice(-2).reverse();
 return <div className="detail-content sector-detail-content">
  {(view==='all'||view==='summary')&&<>
   {view==='all'&&<div className="detail-hero"><h2>{item.trend_name}</h2><div className="detail-badges"><ResearchState value={item.market_state}/><Badge>{item.lifecycle_status}</Badge></div></div>}
   <div className="data-pair"><div><span>产业阶段</span><strong>{stageLabel(item.trend_state)}</strong></div><div><span>最近核验</span><strong>{safeText(item.last_verified_trade_date)}</strong></div></div>
   <div className="invalidation"><span>失效观察条件</span><p>{safeText(item.invalidation_condition)}</p></div>
  </>}
  {(view==='all'||view==='history')&&<div className="detail-section"><div className="small-heading"><GitBranch size={15}/> 状态演变</div><HistoryStrip events={item.state_history}/></div>}
  {(view==='all'||view==='evidence')&&<>
   <div className="detail-section"><div className="small-heading"><Check size={15}/> 支持证据</div>{evidence.length?evidence.map((e,i)=><div className="evidence" key={i}><span className="evidence-date">{e.trade_date}</span><p>{e.description}</p>{/^https?:\/\//.test(e.source||'')&&<a href={e.source} target="_blank" rel="noopener noreferrer">查看依据 <ExternalLink size={12}/></a>}</div>):<p className="muted">没有已发布证据</p>}</div>
   <div className="detail-section"><div className="small-heading"><ShieldAlert size={15}/> 反向证据</div>{contrary.length?contrary.map((e,i)=><div className="evidence" key={i}><span className="evidence-date">{e.trade_date}</span><p>{e.description}</p></div>):<p className="muted">暂无记录</p>}</div>
  </>}
 </div>;
}

const signed = (value,digits=1) => typeof value==='number' && Number.isFinite(value) ? (value>0?'+':'')+fixed(value,digits) : '—';

function MiniHoldingCandles({bars}) {
 const valid=asArray(bars).filter(b=>b&&typeof b.date==='string'&&['open','high','low','close'].every(k=>typeof b[k]==='number'&&Number.isFinite(b[k])&&b[k]>0)&&b.high>=Math.max(b.open,b.close)&&b.low<=Math.min(b.open,b.close)).slice(-5);
 if(!valid.length)return <span className="plot-unavailable">等待历史日 K 发布</span>;
 const rawMin=Math.min(...valid.map(b=>b.low)),rawMax=Math.max(...valid.map(b=>b.high));
 const pad=Math.max((rawMax-rawMin)*.12,Math.abs(rawMax)*.006,.001);
 const low=rawMin-pad,high=rawMax+pad,range=high-low;
 const y=value=>7+(high-value)/range*45;
 return <svg className="home-candle-svg" viewBox="0 0 102 54" preserveAspectRatio="xMinYMid meet" role="img" aria-label={'最近'+valid.length+'个完成交易日日 K，'+valid.map(b=>b.date+' 开盘'+fixed(b.open)+' 收盘'+fixed(b.close)).join('，')}>
  {[0,.5,1].map(t=><line key={t} x1="0" x2="100" y1={7+t*45} y2={7+t*45} stroke="currentColor" strokeOpacity=".09" strokeDasharray="3 4"/>)}
  {valid.map((b,i)=>{const x=6+i*17,rise=b.close>=b.open,color=rise?'#e68178':'#6cb897',top=Math.min(y(b.open),y(b.close)),height=Math.max(1.7,Math.abs(y(b.open)-y(b.close)));return <g key={b.date}>
   <line x1={x} x2={x} y1={y(b.high)} y2={y(b.low)} stroke={color} strokeWidth="1.5"/>
   <rect x={x-5} y={top} width="10" height={height} rx=".8" fill={color}/>
   <title>{b.date+' · 开 '+fixed(b.open)+' / 高 '+fixed(b.high)+' / 低 '+fixed(b.low)+' / 收 '+fixed(b.close)}</title>
  </g>})}
 </svg>;
}

function MiniHoldingIntraday({rows}) {
 const data=asArray(rows).filter(item=>typeof item?.price==='number'&&Number.isFinite(item.price)&&item.price>0&&typeof item?.scan_at==='string'&&!Number.isNaN(Date.parse(item.scan_at))).slice(0,4);
 if(!data.length)return <span className="plot-unavailable">等待快照</span>;
 const prices=data.map(item=>item.price),min=Math.min(...prices),max=Math.max(...prices);
 const padding=Math.max((max-min)*.18,Math.abs(max)*.0015,.001);
 const low=min-padding,high=max+padding;
 const y=value=>6+(high-value)/(high-low)*39;
 const coords=data.map((item,i)=>({x:5+Math.min(3,Number.isInteger(item.slot)?item.slot-1:i)*30,y:y(item.price),item}));
 const path=coords.map((cur,i)=>{
   const prev=coords[i-1];
   return (prev&&cur.x-prev.x<=30.5&&cur.x>prev.x?'L':'M')+cur.x.toFixed(1)+' '+cur.y.toFixed(1);
 }).join(' ');
 const direction=data.length>=2?Math.sign(prices.at(-1)-prices[0]):0;
 const color=direction>0?'#e68178':direction<0?'#6cb897':'#b6c3bd';
 return <svg viewBox="0 0 102 54" className="home-sparkline-svg" preserveAspectRatio="xMinYMid meet" role="img" aria-label={'今日已发布 '+data.length+' 次盘中报价：'+data.map(d=>fmtTime(d.scan_at)+' '+fixed(d.price)+'元').join('，')}>
  {[10,30,49].map(v=><line key={v} x1="0" x2="100" y1={v} y2={v} stroke="currentColor" strokeOpacity=".09" strokeDasharray="3 4"/>)}
  {data.length>=2&&<path d={path} stroke={color} strokeWidth="2.2" fill="none" strokeLinecap="round" strokeLinejoin="round"/>}
  {coords.map((d,i)=><g key={d.item.scan_at}><circle cx={d.x} cy={d.y} r={i===coords.length-1?3.2:2.6} fill={color}/><title>{fmtTime(d.item.scan_at)+' · '+fixed(d.item.price)+' 元'}</title></g>)}
 </svg>;
}

function SnapshotPlot({rows,field,label,unit='%',scale=1,bounds=null,compact=false}){
 const id=React.useId().replace(/:/g,'');
 const [hovered,setHovered]=useState(null);
 const data=asArray(rows).filter(row=>typeof row?.[field]==='number'&&Number.isFinite(row[field])&&!Number.isNaN(Date.parse(row.scan_at)))
  .map(row=>({at:Date.parse(row.scan_at),value:row[field]*scale,scan_at:row.scan_at,row})).sort((a,b)=>a.at-b.at);
 const direction=seriesDirection(data,'value');
 if(!data.length)return <span className="plot-unavailable">无有效数值快照</span>;
 const w=compact?154:460,h=compact?60:208;
 const left=compact?6:49,right=compact?6:17,top=compact?9:25,bottom=compact?9:39;
 const values=data.map(x=>x.value);
 let low=bounds?bounds[0]:Math.min(...values),high=bounds?bounds[1]:Math.max(...values);
 if(!bounds){const spread=high-low;const pad=Math.max(spread*.20,Math.max(Math.abs(high),Math.abs(low),1)*.018);low-=pad;high+=pad}
 if(high<=low){low-=1;high+=1}
 const xMin=data[0].at,xMax=data.at(-1).at;
 const xp=item=>xMax===xMin?(left+w-right)/2:left+(item.at-xMin)/(xMax-xMin)*(w-left-right);
 const yp=item=>top+(high-item.value)/(high-low)*(h-top-bottom);
 const pts=data.map(x=>[xp(x),yp(x)]);
 const path=pts.map((p,i)=>(i?'L':'M')+p[0].toFixed(2)+' '+p[1].toFixed(2)).join(' ');
 const area=path+' L'+pts.at(-1)[0].toFixed(2)+' '+(h-bottom)+' L'+pts[0][0].toFixed(2)+' '+(h-bottom)+' Z';
 const display=value=>fixed(value,unit==='元'?2:1)+unit;
 const net=data.length>1?data.at(-1).value-data[0].value:null;
 const directionText=net==null?'仅一轮':net>0?'上涨':net<0?'下跌':'持平';
 const toneColor=direction==='rise'?'#e68178':direction==='fall'?'#6cb897':'#b6c3bd';
 const hoveredIndex=hovered&&data[hovered.idx]?.scan_at===hovered.at&&data[hovered.idx]?.value===hovered.value?hovered.idx:null;
 const hItem=hoveredIndex!=null?data[hoveredIndex]:null;
 return <div className={compact?'plot plot-compact plot-'+direction:'plot plot-large plot-'+direction}>
  {!compact&&<div className="plot-head"><strong>{label}</strong><span className={'plot-head-change plot-head-'+direction}>{directionText}{net!=null?' '+(net>0?'+':'')+display(net):''}<small> · {data.length} 轮真实快照</small></span></div>}
  <div className="plot-canvas" onMouseLeave={()=>setHovered(null)}>
   <svg viewBox={'0 0 '+w+' '+h} preserveAspectRatio="xMidYMid meet" role="img" aria-label={label+'：'+data.map(d=>fmtTime(d.scan_at)+' '+display(d.value)).join('，')}>
    <defs><linearGradient id={id} x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor={toneColor} stopOpacity=".22"/><stop offset="100%" stopColor={toneColor} stopOpacity="0"/></linearGradient></defs>
    {!compact&&[0,.5,1].map((t,i)=><g key={i}><line x1={left} y1={top+t*(h-top-bottom)} x2={w-right} y2={top+t*(h-top-bottom)} className="plot-grid"/><text x={left-8} y={top+t*(h-top-bottom)+4} textAnchor="end" className="plot-axis">{display(high-t*(high-low))}</text></g>)}
    {data.length>=2&&<path d={area} fill={'url(#'+id+')'}/>}
    {data.length>=2&&<path className={'plot-line plot-line-'+direction} d={path} fill="none" strokeWidth={compact?2.3:2.5} strokeLinecap="round" strokeLinejoin="round"/>}
    {data.map((d,i)=>{
     const latest=i===data.length-1;
     return <g key={d.scan_at} onMouseEnter={()=>setHovered({idx:i,at:d.scan_at,value:d.value})}>
      {hoveredIndex===i&&!compact&&<line x1={pts[i][0]} y1={top} x2={pts[i][0]} y2={h-bottom} className="plot-cursor"/>}
      {latest&&<circle cx={pts[i][0]} cy={pts[i][1]} r={5.25} className="plot-latest-ring"/>}
      <circle cx={pts[i][0]} cy={pts[i][1]} r={latest?3.15:(compact?2.4:3)} className={'plot-point plot-point-'+direction+(latest?' plot-point-current':'')}/>
      <circle cx={pts[i][0]} cy={pts[i][1]} r={compact?10:12} fill="transparent" stroke="none" onClick={compact?undefined:e=>{e.stopPropagation();setHovered(hoveredIndex===i?null:{idx:i,at:d.scan_at,value:d.value})}}/>
      <title>{fmtTime(d.scan_at)+' · '+display(d.value)+(latest?' · 最新已发布快照':'')}</title>
      {!compact&&<text x={pts[i][0]+(i===0?2:latest?-2:0)} y={Math.max(top+12,pts[i][1]-12)} className={'plot-point-label '+(latest?'plot-point-label-last':'')} textAnchor={i===0?'start':latest?'end':'middle'}>{display(d.value)}</text>}
      {!compact&&<text x={pts[i][0]} y={h-13} className="plot-axis plot-time" textAnchor="middle">{new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(d.at))}</text>}
     </g>;
    })}
   </svg>
   {compact?<span className={'plot-compact-value plot-head-'+direction}>{display(data.at(-1).value)}</span>:hItem&&<div className="plot-tooltip" role="status"><span className="plot-tooltip-time">{fmtTime(hItem.scan_at)}</span><strong>{display(hItem.value)}</strong><span className={direction==='rise'?'plot-positive':direction==='fall'?'plot-negative':''}>{hoveredIndex===0?'首轮基准': '相对首轮 '+signed(hItem.value-data[0].value,unit==='元'?2:1)+unit}</span>{(hItem.row.current_state||hItem.row.price_behavior)&&<small>监测状态 · {hItem.row.current_state||hItem.row.price_behavior}</small>}</div>}
  </div>
 </div>;
}

function CrossdayTimeline({archive,monitor,identifier,kind='sector'}){
 const rows=archivedDays(archive,monitor,identifier,kind,5),today=shanghaiDay();
 const count=rows.filter(row=>row.source==='archived_last_scan').length;
 return <div className="crossday-view">
  <div className="crossday-head"><strong>近 5 个可追溯交易日</strong><small>历史来自当日末次盘中扫描，不代表收盘价</small></div>
  {rows.length?<div className="crossday-rail">{rows.map(row=>{const isToday=row.trade_date===today;
    const state=kind==='sector'?(row.current_state||row.last_intraday_state):(row.price_behavior||row.relative_strength);
    const value=kind==='sector'?(typeof row.up_ratio==='number'?fixed(row.up_ratio*100,1)+'%':'—'):(typeof row.price==='number'?fixed(row.price,2)+' 元':'—');
    return <div className={'crossday-card '+(isToday?'crossday-today':'')} key={row.trade_date}>
      <div className="crossday-date">{row.trade_date.slice(5)}{isToday&&<span>今日</span>}</div>
      <strong className="crossday-value">{value}</strong>
      <div className="crossday-state">{state?<Badge>{state}</Badge>:<span>无状态</span>}</div>
      <small>{kind==='sector'?'上涨家数占比':'盘中末次快照价'}</small>
    </div>;
  })}</div>:<p className="crossday-unavailable">暂无可核验的跨日历史快照。</p>}
  {!archive&&<p className="history-disclaimer">跨日存档暂不可用；当前只显示已核验的盘中数据。</p>}
  {archive&&count===0&&<p className="history-disclaimer">跨日存档尚无历史交易日记录，当前仅能展示当日数据。后续产生真实归档后这里会自动增加。</p>}
  {count>0&&rows.length<5&&<p className="history-disclaimer">当前只有 {count} 个已归档交易日；不足 5 日不填充缺失值。</p>}
 </div>;
}
function SevenSessionContext({sector,stock}){
 const context=sector?.seven_day||stock?.seven_day;
 if(!context)return <div className="monitor-more-none">暂未提供七日背景数据。</div>;
 const sectorMode=!!sector;
 const available=context.status==='available';
 const value=sectorMode?context.median_constituent_return_pct:context.close_change_7d_pct;
 const sourceDate=context.source_trade_date||context.baseline_trade_date||'未注明';
 return <div className="seven-context">
  <div><small>{sectorMode?'7 个完整交易时段 · 成分股收益中位数':'7 个完整交易时段 · 个股收盘涨跌幅'}</small><strong className={typeof value==='number'?(value>0?'market-up':value<0?'market-down':''):''}>{available&&typeof value==='number'?pct(value):'数据不足'}</strong></div>
  {sectorMode&&<div><small>区间内正收益成分股比例</small><strong>{typeof context.positive_constituent_ratio==='number'?fixed(context.positive_constituent_ratio*100,1)+'%':'—'}</strong></div>}
  <div><small>历史口径与样本</small><strong>{sectorMode?safeText(context.sample_count)+' / '+safeText(context.target_count):safeText(context.observation_count)+' 个有效收盘价'}</strong></div>
  <p>截至 {sourceDate} · {context.status==='available'?'覆盖可用':'数据覆盖不完整'} · 这是截至历史基准日的累计背景，不是逐日曲线，也不是今天的实时信号。</p>
 </div>;
}
function SnapshotTimeline({rows,kind='sector'}){
 if(!rows.length)return <div className="chart-empty">该交易日没有有效监测记录。</div>;
 return <div className="snapshot-timeline">{rows.map((row,i)=><div className="snapshot-event" key={row.scan_at}>
  <div className="snapshot-marker">{String(i+1).padStart(2,'0')}</div>
  <div className="snapshot-event-main"><div className="snapshot-event-head"><strong>{fmtTime(row.scan_at)}</strong><Badge>{kind==='sector'?row.current_state||'—':row.price_behavior||'—'}</Badge><span>{kind==='sector'?'结构动量 '+safeText(row.structure_momentum):'相对强度 '+safeText(row.relative_strength)}</span></div>
  <div className="snapshot-event-figures">{kind==='sector'?'上涨家数占比 '+(typeof row.up_ratio==='number'?fixed(row.up_ratio*100,1)+'%':'—')+' · 中位涨幅 '+pct(row.median_change_pct):'快照价格 '+(typeof row.price==='number'?fixed(row.price)+' 元':'—')+' · 相对行业 '+pct(row.relative_to_industry_pct)}</div>
  <details className="snapshot-details"><summary>查看本轮判断依据</summary><p>{safeText(row.reason)}</p></details>
  </div></div>)}</div>;
}

function TrendTable({trends,onSelect,selected,monitor,monitorDay,sortMode,onSort,compact=false}){
 const [query,setQuery]=useState(''),[state,setState]=useState('全部');
 const filtered=useMemo(()=>trends.filter(t=>(t.trend_name||'').includes(query)&&(state==='全部'||t.market_state===state)),[trends,query,state]);
 const options=[...new Set(trends.map(t=>t.market_state).filter(Boolean))];
 return <><div className="table-controls trend-controls"><div className="search"><Search size={16}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="搜索板块名称…"/></div>
 <div className="filter-select"><select value={state} onChange={e=>setState(e.target.value)} aria-label="按市场状态筛选"><option>全部</option>{options.map(s=><option key={s}>{s}</option>)}</select><ChevronDown size={13}/></div>
 {onSort&&<div className="filter-select"><select value={sortMode} onChange={e=>onSort(e.target.value)} aria-label="排序方式"><option value="state">市场状态优先</option><option value="formal">正式优先名次</option><option value="change">当日广度变化幅度</option></select><ChevronDown size={13}/></div>}</div>
 <div className="table-wrap"><table className="data-table trend-ranked-table"><thead><tr><th>正式名次</th><th>板块方向</th><th>市场状态</th>{!compact&&<th>盘中上涨占比</th>}{!compact&&<th>当日广度变化</th>}<th>核验日</th><th/></tr></thead><tbody>{filtered.map(t=>{
 const rows=validSnapshots(monitor?.[t.trend_name],monitorDay);
 const delta=snapshotChange(rows,'up_ratio',100);
 return <tr key={t.trend_name} className={selected?.trend_name===t.trend_name?'row-selected':''} onClick={()=>onSelect(t)}>
  <td><div className="rank-column"><span className={t.priorityRank!=null?'official-rank':'unranked'}>{t.priorityRank!=null?String(t.priorityRank).padStart(2,'0'):'—'}</span>{t.priorityRank!=null&&<span className="rank-priority-chip">优先</span>}</div></td>
  <td><strong>{t.trend_name}</strong><small>{safeText(t.trend_state)} · {asArray(t.industry_names).slice(0,1).join(' / ')||'正式趋势池'}</small></td>
  <td><div className="trend-state-stack"><span title="正式研究状态"><ResearchState value={t.market_state}/></span>{rows.length>0&&rows.at(-1)?.current_state&&<span className={'trend-scan-status state-'+tone(rows.at(-1).current_state)} title={'盘中扫描 · '+monitorDay}><span className="state-dot"/><span>盘中 {rows.at(-1).current_state}</span></span>}</div></td>
  {!compact&&<td><SnapshotPlot rows={rows} field="up_ratio" label="上涨占比" scale={100} bounds={[0,100]} compact/></td>}
  {!compact&&<td><span className={'trend-delta '+(delta==null?'':delta>0?'trend-up':delta<0?'trend-down':'')}>{delta==null?'—':signed(delta,1)+' pp'}</span><small>{rows.length?'采样 '+rows.length+' 轮':'未覆盖'}</small></td>}
  <td className="mono soft-text">{safeText(t.last_verified_trade_date)}</td><td className="arrow-col"><ChevronRight size={16}/></td>
 </tr>})}</tbody></table>{!filtered.length&&<Empty title="没有匹配板块" detail="调整搜索条件再试" icon={Search}/>}</div>
 <div className="table-footer">展示 {filtered.length} / {trends.length} 个板块 <span>正式名次仅来自趋势 Handoff · 广度变化单位 pp（百分点）</span></div></>;
}

function Overview({registry,trendHandoff,buy,monitor,holdingSnapshot,holdingCharts,portfolio,status,onSection,setSelectedBuy,monitorUi,setMonitorUi,openMonitor}){
 const monitorCurrent=status.monitor==='OK'&&monitor?.result_kind==='a_share_intraday_monitor_state'&&monitor?.trade_date===shanghaiDay();
 const monitorDay=monitorCurrent?monitor.trade_date:null;
 const history=monitorCurrent?monitor.industry_history:{};
 const ranked=rankedTrendRows(registry,trendHandoff,history,monitorDay);
 const official=ranked.filter(x=>x.priorityRank!=null).slice(0,5);
 const monitored=Object.entries(history||{}).map(([name,historyRows])=>{
  const scans=validSnapshots(historyRows,monitorDay);
  return {name,scans,delta:snapshotChange(scans,'up_ratio',100)};
 }).filter(x=>x.scans.length).sort((a,b)=>Math.abs(b.delta??0)-Math.abs(a.delta??0));
 const active=monitored.find(x=>x.name===monitorUi.sector)||monitored[0];
 const industryLatest=active?.scans.at(-1);
 const representatives=selectRepresentativeStocks(monitor,buy,monitorDay);
 const observed=monitored.flatMap(sector=>representatives.filter(x=>x.trend_name===sector.name));
 const selectedRepresentative=observed.find(x=>x.code===monitorUi.stock)||observed[0];
 const selectedStockLast=selectedRepresentative?.last;
 const openCurrentMonitor=()=>openMonitor({
  tab:monitorUi.tab,
  sector:active?.name||'',
  stock:selectedRepresentative?.code||'',
  group:monitorUi.tab==='stock'?(selectedRepresentative?.trend_name||'全部板块'):monitorUi.group
 });
 const retreatSectors=monitored.filter(item=>item.scans.at(-1)?.current_state==='衰退预警');
 const disputeSectors=monitored.filter(item=>item.scans.at(-1)?.current_state==='分歧');
 const positions=[...portfolio.positions.filter(p=>!p.verified),...portfolio.positions.filter(p=>p.verified)].slice(0,4);
 const formalItems=asArray(buy?.items);
 const ready=formalItems.filter(i=>i.status==='READY').slice().sort((a,b)=>(a.rank||999)-(b.rank||999));
 const waitCount=formalItems.filter(i=>i.status==='WAIT').length;
 return <div className="decision-home new-home">
  <div className="decision-heading"><div><h1>今日决策摘要</h1><p>持仓风险优先，趋势变化其次，只有明确的机会才进入视野。</p></div>
   <div className="decision-date"><Clock3 size={14}/><span>趋势研究日 {registry?.trade_date||'—'}<br/>{monitorCurrent?'盘中扫描 '+fmtTime(monitor.last_scan_at):'当前无今日盘中扫描'}</span></div></div>
  <div className="overview-brief" aria-label="今日重点摘要">
   <div className="overview-kpis">
    <button className="overview-kpi" type="button" onClick={()=>onSection('portfolio')} aria-label="查看已核实持仓">
     <span className="overview-kpi-label">已核实持仓</span>
     <span className="overview-kpi-body"><strong>{status.airtable==='OK'?portfolio.positions.filter(x=>x.verified).length:'—'}</strong><span>只</span></span>
    </button>
    <button className="overview-kpi" type="button" onClick={()=>onSection('trends')} aria-label="查看正式优先板块">
     <span className="overview-kpi-label">正式优先板块</span>
     <span className="overview-kpi-body"><strong>{status.trendHandoff==='OK'?official.length:'—'}</strong><span>个</span></span>
    </button>
    <button className="overview-kpi" type="button" onClick={()=>onSection('buy')} aria-label="查看正式 READY 买点">
     <span className="overview-kpi-label">正式 READY</span>
     <span className="overview-kpi-body"><strong>{status.buyHandoff==='OK'?ready.length:'—'}</strong><span>只</span></span>
    </button>
   </div>
   <div className="overview-brief-monitor">
    <span className="overview-brief-label"><Activity size={13}/>盘中观察</span>
    {monitorCurrent?
      <span className="overview-brief-signals">
       {retreatSectors.length>0&&<span className="signal-text signal-fall">衰退预警 {retreatSectors.length}</span>}
       {disputeSectors.length>0&&<span className="signal-text signal-caution">分歧 {disputeSectors.length}</span>}
       {!retreatSectors.length&&!disputeSectors.length&&<span>未发现已发布的衰退预警或分歧</span>}
       <span className="overview-brief-timestamp">· {fmtTime(monitor.last_scan_at)}</span>
      </span>
      :<span className="overview-brief-signals">今日尚无有效盘中扫描</span>}
    <button type="button" className="overview-brief-link" onClick={openCurrentMonitor}>查看监测 <ArrowRight size={13}/></button>
   </div>
  </div>
  <TodayLeader monitor={monitor} buy={buy} portfolio={portfolio} holdingCharts={holdingCharts} holdingSnapshot={holdingSnapshot} status={status} tradeDate={shanghaiDay()}/>
   <div className="decision-grid">
   <section className="decision-panel decision-portfolio"><div className="decision-panel-top"><div><h2>我的持仓</h2><p>只对已发布并被监测覆盖的持仓显示盘中价格快照。</p></div><button className="text-link" onClick={()=>onSection('portfolio')}>全部持仓 <ArrowRight size={14}/></button></div>
    {status.airtable!=='OK'?<div className="decision-empty">Airtable 当前不可用；不能确认持仓。</div>:positions.length?
     <div className="decision-rows">{positions.map(p=>{
      const scans=monitorCurrent?validSnapshots(monitor.stock_history?.[p.code],monitorDay):[];
      const chart=holdingCharts?.result_kind==='a_share_holding_charts'?holdingCharts.stocks?.[p.code]:null;
      const candles=asArray(chart?.daily_bars).filter(b=>b?.date<holdingCharts?.trade_date).slice(-5);
      const independent=holdingCharts?.trade_date===shanghaiDay()?asArray(chart?.intraday_points).filter(x=>x?.scan_at?.startsWith(holdingCharts.trade_date)):[]; 
      const dayScans=independent.length?independent:scans;
      const assessment=assessHoldingRisk(p,status.monitor==='OK'?monitor:null,shanghaiDay(),status.holdingSnapshot==='OK'?holdingSnapshot:null);
      return <button className="decision-row home-holding" key={p.code} onClick={()=>onSection('portfolio')}>
       <div className="decision-row-main"><strong>{p.name}</strong><small>{p.code} · {p.verified?p.shares+' 股':'持仓待核验'}</small></div>
       <div className="home-mini-chart home-holding-charts" title="左：最近5个完整交易日日K；右：今日真实盘中快照（非收盘价）">
        <div className="home-holding-chart"><span>近 5 日 K 线</span><MiniHoldingCandles bars={candles}/></div>
        <div className="home-holding-chart"><span>今日 {dayScans.length}/4</span><MiniHoldingIntraday rows={dayScans}/></div>
       </div>
       <div className="decision-row-meta"><span className={'holding-risk-brief risk-'+assessment.tone}>{assessment.label}</span><small>{assessment.last?'盘中快照 '+fmtTime(assessment.last.scan_at)+(assessment.rule.basis==='close'?' · 收盘确认制':''):'规则来自 Airtable · 等待有效行情'}</small></div><ChevronRight size={15}/>
      </button>
     })}</div>:<div className="decision-empty">暂无可核实的登记持仓。</div>}
   </section>
   <section className="decision-panel decision-market"><div className="decision-panel-top"><div><h2>正式趋势优先榜</h2><p>只展示 handoff 真实名次，不将其他趋势伪装为 TOP。</p></div><button className="text-link" onClick={()=>onSection('trends')}>全部趋势 <ArrowRight size={14}/></button></div>
    {status.trendHandoff!=='OK'?<div className="decision-empty">正式优先榜单尚不可用。</div>:official.length?<div className="decision-rows">
     {official.map(item=>{
       const scans=monitorCurrent?validSnapshots(history?.[item.trend_name],monitorDay):[];
       const d=snapshotChange(scans,'up_ratio',100);
       return <button className="decision-row home-sector" key={item.trend_name} onClick={()=>onSection('trends')}>
        <span className="decision-rank">{String(item.priorityRank).padStart(2,'0')}</span>
        <div className="decision-row-main"><strong>{item.trend_name}</strong><span className="home-sector-state"><ResearchState value={item.market_state}/><small>{item.trend_state}</small></span></div>
        <div className="home-mini-chart">{scans.length>=1?<SnapshotPlot rows={scans} field="up_ratio" label="上涨家数占比" bounds={[0,100]} scale={100} compact/>:<span className="plot-unavailable">等待盘中扫描</span>}</div>
        <div className="decision-row-meta home-sector-evidence">{scans.length?<div className={'home-alert-state state-'+tone(scans.at(-1).current_state)}><span className="state-dot"/>{scans.at(-1).current_state||'未定'}</div>:<span className="muted">暂无今日监测</span>}<small className={'intraday-breadth-change '+(d==null?'':d>0?'market-up':d<0?'market-down':'')}>{d==null?(scans.length===1?'首轮':'—'):signed(d,1)+' pp'}</small></div><ChevronRight size={15}/>
       </button>
     })}</div>:<div className="decision-empty">本期没有正式排名的板块。</div>}
   </section>
  </div>

  <section className="decision-feature">
   <div className="decision-panel-top"><div><h2>盘中真实变化</h2><p>板块看整体广度，个股每个已覆盖板块只展示一只冻结研究排序靠前的代表观察股；不是龙头评选或买入信号。</p></div><button className="text-link" onClick={openCurrentMonitor}>查看详细监测 <ArrowRight size={14}/></button></div>
   <div className="intraday-tab-switch" role="group" aria-label="市场总览盘中维度">
    <button type="button" aria-pressed={monitorUi.tab==='sector'} className={monitorUi.tab==='sector'?'active':''} onClick={()=>setMonitorUi(prev=>({...prev,tab:'sector'}))}>板块</button>
    <button type="button" aria-pressed={monitorUi.tab==='stock'} className={monitorUi.tab==='stock'?'active':''} onClick={()=>setMonitorUi(prev=>({...prev,tab:'stock'}))}>个股 · 每板块一只</button>
   </div>
   {!monitorCurrent?<div className="decision-empty">今日尚无有效盘中快照；不会用历史报价冒充当日变化。</div>:monitorUi.tab==='sector'?
    !active?<div className="decision-empty">当天尚未发布有效板块扫描。</div>:<>
     <div className="focus-switch">{monitored.map(item=><button key={item.name} className={item.name===active.name?'active':''} onClick={()=>setMonitorUi(prev=>({...prev,sector:item.name}))}>
      <strong>{item.name}</strong><span className={'focus-signal state-'+tone(item.scans.at(-1)?.current_state)}><span className="state-dot"/>{item.scans.at(-1)?.current_state||'未知'}</span><span className={item.delta==null?'':item.delta>0?'market-up':item.delta<0?'market-down':''}>{item.delta==null?'不足两轮':signed(item.delta,1)+' pp'}</span></button>)}</div>
     <div className="feature-plot-grid"><div className="feature-main-plot"><SnapshotPlot rows={active.scans} field="up_ratio" label="上涨家数占比" scale={100} bounds={[0,100]}/></div><div className="feature-side-plot"><SnapshotPlot rows={active.scans} field="median_change_pct" label="成分涨跌幅中位数"/></div></div>
     <div className="feature-caption"><span>{active.name} · 最新盘中状态 <b>{industryLatest?.current_state||'—'}</b> · 结构动量 <b>{industryLatest?.structure_momentum||'—'}</b></span><span>已扫描 {active.scans.length} 轮 · {fmtTime(monitor.last_scan_at)}</span></div>
    </>:
    !selectedRepresentative?<div className="decision-empty">当前板块尚无已发布的有效代表股快照；不会按涨幅临时选股。</div>:<>
     <div className="focus-switch home-representative-switch">{observed.map(item=><button key={item.code} className={item.code===selectedRepresentative.code?'active':''} onClick={()=>setMonitorUi(prev=>({...prev,stock:item.code,group:item.trend_name}))}>
      <strong>{item.trend_name}</strong><span>{item.company_name} · {item.code}</span>
      <span className={typeof item.last.relative_to_industry_pct==='number'?(item.last.relative_to_industry_pct>0?'market-up':item.last.relative_to_industry_pct<0?'market-down':''):''}>{typeof item.last.relative_to_industry_pct==='number'?signed(item.last.relative_to_industry_pct,2)+' pp':'相对行业暂无数据'}</span></button>)}</div>
     <div className="feature-plot-grid"><div className="feature-main-plot"><SnapshotPlot rows={selectedRepresentative.scans} field="price" label="盘中快照价格" unit="元"/></div><div className="feature-side-plot"><SnapshotPlot rows={selectedRepresentative.scans} field="relative_to_industry_pct" label="相对所属行业强度" unit=" pp"/></div></div>
     <div className="feature-caption"><span>{selectedRepresentative.company_name} · {selectedRepresentative.trend_name} · 盘中行为 <b>{selectedStockLast?.price_behavior||'—'}</b></span><span>冻结研究排序选取 · {fmtTime(selectedStockLast?.scan_at)} · 非买点建议</span></div>
    </>}
  </section>
  <section className="decision-panel decision-opportunity"><div className="decision-panel-top"><div><h2>正式买点机会</h2><p>只把 READY 列为待核对机会，WAIT 保留在完整榜单中。</p></div><button className="text-link" onClick={()=>onSection('buy')}>全部买点 <ArrowRight size={14}/></button></div>
   {status.buyHandoff!=='OK'?<div className="decision-empty">买点正式结果尚不可用。</div>:ready.length?<div className="decision-rows decision-entries">
    {ready.slice(0,3).map(item=><button key={item.code} className="decision-row" onClick={()=>{setSelectedBuy(item);onSection('buy')}}><div className="decision-row-main"><strong>{item.company_name}</strong><small>{item.code} · {item.trend_name}</small></div><Badge variant="ready">READY</Badge><div className="decision-row-meta"><span>{Array.isArray(item.entry_zone)?fixed(item.entry_zone[0])+' – '+fixed(item.entry_zone[1]):'等待入场计划'}</span><small>正式发布 · 非实时指令</small></div><ChevronRight size={15}/></button>)}
    </div>:<div className="decision-no-ready"><span className="decision-no-icon"><ShieldCheck size={20}/></span><div><strong>目前没有 READY 买点</strong><p>{waitCount} 只候选处于 WAIT，暂不将等待信号突出为机会。</p></div></div>}
  </section>
  <div className="decision-bottom"><span>图表均来自已发布快照：非分时行情，不自动推导买卖动作。</span><button onClick={()=>onSection('trends')}>查看完整研究池 <ArrowRight size={14}/></button></div>
 </div>;
}

function Trends({registry,trendHandoff,monitor,archive,selected,setSelected}){
 const [sortMode,setSortMode]=useState('state');
 const [detailView,setDetailView]=useState('chart');
 const day=monitor?.result_kind==='a_share_intraday_monitor_state'?monitor.trade_date:null;
 const rows=rankedTrendRows(registry,trendHandoff,monitor?.industry_history,day,sortMode);
 const officialCount=rows.filter(x=>x.priorityRank!=null).length;
 const focus=rows.find(i=>i.trend_name===selected?.trend_name)||rows[0];
 const plotRows=validSnapshots(monitor?.industry_history?.[focus?.trend_name],day);
 const detailTabs=[{id:'chart',label:'走势'},{id:'summary',label:'研判'},{id:'evidence',label:'证据'},{id:'history',label:'状态'},{id:'crossday',label:'跨日'}];
 return <><PageIntro title="板块趋势优先榜" desc="默认按市场状态排序，同状态内按正式 rank；也可切换正式名次或盘中广度变化。未上榜不虚构名次。" date={registry?.trade_date}/>
  <div className="ranking-explainer"><span><b>{officialCount}</b> 个正式优先方向</span><span><b>{rows.length}</b> 个研究池板块</span><span>盘中快照 {day||'未发布'}</span></div>
  <div className="two-pane trend-workspace"><section className="panel"><PanelHead title="板块排序" aside={<span className="count-chip">{rows.length} 个方向</span>}/>
   {rows.length?<TrendTable trends={rows} onSelect={setSelected} selected={focus} monitor={monitor?.industry_history} monitorDay={day} sortMode={sortMode} onSort={setSortMode}/>:<Empty title="暂无趋势数据" detail="等待正式趋势池发布"/>}
  </section>
  <section className="panel inspector inspector-tall sector-detail-pane" aria-label="板块详情">
   <div className="sector-detail-head"><div><strong>{focus?.trend_name||'选择板块'}</strong><span>{safeText(focus?.lifecycle_status)} · {day||'暂无盘中扫描'}</span></div><ResearchState value={focus?.market_state}/></div>
   <div className="sector-detail-tabs" role="group" aria-label="板块详情内容">
    {detailTabs.map(tab=><button key={tab.id} type="button" className={detailView===tab.id?'active':''} aria-pressed={detailView===tab.id} onClick={()=>setDetailView(tab.id)}>{tab.label}</button>)}
   </div>
   <div className="sector-detail-body" role="region" aria-label={detailTabs.find(tab=>tab.id===detailView)?.label+'详情'}>
    {detailView==='chart'&&<div className="sector-chart-inset sector-chart-focus"><p>上涨家数占比 · {day||'尚未发布盘中监测'}</p><SnapshotPlot rows={plotRows} field="up_ratio" label="上涨家数占比" scale={100} bounds={[0,100]}/></div>}
    {(detailView==='summary'||detailView==='evidence'||detailView==='history')&&<TrendInspector item={focus} view={detailView}/>}
    {detailView==='crossday'&&<div className="sector-crossday-inset"><CrossdayTimeline archive={archive} monitor={monitor} identifier={focus?.trend_name} kind="sector"/></div>}
   </div>
  </section>
  </div>
 </>;
}
function PageIntro({title,desc,date}){return <div className="page-intro"><div><h1>{title}</h1><p>{desc}</p></div>{date&&<div className="asof"><Clock3 size={14}/><span>数据交易日 <strong>{date}</strong></span></div>}</div>}
function BuyInspector({item}){
 if(!item)return <Empty title="选择一只候选股票" detail="查看已发布条件、观察参考与风险"/>;
 const waiting=item.status==='WAIT';
 const reference=waiting?item.watch_reference:null;
 const zone=waiting?reference?.reference_zone:item.entry_zone;
 const trigger=waiting?reference?.conditional_trigger:item.entry_trigger;
 const stop=waiting?reference?.invalidation_price:item.invalidation_price;
 return <div className="detail-content buy-inspector">
  <div className="detail-hero"><h2>{item.company_name}<span className="company-code">{item.code}</span></h2><div className="detail-badges"><Badge>{item.status}</Badge><ResearchState value={item.market_state}/></div></div>
  <div className="data-pair">
   <div><span>历史收盘参考价</span><strong className="big-number">{fixed(item.current_price)}</strong></div>
   <div><span>{waiting?'观察形态':'形态类型'}</span><strong>{safeText(waiting?reference?.setup_mode:item.setup_type)}</strong></div>
  </div>
  <div className="detail-section">
   <div className="small-heading"><Target size={15}/>{waiting?'观察参考区间（非买点）':'计划入场区间'}</div>
   <div className="entry-range">{Array.isArray(zone)? `${fixed(zone[0],3)} – ${fixed(zone[1],3)}`:waiting?'尚无可靠观察参考区间':'尚未形成有效入场区间'}</div>
   <p className="hint-text">{waiting?'观察条件：':'入场触发：'}{safeText(trigger)}</p>
  </div>
  <div className="data-pair">
   <div><span>{waiting?'观察触发参考价':'最大入场价'}</span><strong>{fixed(waiting?reference?.reference_trigger_price:item.max_entry_price,3)}</strong></div>
   <div><span>{waiting?'观察结构参考位':'结构失效参考'}</span><strong>{fixed(stop,3)}</strong></div>
  </div>
  <div className="detail-section"><div className="small-heading"><CircleAlert size={15}/> 当前判断</div><p className="reason-paragraph">{safeText(item.decision_reason)}</p></div>
  <div className="invalidation"><span>{waiting?'参考有效性':'失效规则'}</span><p>{waiting?`观察参考基于 ${item.trade_date||'上一交易日'} 的完成收盘数据；触及价位不等于买入，须重新确认行业状态、个股承接和风险。`:safeText(item.invalidation_rule)}</p></div>
  <div className="disclaimer">{waiting?'WAIT 不提供可执行入场计划，也不提供持仓止损指令。':'READY 仅为条件性计划，须核对最新有效行情，不是实时成交指令。'}</div>
 </div>
}
function Buy({buy,selected,setSelected,status}){const items=rankedBuyRows(asArray(buy?.items)); const [filter,setFilter]=useState('全部');const [query,setQuery]=useState('');const [group,setGroup]=useState('全部板块');const markets=[...new Set(items.map(i=>i.trend_name).filter(Boolean))]; const shown=items.filter(i=>(filter==='全部'||i.status===filter)&&(group==='全部板块'||i.trend_name===group)&&`${i.company_name||''}${i.code||''}`.includes(query));const focus=shown.find(i=>i.code===selected?.code)||shown[0];return <><PageIntro title="趋势买点观察" desc="READY 显示条件性入场计划；WAIT 只显示上一交易日观察参考，不代表当日可买。" date={buy?.trade_date}/><div className="buy-summary"><div><Badge>READY</Badge><strong>{items.filter(i=>i.status==='READY').length}</strong><span>条件满足候选</span></div><div><Badge>WAIT</Badge><strong>{items.filter(i=>i.status==='WAIT').length}</strong><span>等待确认</span></div><div><span className="muted">正式覆盖</span><strong>{items.length}</strong><span>已发布标的</span></div></div><div className="two-pane buy-workspace"><section className="panel"><PanelHead title="正式候选列表" aside={<span className="count-chip">{shown.length} 只</span>}/><div className="table-controls"><div className="search"><Search size={16}/><input placeholder="名称或股票代码" value={query} onChange={e=>setQuery(e.target.value)}/></div><div className="filter-select"><select value={filter} onChange={e=>setFilter(e.target.value)}><option>全部</option><option>READY</option><option>WAIT</option></select><ChevronDown size={13}/></div></div><div className="group-select"><SlidersHorizontal size={14}/><select value={group} onChange={e=>setGroup(e.target.value)}><option>全部板块</option>{markets.map(g=><option key={g}>{g}</option>)}</select></div>{items.length?<div className="table-wrap"><table className="data-table"><thead><tr><th>股票 / 代码</th><th>来源板块</th><th>参考价</th><th>信号</th><th/></tr></thead><tbody>{shown.map(item=><tr key={item.code} className={focus?.code===item.code?'row-selected':''} onClick={()=>setSelected(item)}><td><strong>{item.company_name}</strong><small className="mono">{item.code}</small></td><td className="soft-text">{item.trend_name}</td><td className="mono">{fixed(item.current_price)}</td><td><Badge>{item.status}</Badge></td><td><ChevronRight size={16}/></td></tr>)}</tbody></table>{!shown.length&&<Empty title="筛选后无候选" detail="尝试切换信号或板块" icon={Search}/>}</div>:<Empty title="买点榜尚未发布" detail={`数据状态：${formatSource(status.buyHandoff)}`}/>}<div className="table-footer">READY 优先，WAIT 其次；同状态按正式 rank 排序，原始名次不变 <span>交易日 {buy?.trade_date||'—'}</span></div></section><section className="panel inspector inspector-tall" tabIndex={0} aria-label="趋势买点详情，可独立滚动"><BuyInspector item={focus}/></section></div></>}

function Monitor({monitor,archive,status,monitorUi,setMonitorUi}){
 const valid=monitor?.result_kind==='a_share_intraday_monitor_state'&&status.monitor==='OK';
 const day=valid?monitor.trade_date:null;
 const historical=Boolean(day&&day!==shanghaiDay());
 const sectorNames=valid?Object.keys(monitor.industry_history||{}):[];
 const stockCodes=valid?Object.keys(monitor.stock_history||{}):[];
 const sector=sectorNames.includes(monitorUi.sector)?monitorUi.sector:sectorNames[0];
 const allSectors=sectorNames.map(name=>({name,rows:validSnapshots(monitor.industry_history[name],day)}));
 const allStocks=stockCodes.map(code=>({code,rows:validSnapshots(monitor.stock_history[code],day)}));
 const groupOptions=[...new Set(allStocks.map(item=>item.rows.at(-1)?.trend_name).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'zh-CN'));
 const effectiveGroup=groupOptions.includes(monitorUi.group)?monitorUi.group:'全部板块';
 const filteredStocks=allStocks.filter(item=>effectiveGroup==='全部板块'||item.rows.at(-1)?.trend_name===effectiveGroup);
 const filteredStockCodes=filteredStocks.map(item=>item.code);
 const stock=filteredStockCodes.includes(monitorUi.stock)?monitorUi.stock:filteredStockCodes[0];
 const sectorRows=validSnapshots(monitor?.industry_history?.[sector],day);
 const stockRows=validSnapshots(monitor?.stock_history?.[stock],day);
 const sectorLast=sectorRows.at(-1),stockLast=stockRows.at(-1);
 return <><PageIntro title="盘中监测 · 变化过程" desc="板块与个股切换查看已发布的真实盘中采样，不将离散快照视为分时行情。" date={day}/>
 {!valid?<section className="panel monitor-empty"><Empty title="暂无有效盘中监测" detail={'数据源状态：'+formatSource(status.monitor)+'，不推断买卖信号'} icon={Activity}/></section>:<>
 <div className="monitor-context"><span><Clock3 size={14}/> 最新扫描：{fmtTime(monitor.last_scan_at)}</span><span>行情快照：{fmtTime(monitor.snapshot_at)}</span><span className={historical?'monitor-history-label':''}>{historical?'历史交易日记录，非当前信号':'仅展示已发布的当日监测记录'}</span></div>
 <div className="intraday-tab-switch monitor-tab-switch" role="group" aria-label="盘中监测对象类型">
  <button type="button" aria-pressed={monitorUi.tab==='sector'} className={monitorUi.tab==='sector'?'active':''} onClick={()=>setMonitorUi(prev=>({...prev,tab:'sector'}))}>板块 <span>{sectorNames.length}</span></button>
  <button type="button" aria-pressed={monitorUi.tab==='stock'} className={monitorUi.tab==='stock'?'active':''} onClick={()=>setMonitorUi(prev=>({...prev,tab:'stock'}))}>个股 <span>{stockCodes.length}</span></button>
 </div>
 {monitorUi.tab==='sector'&& <section className="panel monitor-chart-panel">
  <div className="monitor-chart-top"><div><h2>板块盘中结构</h2><p>上下两张曲线使用各自真实单位，便于看出板块广度与涨幅中位数是否同步变化。</p></div></div>
  <div className="monitor-selector">{sectorNames.map(name=>{
   const scans=validSnapshots(monitor.industry_history[name],day),last=scans.at(-1);
   return <button key={name} className={sector===name?'active':''} onClick={()=>setMonitorUi(prev=>({...prev,sector:name}))}><strong>{name}</strong><span className="monitor-selector-state">{last?.current_state?<Badge>{last.current_state}</Badge>:'未有效扫描'} <small>{scans.length} 轮</small></span></button>
  })}</div>
  <div className="monitor-chart-pair"><SnapshotPlot rows={sectorRows} field="up_ratio" label="上涨家数占比" scale={100} bounds={[0,100]}/><SnapshotPlot rows={sectorRows} field="median_change_pct" label="成分涨跌幅中位数" /></div>
  <div className="monitor-latest">{sectorLast?<><span>最新状态 <Badge>{sectorLast.current_state||'—'}</Badge></span><span>结构动量 <Badge>{safeText(sectorLast.structure_momentum)}</Badge></span><span>空仓观察 <strong>{safeText(sectorLast.entry_action)}</strong></span><span>持仓管理 <strong>{safeText(sectorLast.holding_action)}</strong></span></>:<span>暂无有效判断</span>}</div>
  <CrossdayTimeline archive={archive} monitor={monitor} identifier={sector} kind="sector"/>
  <details className="monitor-more"><summary>更多板块数据 · 7 日累计背景、广度与覆盖率 <ChevronDown size={15}/></summary>
   <SevenSessionContext sector={sectorLast}/>
   {sectorLast&&<div className="monitor-stat-pairs">
     <div><small>上涨 / 下跌 / 平盘家数</small><strong>{safeText(sectorLast.up_count)} / {safeText(sectorLast.down_count)} / {safeText(sectorLast.flat_count)}</strong></div>
     <div><small>盘中报价覆盖率</small><strong>{typeof sectorLast.coverage_ratio==='number'?fixed(sectorLast.coverage_ratio*100,1)+'%':'—'}</strong></div>
     <div><small>最新结构动量</small><Badge>{sectorLast.structure_momentum||'—'}</Badge></div>
   </div>}
  </details>
  <details className="monitor-expand"><summary>查看 {sector||'板块'} 每轮状态与判断依据 <ChevronDown size={15}/></summary><SnapshotTimeline rows={sectorRows} kind="sector"/></details>
 </section>}
 {monitorUi.tab==='stock'&& <section className="panel monitor-chart-panel">
  <div className="monitor-chart-top"><div><h2>个股监测价格与相对强度</h2><p>价格只是当次快照报价；相对强度以相对行业百分点单独绘制。</p></div>
  <div className="monitor-stock-filters">
    <div className="monitor-stock-select"><label htmlFor="monitored-sector">按所属板块筛选</label><select id="monitored-sector" value={monitorUi.group||'全部板块'} onChange={e=>setMonitorUi(prev=>({...prev,group:e.target.value,stock:''}))}><option value="全部板块">全部板块</option>{groupOptions.map(group=><option value={group} key={group}>{group}</option>)}</select></div>
    <div className="monitor-stock-select"><label htmlFor="monitored-stock">选择监测标的（{filteredStocks.length}）</label><select id="monitored-stock" value={stock||''} onChange={e=>setMonitorUi(prev=>({...prev,stock:e.target.value}))}>{filteredStocks.map(item=><option key={item.code} value={item.code}>{item.rows.at(-1)?.company_name||item.code} · {item.code}</option>)}</select></div>
   </div></div>
  <div className="monitor-chart-pair"><SnapshotPlot rows={stockRows} field="price" label="盘中快照价" unit="元"/><SnapshotPlot rows={stockRows} field="relative_to_industry_pct" label="相对所属行业涨跌幅" unit=" pp" /></div>
  <div className="monitor-latest">{stockLast?<><span>个股 <strong>{stockLast.company_name||stock}</strong></span><span>行为 <Badge>{stockLast.price_behavior||'—'}</Badge></span><span>空仓观察 <strong>{safeText(stockLast.entry_action)}</strong></span><span>持仓管理 <strong>{safeText(stockLast.holding_action)}</strong></span></>:<span>该股票暂无有效快照</span>}</div>
  <CrossdayTimeline archive={archive} monitor={monitor} identifier={stock} kind="stock"/>
  <details className="monitor-more"><summary>更多个股数据 · 7 日累计背景、结构高低点 <ChevronDown size={15}/></summary>
   <SevenSessionContext stock={stockLast}/>
   {stockLast&&<div className="monitor-stat-pairs">
    <div><small>最近结构高点</small><strong>{typeof stockLast.latest_high?.price==='number'?fixed(stockLast.latest_high.price)+' 元':'—'}</strong></div>
    <div><small>最近结构低点</small><strong>{typeof stockLast.latest_low?.price==='number'?fixed(stockLast.latest_low.price)+' 元':'—'}</strong></div>
    <div><small>历史结构趋势 / 破位</small><strong>{safeText(stockLast.history_trend_state)} / {safeText(stockLast.history_break_state)}</strong></div>
   </div>}
  </details>
  <details className="monitor-expand"><summary>查看 {stockLast?.company_name||stock||'个股'} 每轮状态与判断依据 <ChevronDown size={15}/></summary><SnapshotTimeline rows={stockRows} kind="stock"/></details>
 </section>}
 <div className="decision-bottom"><span>榜单与状态来自已发布的盘中快照；切换 Tab 不改变监测结果、不生成新的交易信号。</span></div>
 </>}</>;
}
// Order by actionable evidence first, while keeping missing data distinct from safe observations.
const portfolioPriority = {triggered:0,pending:1,warning:2,watch:3,missing:4,unverified:4,stale:5,not_covered:5,no_price:5,unavailable:5,observing:6};
const portfolioAttention = new Set(['triggered','pending','warning','watch']);
const portfolioUnknown = new Set(['missing','unverified','stale','not_covered','no_price','unavailable']);
function portfolioStatus(assessment){
 const labels={triggered:'盘中条件触及',pending:'待收盘确认',warning:'低于预警价',watch:'盘中转弱',missing:'退出计划待完善',unverified:'持仓待核验',stale:'无当日扫描',not_covered:'未覆盖监测',no_price:'缺少有效报价',unavailable:'暂无有效数据',observing:'继续观察'};
 return {label:labels[assessment.state]||'暂不可判定',tone:portfolioAttention.has(assessment.state)?'caution':portfolioUnknown.has(assessment.state)?'unknown':'normal'};
}
function PortfolioPlan({position,assessment}){
 const levels=assessment.rule?.levels||[];
 return <div className="portfolio-tab-content">
  <div className="portfolio-signal"><span>最新规则状态</span><strong>{assessment.label}</strong></div>
  {levels.length>0?<div className="portfolio-levels">{levels.map((line,i)=>{
   const observation=line.observation==='below'?(line.kind==='warning'?'盘中低于预警线':assessment.rule.basis==='close'?'盘中低于 · 待收盘确认':'盘中条件触及'):line.observation==='not_below'?'盘中未低于':'等待有效当日行情';
   const action=line.action?(line.action==='减仓'?'计划减仓 '+line.quantity+' 股':'计划清仓剩余'):null;
   return <div className="portfolio-level-row" key={line.name+'-'+i}>
    <div><span>{line.name}</span><strong>{fixed(line.price,2)} <small>元</small></strong></div>
    <div><span>{action||'观察阈值'}</span><small>{observation}</small></div>
   </div>;
  })}</div>:<div className="portfolio-empty-rule"><ShieldAlert size={17}/><span>{position.planIssue||'尚无可用的结构化退出规则。'}</span></div>}
  <p className="portfolio-rule-description">{assessment.rule?.detail||'当前无可判定的结构化退出条件。'}</p>
  {position.riskPlan&&<div className="portfolio-plan-meta">
   <span>生效 {position.riskPlan.effectiveDate||'—'}</span><span>依据 {position.riskPlan.basis||'—'}触发</span>
  </div>}
  {position.riskPlan?.notes&&<div className="portfolio-plan-note"><strong>计划备注</strong><p>{position.riskPlan.notes}</p></div>}
 </div>;
}
function PortfolioEvidence({position,assessment}){
 return <div className="portfolio-tab-content">
  <div className="portfolio-signal"><span>当前评估状态</span><strong>{assessment.label}</strong></div>
  {assessment.evidence.length>0?<ul className="portfolio-evidence-list">{assessment.evidence.map((e,i)=><li key={i}>{e}</li>)}</ul>:<div className="portfolio-no-evidence"><CircleAlert size={17}/><span>暂无可核验的当日盘中证据，不能据此判断风险已经解除。</span></div>}
  {position.issues.length>0&&<div className="portfolio-evidence-issue"><strong>成交数据待核对</strong><p>{position.issues.join('；')}</p></div>}
  {position.planIssue&&<div className="portfolio-evidence-issue"><strong>风控计划状态</strong><p>{position.planIssue}</p></div>}
  <div className="portfolio-evidence-foot">
   <span>{assessment.last?'最近有效盘中快照：'+fmtTime(assessment.last.scan_at):'尚无该股票当日有效盘中快照'}</span>
   <p>{assessment.note||'风险提示仅依据已发布的同日行情，不等于自动交易指令。'}</p>
  </div>
 </div>;
}
function PortfolioTrades({position}){
 const trades=position.trades||[];
 return <div className="portfolio-tab-content">
  <div className="portfolio-trade-summary"><span>已登记成交流水</span><strong>共 {position.recordCount} 条</strong></div>
  {trades.length?<div className="portfolio-trades">{trades.slice().reverse().map((trade,index)=><div className="portfolio-trade" key={String(trade.date)+'-'+index}>
   <div><strong>{trade.date||'日期待核对'}</strong><small className={trade.kind==='buy'?'portfolio-buy':trade.kind==='sell'?'portfolio-sell':''}>{trade.kind==='buy'?'买入':trade.kind==='sell'?'卖出':'类型待核对'}</small></div>
   <div><strong>{trade.quantity==null?'股数待核对':trade.quantity.toLocaleString('zh-CN')+' 股'}</strong><small>成交价 {fixed(trade.price,3)} 元</small></div>
  </div>)}</div>:<div className="portfolio-no-evidence">暂无可显示的已登记成交记录。</div>}
  <p className="portfolio-trades-foot">按登记交易日期倒序展示，不推断同日交易先后；成本与持仓股数仍由原有核算逻辑计算。</p>
 </div>;
}
function Portfolio({data,status,monitor,holdingSnapshot}){
 const {positions,recordCount,invalidCount}=data;
 const ok=status.airtable==='OK';
 const [selectedCode,setSelectedCode]=useState(null);
 const [detailTab,setDetailTab]=useState('exit');
 const [listFilter,setListFilter]=useState('all');
 const today=shanghaiDay();
 const rows=useMemo(()=>positions.map(position=>({
  position,assessment:assessHoldingRisk(position,status.monitor==='OK'?monitor:null,today,status.holdingSnapshot==='OK'?holdingSnapshot:null)
 })).sort((a,b)=>(portfolioPriority[a.assessment.state]??5)-(portfolioPriority[b.assessment.state]??5)),[positions,monitor,status.monitor,today]);
 const attentionCount=rows.filter(row=>portfolioAttention.has(row.assessment.state)).length;
 const unverifiedCount=invalidCount+positions.filter(position=>!position.verified).length;
 const filtered=rows.filter(row=>listFilter==='attention'?portfolioAttention.has(row.assessment.state):listFilter==='verify'?portfolioUnknown.has(row.assessment.state):true);
 const selected=filtered.find(row=>row.position.code===selectedCode)||filtered[0];
 const tabs=[{id:'exit',label:'退出计划'},{id:'evidence',label:'风险依据'},{id:'trades',label:'成交记录'}];
 const changeFilter=value=>{setListFilter(value);setDetailTab('exit')};
 return <div className="portfolio-page">
  <PageIntro title="我的持仓" desc="先识别需要关注的持仓，再查看退出规则与证据。"/>
  {!ok?<section className="panel monitor-empty"><Empty title="Airtable 尚未接通网站" detail={status.airtable==='NOT_CONFIGURED'?'在 Vercel 设置 AIRTABLE_TOKEN、AIRTABLE_BASE_ID、AIRTABLE_TABLE_ID 后即可读取。':'当前状态：'+formatSource(status.airtable)+'；不会将读取失败解释为没有持仓。'} icon={Database}/></section>:<>
   <div className="portfolio-overview" aria-label="持仓概况">
    <div><span>已核实在持</span><strong>{positions.filter(p=>p.verified).length}</strong><small>可核实净持仓大于 0</small></div>
    <div><span>风险关注</span><strong>{attentionCount}</strong><small>依据已发布的同日监测</small></div>
    <div><span>数据待核验</span><strong>{unverifiedCount}</strong><small>异常记录或持仓股数</small></div>
   </div>
   <div className="portfolio-data-note"><LockKeyhole size={14}/><span>Airtable 私有成交流水 · 共 {recordCount} 条登记 · {monitor?.result_kind==='a_share_intraday_monitor_state'?'已获取盘中监测数据':'暂无有效盘中监测'} · 不展示未经核实的实时收益</span></div>
   {positions.length?<div className="portfolio-workspace">
    <section className="portfolio-list-panel" aria-label="持仓列表">
     <div className="portfolio-list-head"><div><h2>持仓列表</h2><small>按风险关注优先排列</small></div><span>{rows.length} 只</span></div>
     <div className="portfolio-filters" role="group" aria-label="持仓筛选">
      <button type="button" className={listFilter==='all'?'is-active':''} aria-pressed={listFilter==='all'} onClick={()=>changeFilter('all')}>全部</button>
      <button type="button" className={listFilter==='attention'?'is-active':''} aria-pressed={listFilter==='attention'} onClick={()=>changeFilter('attention')}>风险关注 {attentionCount}</button>
      <button type="button" className={listFilter==='verify'?'is-active':''} aria-pressed={listFilter==='verify'} onClick={()=>changeFilter('verify')}>无法判断 {rows.filter(row=>portfolioUnknown.has(row.assessment.state)).length}</button>
     </div>
     {filtered.length?<div className="portfolio-list">
      {filtered.map(row=>{
       const p=row.position,state=portfolioStatus(row.assessment);
       return <button type="button" key={p.code} className={'portfolio-list-row'+(selected?.position.code===p.code?' is-selected':'')} aria-pressed={selected?.position.code===p.code} onClick={()=>{setSelectedCode(p.code);setDetailTab('exit')}}>
        <div className="portfolio-row-top"><div className="portfolio-row-name"><strong>{p.name}</strong><span>{p.code}</span></div><span className={'portfolio-status portfolio-status-'+state.tone}>{state.label}</span></div>
        <div className="portfolio-row-bottom"><span>持仓 <strong>{p.shares==null?'待核验':p.shares.toLocaleString('zh-CN')+' 股'}</strong></span><span>均价 <strong>{fixed(p.avgCost,3)} 元</strong></span><ChevronRight size={15}/></div>
       </button>;
      })}
     </div>:<div className="portfolio-list-empty">当前筛选下暂无持仓记录。</div>}
    </section>
    {selected?<section className="portfolio-detail-panel" aria-label={selected.position.name+'持仓详情'}>
     <div className="portfolio-detail-head"><div><span>持仓详情 · {selected.position.code}</span><h2>{selected.position.name}</h2></div><span className={'portfolio-status portfolio-status-'+portfolioStatus(selected.assessment).tone}>{portfolioStatus(selected.assessment).label}</span></div>
     <div className="portfolio-position-stats">
      <div><span>登记股数</span><strong>{selected.position.shares==null?'待核验':selected.position.shares.toLocaleString('zh-CN')+' 股'}</strong></div>
      <div><span>剩余均价估算</span><strong>{fixed(selected.position.avgCost,3)} <small>元</small></strong></div>
      <div><span>剩余成本估算</span><strong>{fixed(selected.position.costValue)} <small>元</small></strong></div>
     </div>
     <div className="portfolio-detail-tabs" role="tablist" aria-label="持仓详情分类">
      {tabs.map(tab=><button type="button" role="tab" key={tab.id} id={'portfolio-tab-'+tab.id} aria-controls={'portfolio-panel-'+tab.id} aria-selected={detailTab===tab.id} className={detailTab===tab.id?'is-active':''} onClick={()=>setDetailTab(tab.id)}>{tab.label}</button>)}
     </div>
     <div className="portfolio-detail-body" role="tabpanel" id={'portfolio-panel-'+detailTab} aria-labelledby={'portfolio-tab-'+detailTab} key={selected.position.code+'-'+detailTab}>
      {detailTab==='exit'?<PortfolioPlan position={selected.position} assessment={selected.assessment}/>:detailTab==='evidence'?<PortfolioEvidence position={selected.position} assessment={selected.assessment}/>:<PortfolioTrades position={selected.position}/>}
     </div>
     <div className="portfolio-detail-foot"><span>最后登记交易日 {selected.position.lastDate||'—'}</span><span>已登记 {selected.position.recordCount} 笔成交</span></div>
    </section>:<section className="portfolio-detail-panel portfolio-detail-empty">该筛选下没有需要展示的持仓详情。</section>}
   </div>:<section className="panel"><Empty title="没有可核实的在持股票" detail={invalidCount?'仍有代码缺失的记录需要人工核验。':'已成功读取 Airtable，目前无可核实净持仓。'} icon={Wallet}/></section>}
  </>}
 </div>;
}

function Login({login,loading,error,setupError}) {
 const [password,setPassword]=useState('');
 const [showPassword,setShowPassword]=useState(false);
 return <div className="login-screen login-screen--terminal">
  <div className="login-visual" aria-hidden="true"/>
  <main className="login-panel-wrap">
   <section className="login-panel" aria-labelledby="login-title">
    <div className="login-panel-top">
     <div className="login-panel-brand">
      <img src="/favicon.svg" alt="" aria-hidden="true"/>
      <img src="/wordmark.svg" alt="识势 w.x."/>
     </div>
     <span className="login-panel-name">识势</span>
    </div>
    <div className="login-panel-rule" aria-hidden="true"/>
    <h1 id="login-title" className="login-panel-title">辨趋势之真伪<br/><span>顺市场之大势</span></h1>
    <form className="login-form" onSubmit={e=>{e.preventDefault();login(password)}}>
     <label className="login-sr-only" htmlFor="pass">访问密码</label>
     <div className="login-input">
      <LockKeyhole size={18} aria-hidden="true"/>
      <input id="pass" value={password} onChange={e=>setPassword(e.target.value)}
       placeholder="输入访问密码" type={showPassword?'text':'password'} autoComplete="current-password"
       minLength={1} required/>
      <button type="button" className="login-toggle-password" onClick={()=>setShowPassword(p=>!p)}
       aria-label={showPassword?'隐藏密码':'显示密码'} aria-pressed={showPassword}>
       {showPassword?<EyeOff size={18}/>:<Eye size={18}/>}
      </button>
     </div>
     {error&&<p className="login-error" role="alert"><CircleAlert size={15}/>{error}</p>}
     <button type="submit" className="login-submit" disabled={loading||!!setupError}>
      <span>{loading?'正在验证':'进入系统'}</span><ArrowRight size={18} aria-hidden="true"/>
     </button>
    </form>
    {setupError&&<div className="setup-warning" role="alert">站点尚未配置密码或会话密钥。请先配置 Vercel 环境变量。</div>}
   </section>
  </main>
 </div>;
}

export default function App(){
 const [authenticated,setAuthenticated]=useState(null),[setupError,setSetupError]=useState(false),[loginError,setLoginError]=useState(''),[loadingLogin,setLoadingLogin]=useState(false),[loading,setLoading]=useState(false),[payload,setPayload]=useState(null),[section,setSection]=useState('overview'),[menu,setMenu]=useState(false),[selectedTrend,setSelectedTrend]=useState(null),[selectedBuy,setSelectedBuy]=useState(null),[monitorUi,setMonitorUi]=useState({tab:'sector',sector:'',stock:'',group:'全部板块'});
 const fetchData=useCallback(async()=>{setLoading(true);try{const response=await fetch('/api/data',{cache:'no-store'});if(response.status===401){setAuthenticated(false);setPayload(null);return;}if(!response.ok)throw new Error(`数据接口 HTTP ${response.status}`);setPayload(await response.json());}catch(e){setPayload(old=>old?{...old,fetchError:e.message}:{datasets:{},status:{},fetchError:e.message});}finally{setLoading(false)}},[]);
 useEffect(()=>{let live=true;fetch('/api/auth',{cache:'no-store'}).then(async r=>{const j=await r.json();if(live){setAuthenticated(Boolean(j.authenticated));setSetupError(j.error==='SITE_NOT_CONFIGURED');}}).catch(()=>{if(live)setAuthenticated(false)});return()=>{live=false}},[]);
 useEffect(()=>{if(authenticated)fetchData()},[authenticated,fetchData]);
 const login=async password=>{setLoadingLogin(true);setLoginError('');try{const r=await fetch('/api/auth',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password})});if(!r.ok){setLoginError(r.status===503?'服务器尚未配置访问密钥':'密码错误或服务不可用');return;}setAuthenticated(true)}catch{setLoginError('服务暂时无法连接')}finally{setLoadingLogin(false)}};
 const logout=async()=>{try{await fetch('/api/auth',{method:'DELETE'})}finally{setAuthenticated(false);setPayload(null);setSection('overview')}};
 const openMonitor=patch=>{setMonitorUi(prev=>({...prev,...patch}));setSection('monitor')};
 const datasets=payload?.datasets||{}, status=payload?.status||{};
 const ledger=useMemo(()=>summarizeTrades(datasets.airtable),[datasets.airtable]);
 const portfolio=useMemo(()=>attachRiskPlans(ledger,datasets.riskPlans,status.riskPlans),[ledger,datasets.riskPlans,status.riskPlans]);
 if(authenticated===null)return <div className="boot-screen"><img className="brand-mark" src="/favicon.svg" alt="" aria-hidden="true"/><img className="brand-wordmark" src="/wordmark.svg" alt="识势 w.x."/><div className="spinner"/></div>;
 if(!authenticated)return <Login login={login} loading={loadingLogin} error={loginError} setupError={setupError}/>;
 return <div className="app-shell"><Sidebar section={section} onSection={setSection} openMenu={menu} setOpenMenu={setMenu} status={status}/><div className="main-shell"><Header section={section} refresh={fetchData} refreshing={loading} data={payload} openMenu={menu} setOpenMenu={setMenu} logout={logout}/><main className="main-content">{payload?.fetchError&&<div className="fetch-warning"><CircleAlert size={17}/>{payload.fetchError}，展示上次成功加载的数据。</div>}{!payload?<Skeleton/>:<div className="view-enter" key={section}>{section==='overview'&&<Overview registry={datasets.registry} trendHandoff={datasets.trendHandoff} buy={datasets.buyHandoff} monitor={datasets.monitor} holdingSnapshot={datasets.holdingSnapshot} holdingCharts={datasets.holdingCharts} portfolio={portfolio} status={status} onSection={setSection} setSelectedBuy={setSelectedBuy} monitorUi={monitorUi} setMonitorUi={setMonitorUi} openMonitor={openMonitor}/ >}{section==='trends'&&<Trends registry={datasets.registry} trendHandoff={datasets.trendHandoff} monitor={datasets.monitor} archive={datasets.crossdayArchive} selected={selectedTrend} setSelected={setSelectedTrend}/ >}{section==='buy'&&<Buy buy={datasets.buyHandoff} selected={selectedBuy} setSelected={setSelectedBuy} status={status}/ >}{section==='monitor'&&<Monitor monitor={datasets.monitor} archive={datasets.crossdayArchive} status={status} monitorUi={monitorUi} setMonitorUi={setMonitorUi}/ >}{section==='portfolio'&&<Portfolio data={portfolio} status={status} monitor={datasets.monitor} holdingSnapshot={datasets.holdingSnapshot}/>}{section==='validation'&&<TrendValidation summary={datasets.validationSummary} trends={datasets.validationTrends} stocks={datasets.validationStocks} status={status}/>}</div>}<footer className="main-footer"><span>w.x. · 识势</span><span>数据来自已发布的 GitHub 文件和私有 Airtable 记录 · 仅供研究参考，不构成交易建议</span><span>{payload?.receivedAt?`页面读取于 ${fmtTime(payload.receivedAt)}`:'等待同步'}</span></footer></main></div></div>;
}
