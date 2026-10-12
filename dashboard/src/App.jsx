import React, {useCallback, useEffect, useMemo, useState} from 'react';
import {
 Activity, ArrowDownRight, ArrowLeft, ArrowRight, ArrowUpRight, BarChart3, CalendarDays,
 Check, ChevronDown, ChevronRight, CircleAlert, Clock3, Command, Database,
 ExternalLink, Eye, GitBranch, Layers, LockKeyhole, LogOut, Menu,
 RefreshCw, Search, ShieldCheck, ShieldAlert, SlidersHorizontal,
 Sparkles, Target, Wallet, X, Zap, PanelLeftClose, ListFilter
} from 'lucide-react';
import {asArray, latestMonitorRecords, fixed, fmtTime, formatSource, pct, safeText, shanghaiDay, summarizeTrades, validSnapshots, snapshotChange, rankedTrendRows, seriesDirection, statusTone, trendEvents, archivedDays} from './model.js';

const sections = [
 {id:'overview',icon:BarChart3,title:'市场总览',en:'Overview'},
 {id:'trends',icon:Layers,title:'板块趋势',en:'Trend Radar'},
 {id:'buy',icon:Target,title:'趋势买点',en:'Entry Signals'},
 {id:'monitor',icon:Activity,title:'盘中监测',en:'Live Monitor'},
 {id:'portfolio',icon:Wallet,title:'我的持仓',en:'Portfolio'}
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
 return <header className="topbar"><div className="top-left"><button className="icon-button mobile-menu" onClick={()=>setOpenMenu(!openMenu)} aria-label="打开导航"><Menu size={20}/></button><span className="breadcrumb-muted">决策工作台</span><ChevronRight size={14} className="breadcrumb-chevron"/><strong>{active.title}</strong></div><div className="top-right"><div className="top-date"><CalendarDays size={15}/><span>{shanghaiDay()} · 北京时间</span></div><button type="button" className="header-btn" onClick={refresh} disabled={refreshing} aria-label={refreshing?"正在刷新数据":"手动刷新数据"} title="读取最新发布的数据"><RefreshCw size={15} className={refreshing?'spin':''}/><span>刷新数据</span></button><button type="button" className="icon-button logout" onClick={logout} title="退出登录" aria-label="退出登录"><LogOut size={18}/></button></div></header>;
}
function Sidebar({section,onSection,openMenu,setOpenMenu,status}){
 const navigate=id=>{onSection(id);setOpenMenu(false)};
 return <><div className={`sidebar-backdrop ${openMenu?'show':''}`} onClick={()=>setOpenMenu(false)}/><aside className={`sidebar ${openMenu?'open':''}`}><div className="brand"><img className="brand-mark" src="/favicon.svg" alt="" aria-hidden="true"/><div className="brand-identity"><img className="brand-wordmark" src="/wordmark.svg" alt="w.x."/><small>A 股决策中心</small></div><button className="icon-button mobile-close" onClick={()=>setOpenMenu(false)}><X size={18}/></button></div><div className="side-group-label">工作空间</div><nav className="side-nav">{sections.map(item=><button key={item.id} className={`nav-item ${section===item.id?'selected':''}`} aria-current={section===item.id?'page':undefined} onClick={()=>navigate(item.id)}><item.icon size={18}/><span>{item.title}</span>{item.id==='monitor' && status?.monitor!=='OK' && <span className="nav-signal"/>}{section===item.id && <div className="nav-active-line"/>}</button>)}</nav><div className="sidebar-spacer"/><div className="side-status"><div className="side-status-head"><span className="live-indicator"/>系统状态 <span className="side-status-tag">只读</span></div><div className="side-status-row"><span>GitHub 研究数据</span><strong className={status?.registry==='OK'?'status-good':'status-dim'}>{formatSource(status?.registry)}</strong></div><div className="side-status-row"><span>Airtable 持仓</span><strong className={status?.airtable==='OK'?'status-good':'status-dim'}>{formatSource(status?.airtable)}</strong></div><div className="side-status-divider"/><p>本看板只展示已发布结果，不自动生成交易信号。</p></div><div className="side-footer"><ShieldCheck size={15}/> PRIVATE INVESTOR DESK <span>v1.0</span></div></aside></>;
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
function TrendInspector({item}) {
 if(!item) return <Empty title="选择一个板块" detail="查看产业状态、支持证据与失效条件"/>;
 const evidence=asArray(item.supporting_evidence).slice(-2).reverse();
 const contrary=asArray(item.contrary_evidence).slice(-2).reverse();
 return <div className="detail-content"><div className="detail-hero"><h2>{item.trend_name}</h2><div className="detail-badges"><ResearchState value={item.market_state}/><Badge>{item.lifecycle_status}</Badge></div></div><div className="data-pair"><div><span>产业阶段</span><strong>{stageLabel(item.trend_state)}</strong></div><div><span>最近核验</span><strong>{safeText(item.last_verified_trade_date)}</strong></div></div><div className="detail-section"><div className="small-heading"><GitBranch size={15}/> 状态演变</div><HistoryStrip events={item.state_history}/></div><div className="detail-section"><div className="small-heading"><Check size={15}/> 支持证据</div>{evidence.length ? evidence.map((e,i)=><div className="evidence" key={i}><span className="evidence-date">{e.trade_date}</span><p>{e.description}</p>{/^https?:\/\//.test(e.source||'')&&<a href={e.source} target="_blank" rel="noopener noreferrer">查看依据 <ExternalLink size={12}/></a>}</div>):<p className="muted">没有已发布证据</p>}</div><div className="detail-section"><div className="small-heading"><ShieldAlert size={15}/> 反向证据</div>{contrary.length ? contrary.map((e,i)=><div className="evidence" key={i}><span className="evidence-date">{e.trade_date}</span><p>{e.description}</p></div>):<p className="muted">暂无记录</p>}</div><div className="invalidation"><span>失效观察条件</span><p>{safeText(item.invalidation_condition)}</p></div></div>;
}

const signed = (value,digits=1) => typeof value==='number' && Number.isFinite(value) ? (value>0?'+':'')+fixed(value,digits) : '—';

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
 {onSort&&<div className="filter-select"><select value={sortMode} onChange={e=>onSort(e.target.value)} aria-label="排序方式"><option value="formal">正式优先顺序</option><option value="change">当日广度变化幅度</option></select><ChevronDown size={13}/></div>}</div>
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

function Overview({registry,trendHandoff,buy,monitor,portfolio,status,onSection,setSelectedBuy}){
 const [focusSector,setFocusSector]=useState(null);
 const monitorCurrent=status.monitor==='OK'&&monitor?.result_kind==='a_share_intraday_monitor_state'&&monitor?.trade_date===shanghaiDay();
 const monitorDay=monitorCurrent?monitor.trade_date:null;
 const history=monitorCurrent?monitor.industry_history:{};
 const ranked=rankedTrendRows(registry,trendHandoff,history,monitorDay);
 const official=ranked.filter(x=>x.priorityRank!=null).slice(0,5);
 const monitored=Object.entries(history||{}).map(([name,historyRows])=>{
  const scans=validSnapshots(historyRows,monitorDay);
  return {name,scans,delta:snapshotChange(scans,'up_ratio',100)};
 }).filter(x=>x.scans.length).sort((a,b)=>Math.abs(b.delta??0)-Math.abs(a.delta??0));
 const active=monitored.find(x=>x.name===focusSector)||monitored[0];
 const industryLatest=active?.scans.at(-1);
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
    <button type="button" className="overview-brief-link" onClick={()=>onSection('monitor')}>查看监测 <ArrowRight size={13}/></button>
   </div>
  </div>
  <div className="decision-grid">
   <section className="decision-panel decision-portfolio"><div className="decision-panel-top"><div><h2>我的持仓</h2><p>只对已发布并被监测覆盖的持仓显示盘中价格快照。</p></div><button className="text-link" onClick={()=>onSection('portfolio')}>全部持仓 <ArrowRight size={14}/></button></div>
    {status.airtable!=='OK'?<div className="decision-empty">Airtable 当前不可用；不能确认持仓。</div>:positions.length?
     <div className="decision-rows">{positions.map(p=>{
      const scans=monitorCurrent?validSnapshots(monitor.stock_history?.[p.code],monitorDay):[];
      const last=scans.at(-1);
      return <button className="decision-row home-holding" key={p.code} onClick={()=>onSection('portfolio')}>
       <div className="decision-row-main"><strong>{p.name}</strong><small>{p.code} · {p.verified?p.shares+' 股':'持仓待核验'}</small></div>
       <div className="home-mini-chart">{scans.length>=2?<SnapshotPlot rows={scans} field="price" label="盘中快照价" unit="元" compact/>:<span className="plot-unavailable">暂无价格曲线</span>}</div>
       <div className="decision-row-meta"><span>{!p.verified?'记录待核验':!monitorCurrent?'无今日监测':!last?'未被监测覆盖':last.holding_action||'暂无盘中持仓结论'}</span><small>{last?'最近扫描 '+fmtTime(last.scan_at)+' · Airtable 已登记':p.conditions.length?'已记录失效观察条件':'待补充退出条件'}</small></div><ChevronRight size={15}/>
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
        <div className="home-mini-chart">{scans.length>=2?<SnapshotPlot rows={scans} field="up_ratio" label="上涨家数占比" bounds={[0,100]} scale={100} compact/>:<span className="plot-unavailable">等待盘中扫描</span>}</div>
        <div className="decision-row-meta home-sector-evidence">{scans.length?<div className={'home-alert-state state-'+tone(scans.at(-1).current_state)}><span className="state-dot"/>{scans.at(-1).current_state||'未定'}</div>:<span className="muted">暂无今日监测</span>}<small className={'intraday-breadth-change '+(d==null?'':d>0?'market-up':d<0?'market-down':'')}>{d==null?'—':signed(d,1)+' pp'}</small></div><ChevronRight size={15}/>
       </button>
     })}</div>:<div className="decision-empty">本期没有正式排名的板块。</div>}
   </section>
  </div>
  <section className="decision-feature">
   <div className="decision-panel-top"><div><h2>盘中真实变化</h2><p>按当天上涨家数占比变化绝对值排列观察对象；这是展示顺序，不是模型强弱评分。</p></div><button className="text-link" onClick={()=>onSection('monitor')}>查看全部监测 <ArrowRight size={14}/></button></div>
   {!monitorCurrent||!active?<div className="decision-empty">今日尚无有效盘中快照；不会拿历史数据冒充实时曲线。</div>:<>
    <div className="focus-switch">{monitored.map(item=><button key={item.name} className={item.name===active.name?'active':''} onClick={()=>setFocusSector(item.name)}>
      <strong>{item.name}</strong><span className={'focus-signal state-'+tone(item.scans.at(-1)?.current_state)}><span className="state-dot"/>{item.scans.at(-1)?.current_state||'未知'}</span><span className={item.delta==null?'':item.delta>0?'market-up':item.delta<0?'market-down':''}>{item.delta==null?'不足两轮':signed(item.delta,1)+' pp'}</span></button>)}</div>
    <div className="feature-plot-grid"><div className="feature-main-plot"><SnapshotPlot rows={active.scans} field="up_ratio" label="上涨家数占比" scale={100} bounds={[0,100]}/></div><div className="feature-side-plot"><SnapshotPlot rows={active.scans} field="median_change_pct" label="成分涨跌幅中位数" /></div></div>
    <div className="feature-caption"><span>{active.name} · 最新盘中状态 <b>{industryLatest?.current_state||'—'}</b> · 结构动量 <b>{industryLatest?.structure_momentum||'—'}</b></span><span>来源 {monitor.trade_date} · 已扫描 {active.scans.length} 轮</span></div>
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
 const [sortMode,setSortMode]=useState('formal');
 const day=monitor?.result_kind==='a_share_intraday_monitor_state'?monitor.trade_date:null;
 const rows=rankedTrendRows(registry,trendHandoff,monitor?.industry_history,day,sortMode);
 const officialCount=rows.filter(x=>x.priorityRank!=null).length;
 const focus=rows.find(i=>i.trend_name===selected?.trend_name)||rows[0];
 const plotRows=validSnapshots(monitor?.industry_history?.[focus?.trend_name],day);
 return <><PageIntro title="板块趋势优先榜" desc="正式优先榜 rank 置顶；可切换按当日真实广度变化幅度排序。未上榜板块不被虚构名次。" date={registry?.trade_date}/>
  <div className="ranking-explainer"><span><b>{officialCount}</b> 个正式优先方向</span><span><b>{rows.length}</b> 个研究池板块</span><span>盘中快照 {day||'未发布'}</span></div>
  <div className="two-pane trend-workspace"><section className="panel"><PanelHead title="板块排序" aside={<span className="count-chip">{rows.length} 个方向</span>}/>
   {rows.length?<TrendTable trends={rows} onSelect={setSelected} selected={focus} monitor={monitor?.industry_history} monitorDay={day} sortMode={sortMode} onSort={setSortMode}/>:<Empty title="暂无趋势数据" detail="等待正式趋势池发布"/>}
  </section>
  <section className="panel inspector inspector-tall"><div className="sector-chart-inset"><strong>{focus?.trend_name||'选择板块'}</strong><p>上涨家数占比 · {day||'尚未发布盘中监测'}</p><SnapshotPlot rows={plotRows} field="up_ratio" label="上涨家数占比" scale={100} bounds={[0,100]}/><CrossdayTimeline archive={archive} monitor={monitor} identifier={focus?.trend_name} kind="sector"/></div><TrendInspector item={focus}/></section>
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
function Buy({buy,selected,setSelected,status}){const items=asArray(buy?.items); const [filter,setFilter]=useState('全部');const [query,setQuery]=useState('');const [group,setGroup]=useState('全部板块');const markets=[...new Set(items.map(i=>i.trend_name).filter(Boolean))]; const shown=items.filter(i=>(filter==='全部'||i.status===filter)&&(group==='全部板块'||i.trend_name===group)&&`${i.company_name||''}${i.code||''}`.includes(query));const focus=items.find(i=>i.code===selected?.code)||shown[0];return <><PageIntro title="趋势买点观察" desc="READY 显示条件性入场计划；WAIT 只显示上一交易日观察参考，不代表当日可买。" date={buy?.trade_date}/><div className="buy-summary"><div><Badge>READY</Badge><strong>{items.filter(i=>i.status==='READY').length}</strong><span>条件满足候选</span></div><div><Badge>WAIT</Badge><strong>{items.filter(i=>i.status==='WAIT').length}</strong><span>等待确认</span></div><div><span className="muted">正式覆盖</span><strong>{items.length}</strong><span>已发布标的</span></div></div><div className="two-pane"><section className="panel"><PanelHead title="正式候选列表" aside={<span className="count-chip">{shown.length} 只</span>}/><div className="table-controls"><div className="search"><Search size={16}/><input placeholder="名称或股票代码" value={query} onChange={e=>setQuery(e.target.value)}/></div><div className="filter-select"><select value={filter} onChange={e=>setFilter(e.target.value)}><option>全部</option><option>READY</option><option>WAIT</option></select><ChevronDown size={13}/></div></div><div className="group-select"><SlidersHorizontal size={14}/><select value={group} onChange={e=>setGroup(e.target.value)}><option>全部板块</option>{markets.map(g=><option key={g}>{g}</option>)}</select></div>{items.length?<div className="table-wrap"><table className="data-table"><thead><tr><th>股票 / 代码</th><th>来源板块</th><th>参考价</th><th>信号</th><th/></tr></thead><tbody>{shown.map(item=><tr key={item.code} className={focus?.code===item.code?'row-selected':''} onClick={()=>setSelected(item)}><td><strong>{item.company_name}</strong><small className="mono">{item.code}</small></td><td className="soft-text">{item.trend_name}</td><td className="mono">{fixed(item.current_price)}</td><td><Badge>{item.status}</Badge></td><td><ChevronRight size={16}/></td></tr>)}</tbody></table>{!shown.length&&<Empty title="筛选后无候选" detail="尝试切换信号或板块" icon={Search}/>}</div>:<Empty title="买点榜尚未发布" detail={`数据状态：${formatSource(status.buyHandoff)}`}/>}<div className="table-footer">正式排名不因页面筛选而改变 <span>交易日 {buy?.trade_date||'—'}</span></div></section><section className="panel inspector inspector-tall"><BuyInspector item={focus}/></section></div></>}

function Monitor({monitor,archive,status}){
 const [sectorName,setSectorName]=useState(''),[stockCode,setStockCode]=useState('');
 const valid=monitor?.result_kind==='a_share_intraday_monitor_state' && status.monitor==='OK';
 const day=valid?monitor.trade_date:null;
 const historical=day&&day!==shanghaiDay();
 const sectorNames=valid?Object.keys(monitor.industry_history||{}):[];
 const stockCodes=valid?Object.keys(monitor.stock_history||{}):[];
 const sector=sectorNames.includes(sectorName)?sectorName:sectorNames[0];
 const stock=stockCodes.includes(stockCode)?stockCode:stockCodes[0];
 const sectorRows=validSnapshots(monitor?.industry_history?.[sector],day);
 const stockRows=validSnapshots(monitor?.stock_history?.[stock],day);
 const sectorLast=sectorRows.at(-1),stockLast=stockRows.at(-1);
 const allSectors=sectorNames.map(name=>({name,rows:validSnapshots(monitor.industry_history[name],day)}));
 const allStocks=stockCodes.map(code=>({code,rows:validSnapshots(monitor.stock_history[code],day)}));
 return <><PageIntro title="盘中监测 · 变化过程" desc="真实采样点逐轮连接，不将两轮补成四轮，不把盘中价格线当成分时行情。" date={day}/>
 {!valid?<section className="panel monitor-empty"><Empty title="暂无有效盘中监测" detail={'数据源状态：'+formatSource(status.monitor)+'，不推断买卖信号'} icon={Activity}/></section>:<>
 <div className="monitor-context"><span><Clock3 size={14}/> 最新扫描：{fmtTime(monitor.last_scan_at)}</span><span>行情快照：{fmtTime(monitor.snapshot_at)}</span><span className={historical?'monitor-history-label':''}>{historical?'历史交易日记录，非当前信号':'仅展示已发布的当日监测记录'}</span></div>
 <section className="panel monitor-chart-panel">
  <div className="monitor-chart-top"><div><h2>板块盘中结构</h2><p>上下两张曲线使用各自真实单位，便于看出板块广度与涨幅中位数是否同步变化。</p></div></div>
  <div className="monitor-selector">{sectorNames.map(name=>{
   const scans=validSnapshots(monitor.industry_history[name],day),last=scans.at(-1);
   return <button key={name} className={sector===name?'active':''} onClick={()=>setSectorName(name)}><strong>{name}</strong><span className="monitor-selector-state">{last?.current_state?<Badge>{last.current_state}</Badge>:'未有效扫描'} <small>{scans.length} 轮</small></span></button>
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
 </section>
 <section className="panel monitor-chart-panel">
  <div className="monitor-chart-top"><div><h2>个股监测价格与相对强度</h2><p>价格只是当次快照报价；相对强度以相对行业百分点单独绘制。</p></div>
  <div className="monitor-stock-select"><label htmlFor="monitored-stock">选择监测标的</label><select id="monitored-stock" value={stock||''} onChange={e=>setStockCode(e.target.value)}>{allStocks.map(item=><option key={item.code} value={item.code}>{item.rows.at(-1)?.company_name||item.code} · {item.code}</option>)}</select></div></div>
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
 </section>
 <details className="panel monitor-all-list"><summary>浏览所有已覆盖板块与个股 <ChevronDown size={16}/></summary><div className="monitor-coverage"><div><h3>板块（{allSectors.length}）</h3>{allSectors.map(item=><button key={item.name} onClick={()=>setSectorName(item.name)}><span>{item.name}</span><small>{item.rows.at(-1)?.current_state||'无记录'}</small></button>)}</div><div><h3>个股（{allStocks.length}）</h3>{allStocks.map(item=><button key={item.code} onClick={()=>setStockCode(item.code)}><span>{item.rows.at(-1)?.company_name||item.code}</span><small>{item.rows.at(-1)?.price_behavior||'无记录'}</small></button>)}</div></div></details>
 <div className="decision-bottom"><span>状态由既有盘中监测任务输出；曲线不产生额外买卖或结构失效判断。</span></div>
 </>}</>;
}
function Portfolio({data,status,monitor}){const {positions,recordCount,invalidCount}=data;const ok=status.airtable==='OK';return <><PageIntro title="个人持仓记录" desc="Airtable 仅用于核验登记交易与退出规则，不作为实时市场行情源。"/><div className="monitor-note privacy-note"><LockKeyhole size={18}/><div><strong>个人数据仅经受保护的服务端接口读取</strong><p>不会写入公开 GitHub 仓库；未取得行情与收盘确认时，不计算实时收益或自动给出卖出指令。</p></div></div>{!ok?<section className="panel monitor-empty"><Empty title="Airtable 尚未接通网站" detail={status.airtable==='NOT_CONFIGURED'?'在 Vercel 设置 AIRTABLE_TOKEN、AIRTABLE_BASE_ID、AIRTABLE_TABLE_ID 后即可读取。':`当前状态：${formatSource(status.airtable)}；不会将读取失败解释为没有持仓。`} icon={Database}/></section>:<><div className="metrics-grid portfolio-metrics"><Metric label="记录交易" value={recordCount} icon={Database} meta="Airtable 原始条目"/><Metric label="登记在持" value={positions.filter(p=>p.verified).length} icon={Wallet} accent="green" meta="可核实净持仓 > 0"/><Metric label="待核对记录" value={invalidCount+positions.filter(p=>!p.verified).length} icon={ShieldAlert} accent="amber" meta="不可据此生成交易动作"/><Metric label="行情联动" value={monitor?.result_kind==='a_share_intraday_monitor_state'?'有监测数据':'尚未就绪'} icon={Activity} accent="purple" meta="仅已发布的盘中快照"/></div><section className="panel"><PanelHead title="登记持仓清单" aside={<span className="count-chip">{positions.length} 条待关注</span>}/>{positions.length?<div className="portfolio-grid">{positions.map(p=><article key={p.code} className="position-card"><div className="position-heading"><div><div className="eyebrow">{p.code}</div><h3>{p.name}</h3></div><Badge variant={p.verified?'verified':'caution'}>{p.verified?'已核实股数':'待核验'}</Badge></div><div className="position-numbers"><div><span>登记股数</span><strong>{p.shares==null?'待确认':p.shares.toLocaleString('zh-CN')}</strong></div><div><span>剩余均价估算</span><strong>{fixed(p.avgCost,3)}</strong></div><div><span>剩余成本估算</span><strong>{fixed(p.costValue)}</strong></div></div><div className="position-rule"><span><ShieldAlert size={14}/> 记录的失效条件</span><p>{p.conditions.length===1?p.conditions[0]:p.conditions.length>1?'存在多条不同条件，需人工核验':'尚未记录明确失效条件'}</p></div>{p.issues.length>0&&<div className="issue-text">{p.issues.join('；')}</div>}<div className="position-foot">最后登记交易日 <b>{p.lastDate||'—'}</b><span>共 {p.recordCount} 条成交记录</span></div></article>)}</div>:<Empty title="没有可核实的在持股票" detail={invalidCount?'仍有代码缺失的记录需要人工核验。':'已成功读取 Airtable，目前无可核实净持仓。'} icon={Wallet}/>}</section></>}</>}
function Login({login,loading,error,setupError}){const [password,setPassword]=useState('');return <div className="login-screen"><div className="login-glow"/><div className="login-shell"><div className="login-brand"><img className="brand-mark" src="/favicon.svg" alt="" aria-hidden="true"/><img className="brand-wordmark" src="/wordmark.svg" alt="w.x."/></div><div className="login-eyebrow">PRIVATE MARKET WORKSPACE</div><h1>看清趋势，<br/><span>从容决策。</span></h1><p className="login-description">你的 A 股市场研究与个人持仓决策工作台。一个页面，掌握所有重要信息。</p><form onSubmit={e=>{e.preventDefault();login(password)}}><label htmlFor="pass">访问密码</label><div className="password-control"><LockKeyhole size={19}/><input id="pass" value={password} onChange={e=>setPassword(e.target.value)} placeholder="输入看板访问密码" type="password" autoComplete="current-password" minLength={1} required/></div>{error&&<p className="login-error"><CircleAlert size={15}/>{error}</p>}<button type="submit" className="primary-btn" disabled={loading||!!setupError}>{loading?'验证中...':'进入工作台'} <ArrowRight size={17}/></button></form>{setupError&&<div className="setup-warning">站点尚未配置密码或会话密钥。请先配置 Vercel 环境变量。</div>}<div className="login-footer"><ShieldCheck size={15}/> READ ONLY · PRIVATE BY DESIGN</div></div><div className="login-art"><div className="login-art-box"><div className="login-art-title"><span className="live-indicator"/> SIGNAL DISCIPLINE</div><div className="login-art-line">OBSERVE <span>→</span> VERIFY <span>→</span> DECIDE</div><div className="login-art-graph"><svg viewBox="0 0 440 190" preserveAspectRatio="none"><defs><linearGradient id="lg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#68d5bb" stopOpacity=".26"/><stop offset="1" stopColor="#68d5bb" stopOpacity="0"/></linearGradient></defs><path d="M0 150 L40 144 L75 148 L110 104 L151 111 L187 83 L223 101 L253 68 L282 73 L322 44 L363 55 L399 23 L440 12 L440 190 L0 190Z" fill="url(#lg)"/><path d="M0 150 L40 144 L75 148 L110 104 L151 111 L187 83 L223 101 L253 68 L282 73 L322 44 L363 55 L399 23 L440 12" stroke="#67dcc0" strokeWidth="2.5" fill="none"/></svg></div><div className="art-bottom"><span>MARKET<br/>INTELLIGENCE</span><strong>01 — 05</strong></div></div><span className="mock-warning">装饰性图形 · 非实际行情</span></div></div>}
export default function App(){
 const [authenticated,setAuthenticated]=useState(null),[setupError,setSetupError]=useState(false),[loginError,setLoginError]=useState(''),[loadingLogin,setLoadingLogin]=useState(false),[loading,setLoading]=useState(false),[payload,setPayload]=useState(null),[section,setSection]=useState('overview'),[menu,setMenu]=useState(false),[selectedTrend,setSelectedTrend]=useState(null),[selectedBuy,setSelectedBuy]=useState(null);
 const fetchData=useCallback(async()=>{setLoading(true);try{const response=await fetch('/api/data',{cache:'no-store'});if(response.status===401){setAuthenticated(false);setPayload(null);return;}if(!response.ok)throw new Error(`数据接口 HTTP ${response.status}`);setPayload(await response.json());}catch(e){setPayload(old=>old?{...old,fetchError:e.message}:{datasets:{},status:{},fetchError:e.message});}finally{setLoading(false)}},[]);
 useEffect(()=>{let live=true;fetch('/api/auth',{cache:'no-store'}).then(async r=>{const j=await r.json();if(live){setAuthenticated(Boolean(j.authenticated));setSetupError(j.error==='SITE_NOT_CONFIGURED');}}).catch(()=>{if(live)setAuthenticated(false)});return()=>{live=false}},[]);
 useEffect(()=>{if(authenticated)fetchData()},[authenticated,fetchData]);
 const login=async password=>{setLoadingLogin(true);setLoginError('');try{const r=await fetch('/api/auth',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password})});if(!r.ok){setLoginError(r.status===503?'服务器尚未配置访问密钥':'密码错误或服务不可用');return;}setAuthenticated(true)}catch{setLoginError('服务暂时无法连接')}finally{setLoadingLogin(false)}};
 const logout=async()=>{try{await fetch('/api/auth',{method:'DELETE'})}finally{setAuthenticated(false);setPayload(null);setSection('overview')}};
 const datasets=payload?.datasets||{}, status=payload?.status||{};
 const portfolio=useMemo(()=>summarizeTrades(datasets.airtable),[datasets.airtable]);
 if(authenticated===null)return <div className="boot-screen"><img className="brand-mark" src="/favicon.svg" alt="" aria-hidden="true"/><img className="brand-wordmark" src="/wordmark.svg" alt="w.x."/><div className="spinner"/></div>;
 if(!authenticated)return <Login login={login} loading={loadingLogin} error={loginError} setupError={setupError}/>;
 return <div className="app-shell"><Sidebar section={section} onSection={setSection} openMenu={menu} setOpenMenu={setMenu} status={status}/><div className="main-shell"><Header section={section} refresh={fetchData} refreshing={loading} data={payload} openMenu={menu} setOpenMenu={setMenu} logout={logout}/><main className="main-content">{payload?.fetchError&&<div className="fetch-warning"><CircleAlert size={17}/>{payload.fetchError}，展示上次成功加载的数据。</div>}{!payload?<Skeleton/>:<div className="view-enter" key={section}>{section==='overview'&&<Overview registry={datasets.registry} trendHandoff={datasets.trendHandoff} buy={datasets.buyHandoff} monitor={datasets.monitor} portfolio={portfolio} status={status} onSection={setSection} setSelectedBuy={setSelectedBuy}/ >}{section==='trends'&&<Trends registry={datasets.registry} trendHandoff={datasets.trendHandoff} monitor={datasets.monitor} archive={datasets.crossdayArchive} selected={selectedTrend} setSelected={setSelectedTrend}/ >}{section==='buy'&&<Buy buy={datasets.buyHandoff} selected={selectedBuy} setSelected={setSelectedBuy} status={status}/ >}{section==='monitor'&&<Monitor monitor={datasets.monitor} archive={datasets.crossdayArchive} status={status}/ >}{section==='portfolio'&&<Portfolio data={portfolio} status={status} monitor={datasets.monitor}/>}</div>}<footer className="main-footer"><span>w.x. MARKET DESK</span><span>数据来自已发布的 GitHub 文件和私有 Airtable 记录 · 仅供研究参考，不构成交易建议</span><span>{payload?.receivedAt?`页面读取于 ${fmtTime(payload.receivedAt)}`:'等待同步'}</span></footer></main></div></div>;
}
