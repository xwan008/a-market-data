import React, {useCallback, useEffect, useMemo, useState} from 'react';
import {
 Activity, ArrowDownRight, ArrowLeft, ArrowRight, ArrowUpRight, BarChart3, CalendarDays,
 Check, ChevronDown, ChevronRight, CircleAlert, Clock3, Command, Database,
 ExternalLink, Eye, GitBranch, Layers, LockKeyhole, LogOut, Menu,
 RefreshCw, Search, ShieldCheck, ShieldAlert, SlidersHorizontal,
 Sparkles, Target, TrendingUp, Wallet, X, Zap, PanelLeftClose, ListFilter
} from 'lucide-react';
import {asArray, latestMonitorRecords, fixed, fmtTime, formatSource, pct, safeText, shanghaiDay, summarizeTrades, validSnapshots, snapshotChange, rankedTrendRows} from './model.js';

const sections = [
 {id:'overview',icon:BarChart3,title:'市场总览',en:'Overview'},
 {id:'trends',icon:Layers,title:'板块趋势',en:'Trend Radar'},
 {id:'buy',icon:Target,title:'趋势买点',en:'Entry Signals'},
 {id:'monitor',icon:Activity,title:'盘中监测',en:'Live Monitor'},
 {id:'portfolio',icon:Wallet,title:'我的持仓',en:'Portfolio'}
];
const tone = value => {
 if (value === 'READY' || value === '趋势确认' || value === '有效' || value === '正常') return 'good';
 if (/失效|衰退|退化|暂停|破位/.test(String(value))) return 'bad';
 if (/WAIT|分歧|候选|待复核|观察|修复/.test(String(value))) return 'warn';
 return 'neutral';
};
const stageLabel = s => ({T1:'T1 · 早期趋势',T2:'T2 · 产业阶段',T3:'T3 · 成熟阶段'}[s]||safeText(s));
function Badge({children,variant}) {return <span className={`badge badge-${variant||tone(children)}`}><span className="badge-dot"/>{children}</span>}
function MiniDot({active=false}) {return <span className={`mini-dot ${active?'mini-dot-active':''}`}/>}
function PanelHead({label,title,aside,children}) {return <div className="panel-head"><div><div className="eyebrow">{label}</div><h3>{title}</h3>{children}</div>{aside}</div>}
function Empty({title,detail,icon:Icon=CircleAlert}) {return <div className="empty"><div className="empty-icon"><Icon size={23}/></div><strong>{title}</strong><p>{detail}</p></div>}
function Skeleton(){return <div className="skeleton-page"><div className="skeleton skeleton-title"/><div className="skeleton-grid">{[1,2,3].map(n=><div className="skeleton skeleton-card" key={n}/>)}</div><div className="skeleton skeleton-panel"/></div>}
function Header({section,refresh,refreshing,data,openMenu,setOpenMenu,logout}) {
 const active=sections.find(x=>x.id===section)||sections[0];
 return <header className="topbar"><div className="top-left"><button className="icon-button mobile-menu" onClick={()=>setOpenMenu(!openMenu)} aria-label="打开导航"><Menu size={20}/></button><span className="breadcrumb-muted">决策工作台</span><ChevronRight size={14} className="breadcrumb-chevron"/><strong>{active.title}</strong></div><div className="top-right"><div className="top-date"><CalendarDays size={15}/><span>{shanghaiDay()} · 北京时间</span></div><button type="button" className="header-btn" onClick={refresh} disabled={refreshing} aria-label={refreshing?"正在刷新数据":"手动刷新数据"} title="读取最新发布的数据"><RefreshCw size={15} className={refreshing?'spin':''}/><span>刷新数据</span></button><button type="button" className="icon-button logout" onClick={logout} title="退出登录" aria-label="退出登录"><LogOut size={18}/></button></div></header>;
}
function Sidebar({section,onSection,openMenu,setOpenMenu,status}){
 const navigate=id=>{onSection(id);setOpenMenu(false)};
 return <><div className={`sidebar-backdrop ${openMenu?'show':''}`} onClick={()=>setOpenMenu(false)}/><aside className={`sidebar ${openMenu?'open':''}`}><div className="brand"><div className="brand-mark"><TrendingUp size={24} strokeWidth={2.6}/></div><div><strong>岚图 <span>LAN TU</span></strong><small>MARKET INTELLIGENCE</small></div><button className="icon-button mobile-close" onClick={()=>setOpenMenu(false)}><X size={18}/></button></div><div className="side-group-label">WORKSPACE <span>工作空间</span></div><nav className="side-nav">{sections.map(item=><button key={item.id} className={`nav-item ${section===item.id?'selected':''}`} aria-current={section===item.id?'page':undefined} onClick={()=>navigate(item.id)}><item.icon size={18}/><span>{item.title}</span>{item.id==='monitor' && status?.monitor!=='OK' && <span className="nav-signal"/>}{section===item.id && <div className="nav-active-line"/>}</button>)}</nav><div className="sidebar-spacer"/><div className="side-status"><div className="side-status-head"><span className="live-indicator"/>系统状态 <span className="side-status-tag">READ ONLY</span></div><div className="side-status-row"><span>GitHub 研究数据</span><strong className={status?.registry==='OK'?'status-good':'status-dim'}>{formatSource(status?.registry)}</strong></div><div className="side-status-row"><span>Airtable 持仓</span><strong className={status?.airtable==='OK'?'status-good':'status-dim'}>{formatSource(status?.airtable)}</strong></div><div className="side-status-divider"/><p>本看板只展示已发布结果，不自动生成交易信号。</p></div><div className="side-footer"><ShieldCheck size={15}/> PRIVATE INVESTOR DESK <span>v1.0</span></div></aside></>;
}
function Metric({label,value,meta,icon:Icon,accent='blue',hint}) {return <div className="metric-card"><div className="metric-top"><span>{label}</span><span className={`metric-icon metric-${accent}`}><Icon size={18}/></span></div><div className="metric-number">{value}</div><div className="metric-meta">{hint && <span className="metric-hint">{hint}</span>}{meta}</div></div>}
function TrendFocus({item,rank}) {return <div className="focus-row"><div className="focus-rank">{String(rank).padStart(2,'0')}</div><div className="focus-details"><strong>{item.trend_name}</strong><div><span>{safeText(item.trend_state)}</span><span className="tiny-sep">·</span><span>{safeText(item.industry_names?.[0])}</span></div></div><Badge>{item.market_state}</Badge></div>}
function HistoryStrip({events}) {const list=asArray(events).slice(-6);return list.length?<div className="history-strip">{list.map((e,i)=><div className="history-node" key={`${e.trade_date}-${i}`} title={`${e.trade_date} · ${e.to||e.event||'历史观察'}`}><span className={i===list.length-1?'history-node-current':''}/><small>{String(e.trade_date||'').slice(5)}</small></div>)}</div>:<span className="muted">暂无状态历史</span>}
function TrendInspector({item}) {
 if(!item) return <Empty title="选择一个板块" detail="查看产业状态、支持证据与失效条件"/>;
 const evidence=asArray(item.supporting_evidence).slice(-2).reverse();
 const contrary=asArray(item.contrary_evidence).slice(-2).reverse();
 return <div className="detail-content"><div className="detail-hero"><div className="eyebrow">SECTOR PROFILE / 板块详情</div><h2>{item.trend_name}</h2><div className="detail-badges"><Badge>{item.market_state}</Badge><Badge>{item.lifecycle_status}</Badge></div></div><div className="data-pair"><div><span>产业阶段</span><strong>{stageLabel(item.trend_state)}</strong></div><div><span>最近核验</span><strong>{safeText(item.last_verified_trade_date)}</strong></div></div><div className="detail-section"><div className="small-heading"><GitBranch size={15}/> 状态演变</div><HistoryStrip events={item.state_history}/></div><div className="detail-section"><div className="small-heading"><Check size={15}/> 支持证据</div>{evidence.length ? evidence.map((e,i)=><div className="evidence" key={i}><span className="evidence-date">{e.trade_date}</span><p>{e.description}</p>{/^https?:\/\//.test(e.source||'')&&<a href={e.source} target="_blank" rel="noopener noreferrer">查看依据 <ExternalLink size={12}/></a>}</div>):<p className="muted">没有已发布证据</p>}</div><div className="detail-section"><div className="small-heading"><ShieldAlert size={15}/> 反向证据</div>{contrary.length ? contrary.map((e,i)=><div className="evidence" key={i}><span className="evidence-date">{e.trade_date}</span><p>{e.description}</p></div>):<p className="muted">暂无记录</p>}</div><div className="invalidation"><span>失效观察条件</span><p>{safeText(item.invalidation_condition)}</p></div></div>;
}

const signed = (value,digits=1) => typeof value==='number' && Number.isFinite(value) ? (value>0?'+':'')+fixed(value,digits) : '—';
const changeWord = d => d==null?'不足两轮':d<0?'回落':d>0?'回升':'持平';
function SnapshotPlot({rows,field,label,unit='%',scale=1,bounds=null,compact=false,color='mint'}){
 const id=React.useId().replace(/:/g,'');
 const data=asArray(rows).filter(row=>typeof row?.[field]==='number' && Number.isFinite(row[field]) && !Number.isNaN(Date.parse(row.scan_at)))
  .map(row=>({at:Date.parse(row.scan_at),value:row[field]*scale,scan_at:row.scan_at})).sort((a,b)=>a.at-b.at);
 if(!data.length)return <span className="plot-unavailable">无有效数值快照</span>;
 const w=compact?164:680,h=compact?53:242;
 const left=compact?5:56,right=compact?5:24,top=compact?7:17,bottom=compact?7:43;
 const values=data.map(x=>x.value);
 let low=bounds?bounds[0]:Math.min(...values);
 let high=bounds?bounds[1]:Math.max(...values);
 if(!bounds){const spread=high-low;const pad=Math.max(spread*.20,Math.max(Math.abs(high),Math.abs(low),1)*.012);low-=pad;high+=pad}
 if(high<=low){low-=1;high+=1}
 const xMin=data[0].at,xMax=data.at(-1).at;
 const xp=item=>xMax===xMin?(left+w-right)/2:left+(item.at-xMin)/(xMax-xMin)*(w-left-right);
 const yp=item=>top+(high-item.value)/(high-low)*(h-top-bottom);
 const pts=data.map(x=>[xp(x),yp(x)]);
 const path=pts.map((p,i)=>(i?'L':'M')+p[0].toFixed(2)+' '+p[1].toFixed(2)).join(' ');
 const area=path+' L'+pts.at(-1)[0].toFixed(2)+' '+(h-bottom)+' L'+pts[0][0].toFixed(2)+' '+(h-bottom)+' Z';
 const display=value=>fixed(value,unit==='元'?2:1)+unit;
 return <div className={compact?'plot plot-compact':'plot plot-large'}>
  {!compact&&<div className="plot-head"><strong>{label}</strong><span>{data.length} 轮有效快照 · 最新 {display(data.at(-1).value)}</span></div>}
  <svg viewBox={'0 0 '+w+' '+h} preserveAspectRatio="xMidYMid meet" role="img" aria-label={label+'：'+data.map(d=>fmtTime(d.scan_at)+' '+display(d.value)).join('，')}>
   <defs><linearGradient id={id} x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor={color==='amber'?'#d0b18a':'#9ecbb0'} stopOpacity=".15"/><stop offset="100%" stopColor={color==='amber'?'#d0b18a':'#9ecbb0'} stopOpacity="0"/></linearGradient></defs>
   {!compact&&[0,.5,1].map((t,i)=><g key={i}><line x1={left} y1={top+t*(h-top-bottom)} x2={w-right} y2={top+t*(h-top-bottom)} className="plot-grid"/><text x={left-12} y={top+t*(h-top-bottom)+4} textAnchor="end" className="plot-axis">{display(high-t*(high-low))}</text></g>)}
   {data.length>=2&&<path d={area} fill={'url(#'+id+')'}/>}
   {data.length>=2&&<path className={'plot-line plot-line-'+color} d={path} fill="none" strokeWidth={compact?2.2:2.65} strokeLinecap="round" strokeLinejoin="round"/>}
   {data.map((d,i)=><g key={d.scan_at}><circle cx={pts[i][0]} cy={pts[i][1]} r={compact?3.25:4.6} className={'plot-point plot-point-'+color}/><title>{fmtTime(d.scan_at)+' · '+display(d.value)}</title>{!compact&&<text x={pts[i][0]} y={h-14} className="plot-axis plot-time" textAnchor="middle">{new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(d.at))}</text>}</g>)}
  </svg>
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
  <td><span className={t.priorityRank!=null?'official-rank':'unranked'}>{t.priorityRank!=null?String(t.priorityRank).padStart(2,'0'):'—'}</span></td>
  <td><strong>{t.trend_name}</strong><small>{safeText(t.trend_state)} · {asArray(t.industry_names).slice(0,1).join(' / ')||'正式趋势池'}</small></td>
  <td><Badge>{t.market_state}</Badge></td>
  {!compact&&<td><SnapshotPlot rows={rows} field="up_ratio" label="上涨占比" scale={100} bounds={[0,100]} compact/></td>}
  {!compact&&<td><span className={'trend-delta '+(delta!=null&&delta<0?'trend-down':'')}>{delta==null?'—':signed(delta,1)+' pp'}</span><small>{rows.length?'采样 '+rows.length+' 轮':'未覆盖'}</small></td>}
  <td className="mono soft-text">{safeText(t.last_verified_trade_date)}</td><td className="arrow-col"><ChevronRight size={16}/></td>
 </tr>})}</tbody></table>{!filtered.length&&<Empty title="没有匹配板块" detail="调整搜索条件再试" icon={Search}/>}</div>
 <div className="table-footer">展示 {filtered.length} / {trends.length} 个板块 <span>正式名次仅来自趋势 Handoff · 广度变化单位 pp（百分点）</span></div></>;
}
function Overview({registry,trendHandoff,buy,monitor,portfolio,status,onSection,setSelectedBuy}){
 const confirmedPositions=portfolio.positions.filter(p=>p.verified);
 const unverifiedPositions=portfolio.positions.filter(p=>!p.verified);
 const formalItems=asArray(buy?.items);
 const ready=formalItems.filter(item=>item.status==='READY').sort((a,b)=>(a.rank||999)-(b.rank||999));
 const waiting=formalItems.filter(item=>item.status==='WAIT');
 const ranked=asArray(trendHandoff?.signals).slice().sort((a,b)=>(a.rank||999)-(b.rank||999));
 const monitorCurrent=status.monitor==='OK' && monitor?.result_kind==='a_share_intraday_monitor_state' && monitor.trade_date===shanghaiDay();
 const monitoredSectors=monitorCurrent?latestMonitorRecords(monitor.industry_history):[];
 const monitoredStocks=monitorCurrent?latestMonitorRecords(monitor.stock_history):[];
 const sectorByName=new Map(monitoredSectors.map(row=>[row.trend_name||row.key,row]));
 const stockByCode=new Map(monitoredStocks.map(row=>[row.code||row.key,row]));
 const visiblePositions=[...unverifiedPositions,...confirmedPositions].slice(0,4);
 return <div className="decision-home">
  <div className="decision-heading">
   <div><div className="eyebrow">TODAY / DECISION FOCUS</div><h1>今日重点</h1><p>先看已有持仓，再看市场变化，最后看新的机会。</p></div>
   <div className="decision-date"><Clock3 size={14}/><span>趋势基准 {registry?.trade_date||'—'}<br/>盘中最近扫描 {monitorCurrent?fmtTime(monitor.last_scan_at):'暂无今日有效记录'}</span></div>
  </div>
  <div className="decision-strip">
   <div><span>登记持仓</span><strong>{status.airtable==='OK'?confirmedPositions.length:'—'}</strong><small>{unverifiedPositions.length?String(unverifiedPositions.length)+' 项待核验':'按 Airtable 记录'}</small></div>
   <div><span>盘中覆盖</span><strong>{monitorCurrent?monitoredSectors.length:'—'}</strong><small>{monitorCurrent?'今日板块快照':'尚无今日快照'}</small></div>
   <div><span>正式 READY</span><strong>{status.buyHandoff==='OK'?ready.length:'—'}</strong><small>{status.buyHandoff==='OK'?String(waiting.length)+' 只 WAIT':'暂无数据'}</small></div>
  </div>
  <div className="decision-grid">
   <section className="panel decision-panel decision-portfolio">
    <div className="decision-panel-top"><div><span className="decision-step">01 · 优先关注</span><h2>我的持仓</h2><p>只展示已记录的持仓与已发布的监测结果，不新增卖出判断。</p></div><button className="text-link" onClick={()=>onSection('portfolio')}>持仓详情 <ArrowRight size={14}/></button></div>
    {status.airtable!=='OK'?<div className="decision-empty">Airtable 暂不可用，无法核实持仓。<button onClick={()=>onSection('portfolio')}>查看数据状态 <ArrowRight size={13}/></button></div>:
      visiblePositions.length?<div className="decision-rows">{visiblePositions.map(p=>{
        const m=stockByCode.get(p.code);
        return <button type="button" className="decision-row" key={p.code} onClick={()=>onSection('portfolio')}>
         <div className="decision-row-main"><strong>{p.name}</strong><small>{p.code} · {p.verified?String(p.shares)+' 股':'持仓待核验'}</small></div>
         <div className="decision-row-meta"><span>{!p.verified?'成交记录待核验':!monitorCurrent?'暂无今日监测':!m?'盘中快照未覆盖':m.holding_action||'无已发布持仓动作'}</span><small>{p.conditions.length?'已有失效观察条件':'退出条件待补充'}</small></div><ChevronRight size={15}/>
        </button>
       })}</div>:<div className="decision-empty">目前没有可核实的登记持仓。<button onClick={()=>onSection('portfolio')}>查看交易记录 <ArrowRight size={13}/></button></div>}
    {portfolio.positions.length>visiblePositions.length&&<button className="decision-more" onClick={()=>onSection('portfolio')}>其余持仓在详情中查看 <ArrowRight size={13}/></button>}
   </section>
   <section className="panel decision-panel decision-market">
    <div className="decision-panel-top"><div><span className="decision-step">02 · 盘中变化</span><h2>优先板块</h2><p>保留趋势榜原始排序，对照本轮盘中状态。</p></div><button className="text-link" onClick={()=>onSection('monitor')}>监测详情 <ArrowRight size={14}/></button></div>
    {!monitorCurrent&&<div className="decision-message"><CircleAlert size={14}/> 当前没有今日有效监测，以下仅展示趋势榜的历史优先顺序。</div>}
    {ranked.length?<div className="decision-rows">{ranked.slice(0,4).map((item,i)=>{
      const m=sectorByName.get(item.trend_name);
      const movement=m?(m.previous_state&&m.previous_state!==m.current_state?m.previous_state+' → '+m.current_state:m.current_state):'尚无今日盘中状态';
      return <button type="button" className="decision-row" key={item.trend_name} onClick={()=>onSection('monitor')}>
       <div className="decision-rank">{String(item.rank||i+1).padStart(2,'0')}</div>
       <div className="decision-row-main"><strong>{item.trend_name}</strong><small>{item.trend_state} · {item.market_state}</small></div>
       <div className="decision-row-meta"><span>{movement}</span><small>{m?'结构动量：'+safeText(m.structure_momentum):'研究日 '+(trendHandoff?.trade_date||'—')}</small></div><ChevronRight size={15}/>
      </button>
    })}</div>:<div className="decision-empty">尚未发布优先趋势排序。</div>}
   </section>
  </div>
  <section className="panel decision-panel decision-opportunity">
   <div className="decision-panel-top"><div><span className="decision-step">03 · 新的机会</span><h2>正式买点</h2><p>仅 READY 作为已发布待核对机会；WAIT 不等于可立即买入。</p></div><button className="text-link" onClick={()=>onSection('buy')}>完整买点榜 <ArrowRight size={14}/></button></div>
   {status.buyHandoff!=='OK'?<div className="decision-empty">正式买点数据暂不可用。</div>:ready.length?
    <div className="decision-rows decision-entries">{ready.slice(0,3).map(item=><button className="decision-row" type="button" key={item.code} onClick={()=>{setSelectedBuy(item);onSection('buy')}}>
     <div className="decision-row-main"><strong>{item.company_name}</strong><small>{item.code} · {item.trend_name}</small></div>
     <Badge variant="good">READY</Badge><div className="decision-row-meta"><span>{Array.isArray(item.entry_zone)?fixed(item.entry_zone[0],2)+' – '+fixed(item.entry_zone[1],2):'入场计划待核验'}</span><small>入场计划，不是实时交易指令</small></div><ChevronRight size={15}/>
    </button>)}</div>
   :<div className="decision-no-ready"><span className="decision-no-icon"><ShieldCheck size={21}/></span><div><strong>目前没有 READY 买点</strong><p>正式榜单中的 {waiting.length} 只股票仍为 WAIT，暂不把等待信号显示为买入机会。</p></div><button className="text-link" onClick={()=>onSection('buy')}>查看 WAIT <ArrowRight size={14}/></button></div>}
  </section>
  <div className="decision-bottom"><span>所有信息均来自已发布的正式数据；盘中观察不等于结构失效或交易指令。</span><button onClick={()=>onSection('trends')}>研究全部 {asArray(registry?.trends).length} 个趋势方向 <ArrowRight size={14}/></button></div>
 </div>;
}
function Trends({registry,selected,setSelected}){const trends=asArray(registry?.trends);return <><PageIntro code="01 / SECTOR RESEARCH" title="板块趋势雷达" desc="产业阶段、市场确认和反向证据，分层呈现。所有状态均来自正式趋势池。" date={registry?.trade_date}/><div className="two-pane"><section className="panel"><PanelHead label="TREND REGISTRY" title="全部趋势方向" aside={<span className="count-chip">{trends.length} 个方向</span>}/>{trends.length?<TrendTable trends={trends} selected={selected} onSelect={setSelected}/>:<Empty title="暂无趋势数据" detail="等待正式趋势池发布"/>}</section><section className="panel inspector inspector-tall"><TrendInspector item={selected||trends[0]}/></section></div></>}
function PageIntro({code,title,desc,date}){return <div className="page-intro"><div><div className="eyebrow">{code}</div><h1>{title}</h1><p>{desc}</p></div><div className="asof"><Clock3 size={15}/><span>数据交易日 <strong>{date||'—'}</strong></span></div></div>}
function BuyInspector({item}){if(!item)return <Empty title="选择一只候选股票" detail="查看已发布入场条件、结构失效计划与风险"/>;return <div className="detail-content buy-inspector"><div className="detail-hero"><div className="eyebrow">ENTRY PROFILE / 交易计划</div><h2>{item.company_name}<span className="company-code">{item.code}</span></h2><div className="detail-badges"><Badge>{item.status}</Badge><Badge>{item.market_state}</Badge></div></div><div className="data-pair"><div><span>历史收盘参考价</span><strong className="big-number">{fixed(item.current_price)}</strong></div><div><span>形态类型</span><strong>{safeText(item.setup_type)}</strong></div></div><div className="detail-section"><div className="small-heading"><Target size={15}/> 计划入场区间</div><div className="entry-range">{Array.isArray(item.entry_zone)? `${fixed(item.entry_zone[0],3)} – ${fixed(item.entry_zone[1],3)}`:'尚未形成有效入场区间'}</div><p className="hint-text">入场触发：{safeText(item.entry_trigger)}</p></div><div className="data-pair"><div><span>最大入场价</span><strong>{fixed(item.max_entry_price,3)}</strong></div><div><span>结构失效参考</span><strong>{fixed(item.invalidation_price,3)}</strong></div></div><div className="detail-section"><div className="small-heading"><CircleAlert size={15}/> 当前判断</div><p className="reason-paragraph">{safeText(item.decision_reason)}</p></div><div className="invalidation"><span>失效规则</span><p>{safeText(item.invalidation_rule)}</p></div><div className="disclaimer">READY / WAIT 是正式研究结果，不代表实时成交指令。无当日行情确认时不得据此执行。</div></div>}
function Buy({buy,selected,setSelected,status}){const items=asArray(buy?.items); const [filter,setFilter]=useState('全部');const [query,setQuery]=useState('');const [group,setGroup]=useState('全部板块');const markets=[...new Set(items.map(i=>i.trend_name).filter(Boolean))]; const shown=items.filter(i=>(filter==='全部'||i.status===filter)&&(group==='全部板块'||i.trend_name===group)&&`${i.company_name||''}${i.code||''}`.includes(query));const focus=items.find(i=>i.code===selected?.code)||shown[0];return <><PageIntro code="02 / ENTRY SIGNALS" title="趋势买点观察" desc="优先呈现正式 READY / WAIT 结果，保留原始入场计划和风险条件。" date={buy?.trade_date}/><div className="buy-summary"><div><Badge>READY</Badge><strong>{items.filter(i=>i.status==='READY').length}</strong><span>条件满足候选</span></div><div><Badge>WAIT</Badge><strong>{items.filter(i=>i.status==='WAIT').length}</strong><span>等待确认</span></div><div><span className="muted">正式覆盖</span><strong>{items.length}</strong><span>已发布标的</span></div></div><div className="two-pane"><section className="panel"><PanelHead label="BUY-POINT HANDOFF · V2" title="正式候选列表" aside={<span className="count-chip">{shown.length} 只</span>}/><div className="table-controls"><div className="search"><Search size={16}/><input placeholder="名称或股票代码" value={query} onChange={e=>setQuery(e.target.value)}/></div><div className="filter-select"><select value={filter} onChange={e=>setFilter(e.target.value)}><option>全部</option><option>READY</option><option>WAIT</option></select><ChevronDown size={13}/></div></div><div className="group-select"><SlidersHorizontal size={14}/><select value={group} onChange={e=>setGroup(e.target.value)}><option>全部板块</option>{markets.map(g=><option key={g}>{g}</option>)}</select></div>{items.length?<div className="table-wrap"><table className="data-table"><thead><tr><th>股票 / 代码</th><th>来源板块</th><th>参考价</th><th>信号</th><th/></tr></thead><tbody>{shown.map(item=><tr key={item.code} className={focus?.code===item.code?'row-selected':''} onClick={()=>setSelected(item)}><td><strong>{item.company_name}</strong><small className="mono">{item.code}</small></td><td className="soft-text">{item.trend_name}</td><td className="mono">{fixed(item.current_price)}</td><td><Badge>{item.status}</Badge></td><td><ChevronRight size={16}/></td></tr>)}</tbody></table>{!shown.length&&<Empty title="筛选后无候选" detail="尝试切换信号或板块" icon={Search}/>}</div>:<Empty title="买点榜尚未发布" detail={`数据状态：${formatSource(status.buyHandoff)}`}/>}<div className="table-footer">正式排名不因页面筛选而改变 <span>交易日 {buy?.trade_date||'—'}</span></div></section><section className="panel inspector inspector-tall"><BuyInspector item={focus}/></section></div></>}
function Monitor({monitor,status}){const industries=latestMonitorRecords(monitor?.industry_history);const stocks=latestMonitorRecords(monitor?.stock_history);const isValid=monitor?.result_kind==='a_share_intraday_monitor_state';return <><PageIntro code="03 / INTRADAY OBSERVATION" title="盘中结构监测" desc="仅展示已提交并通过校验的盘中判断，不将盘中风险提示误写为已确认卖出。" date={monitor?.trade_date}/><div className="monitor-note"><ShieldCheck size={18}/><div><strong>独立的交易信号边界</strong><p>盘中提醒 ≠ 日线结构失效；持仓退出以原定交易计划的确认条件为准。</p></div></div>{!isValid?<section className="panel monitor-empty"><Empty title="暂无有效盘中监测记录" detail={`research/intraday_monitor_state.json：${formatSource(status.monitor)}。没有已发布状态时不推断盘中信号。`} icon={Activity}/></section>:<><div className="metrics-grid monitor-metrics"><Metric label="板块监测" icon={Layers} value={industries.length} meta="已归档结构观察"/><Metric label="个股监测" icon={Target} value={stocks.length} meta="冻结候选覆盖"/><Metric label="记录交易日" icon={CalendarDays} value={monitor.trade_date||'—'} meta="监测数据基准"/><Metric label="最后扫描" icon={Clock3} value={fmtTime(monitor.last_scan_at)} meta="北京时间"/></div><section className="panel"><PanelHead label="INTRADAY SECTOR STATE" title="板块监测结果" aside={<span className="panel-note">快照时间 {fmtTime(monitor.snapshot_at)}</span>}/>{industries.length?<div className="table-wrap"><table className="data-table"><thead><tr><th>板块</th><th>当前状态</th><th>结构动量</th><th>空仓动作</th><th>持仓动作</th></tr></thead><tbody>{industries.map((row,i)=><tr key={i}><td><strong>{row.trend_name||row.key||'—'}</strong></td><td><Badge>{row.current_state||'—'}</Badge></td><td>{safeText(row.structure_momentum)}</td><td>{safeText(row.entry_action)}</td><td>{safeText(row.holding_action)}</td></tr>)}</tbody></table></div>:<Empty title="当前文件没有板块记录" detail="等待任务发布行业监测结果"/>}</section><section className="panel monitor-stock-panel"><PanelHead label="INTRADAY STOCK STATE" title="个股监测结果"/>{stocks.length?<div className="table-wrap"><table className="data-table"><thead><tr><th>股票</th><th>价格行为</th><th>相对强度</th><th>空仓观察</th><th>持仓管理</th></tr></thead><tbody>{stocks.map((row,i)=><tr key={i}><td><strong>{row.company_name||row.key||row.code||'—'}</strong></td><td>{safeText(row.price_behavior)}</td><td>{safeText(row.relative_strength)}</td><td>{safeText(row.entry_action)}</td><td>{safeText(row.holding_action)}</td></tr>)}</tbody></table></div>:<Empty title="当前文件没有个股记录" detail="等待任务发布候选股监测结果"/>}</section></>}</>}
function Portfolio({data,status,monitor}){const {positions,recordCount,invalidCount}=data;const ok=status.airtable==='OK';return <><PageIntro code="04 / PERSONAL RISK DESK" title="个人持仓记录" desc="Airtable 仅用于核验登记交易与退出规则，不作为实时市场行情源。"/><div className="monitor-note privacy-note"><LockKeyhole size={18}/><div><strong>个人数据仅经受保护的服务端接口读取</strong><p>不会写入公开 GitHub 仓库；未取得行情与收盘确认时，不计算实时收益或自动给出卖出指令。</p></div></div>{!ok?<section className="panel monitor-empty"><Empty title="Airtable 尚未接通网站" detail={status.airtable==='NOT_CONFIGURED'?'在 Vercel 设置 AIRTABLE_TOKEN、AIRTABLE_BASE_ID、AIRTABLE_TABLE_ID 后即可读取。':`当前状态：${formatSource(status.airtable)}；不会将读取失败解释为没有持仓。`} icon={Database}/></section>:<><div className="metrics-grid portfolio-metrics"><Metric label="记录交易" value={recordCount} icon={Database} meta="Airtable 原始条目"/><Metric label="登记在持" value={positions.filter(p=>p.verified).length} icon={Wallet} accent="green" meta="可核实净持仓 > 0"/><Metric label="待核对记录" value={invalidCount+positions.filter(p=>!p.verified).length} icon={ShieldAlert} accent="amber" meta="不可据此生成交易动作"/><Metric label="行情联动" value={monitor?.result_kind==='a_share_intraday_monitor_state'?'有监测数据':'尚未就绪'} icon={Activity} accent="purple" meta="仅已发布的盘中快照"/></div><section className="panel"><PanelHead label="AIRTABLE · TRADE LEDGER" title="登记持仓清单" aside={<span className="count-chip">{positions.length} 条待关注</span>}/>{positions.length?<div className="portfolio-grid">{positions.map(p=><article key={p.code} className="position-card"><div className="position-heading"><div><div className="eyebrow">{p.code}</div><h3>{p.name}</h3></div><Badge variant={p.verified?'good':'warn'}>{p.verified?'已核实股数':'待核验'}</Badge></div><div className="position-numbers"><div><span>登记股数</span><strong>{p.shares==null?'待确认':p.shares.toLocaleString('zh-CN')}</strong></div><div><span>剩余均价估算</span><strong>{fixed(p.avgCost,3)}</strong></div><div><span>剩余成本估算</span><strong>{fixed(p.costValue)}</strong></div></div><div className="position-rule"><span><ShieldAlert size={14}/> 记录的失效条件</span><p>{p.conditions.length===1?p.conditions[0]:p.conditions.length>1?'存在多条不同条件，需人工核验':'尚未记录明确失效条件'}</p></div>{p.issues.length>0&&<div className="issue-text">{p.issues.join('；')}</div>}<div className="position-foot">最后登记交易日 <b>{p.lastDate||'—'}</b><span>共 {p.recordCount} 条成交记录</span></div></article>)}</div>:<Empty title="没有可核实的在持股票" detail={invalidCount?'仍有代码缺失的记录需要人工核验。':'已成功读取 Airtable，目前无可核实净持仓。'} icon={Wallet}/>}</section></>}</>}
function Login({login,loading,error,setupError}){const [password,setPassword]=useState('');return <div className="login-screen"><div className="login-glow"/><div className="login-shell"><div className="login-brand"><div className="brand-mark"><TrendingUp size={25}/></div><span>岚图 <small>LAN TU</small></span></div><div className="login-eyebrow">PRIVATE MARKET WORKSPACE</div><h1>看清趋势，<br/><span>从容决策。</span></h1><p className="login-description">你的 A 股市场研究与个人持仓决策工作台。一个页面，掌握所有重要信息。</p><form onSubmit={e=>{e.preventDefault();login(password)}}><label htmlFor="pass">访问密码</label><div className="password-control"><LockKeyhole size={19}/><input id="pass" value={password} onChange={e=>setPassword(e.target.value)} placeholder="输入看板访问密码" type="password" autoComplete="current-password" minLength={1} required/></div>{error&&<p className="login-error"><CircleAlert size={15}/>{error}</p>}<button type="submit" className="primary-btn" disabled={loading||!!setupError}>{loading?'验证中...':'进入工作台'} <ArrowRight size={17}/></button></form>{setupError&&<div className="setup-warning">站点尚未配置密码或会话密钥。请先配置 Vercel 环境变量。</div>}<div className="login-footer"><ShieldCheck size={15}/> READ ONLY · PRIVATE BY DESIGN</div></div><div className="login-art"><div className="login-art-box"><div className="login-art-title"><span className="live-indicator"/> SIGNAL DISCIPLINE</div><div className="login-art-line">OBSERVE <span>→</span> VERIFY <span>→</span> DECIDE</div><div className="login-art-graph"><svg viewBox="0 0 440 190" preserveAspectRatio="none"><defs><linearGradient id="lg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#68d5bb" stopOpacity=".26"/><stop offset="1" stopColor="#68d5bb" stopOpacity="0"/></linearGradient></defs><path d="M0 150 L40 144 L75 148 L110 104 L151 111 L187 83 L223 101 L253 68 L282 73 L322 44 L363 55 L399 23 L440 12 L440 190 L0 190Z" fill="url(#lg)"/><path d="M0 150 L40 144 L75 148 L110 104 L151 111 L187 83 L223 101 L253 68 L282 73 L322 44 L363 55 L399 23 L440 12" stroke="#67dcc0" strokeWidth="2.5" fill="none"/></svg></div><div className="art-bottom"><span>MARKET<br/>INTELLIGENCE</span><strong>01 — 05</strong></div></div><span className="mock-warning">装饰性图形 · 非实际行情</span></div></div>}
export default function App(){
 const [authenticated,setAuthenticated]=useState(null),[setupError,setSetupError]=useState(false),[loginError,setLoginError]=useState(''),[loadingLogin,setLoadingLogin]=useState(false),[loading,setLoading]=useState(false),[payload,setPayload]=useState(null),[section,setSection]=useState('overview'),[menu,setMenu]=useState(false),[selectedTrend,setSelectedTrend]=useState(null),[selectedBuy,setSelectedBuy]=useState(null);
 const fetchData=useCallback(async()=>{setLoading(true);try{const response=await fetch('/api/data',{cache:'no-store'});if(response.status===401){setAuthenticated(false);setPayload(null);return;}if(!response.ok)throw new Error(`数据接口 HTTP ${response.status}`);setPayload(await response.json());}catch(e){setPayload(old=>old?{...old,fetchError:e.message}:{datasets:{},status:{},fetchError:e.message});}finally{setLoading(false)}},[]);
 useEffect(()=>{let live=true;fetch('/api/auth',{cache:'no-store'}).then(async r=>{const j=await r.json();if(live){setAuthenticated(Boolean(j.authenticated));setSetupError(j.error==='SITE_NOT_CONFIGURED');}}).catch(()=>{if(live)setAuthenticated(false)});return()=>{live=false}},[]);
 useEffect(()=>{if(authenticated)fetchData()},[authenticated,fetchData]);
 const login=async password=>{setLoadingLogin(true);setLoginError('');try{const r=await fetch('/api/auth',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password})});if(!r.ok){setLoginError(r.status===503?'服务器尚未配置访问密钥':'密码错误或服务不可用');return;}setAuthenticated(true)}catch{setLoginError('服务暂时无法连接')}finally{setLoadingLogin(false)}};
 const logout=async()=>{try{await fetch('/api/auth',{method:'DELETE'})}finally{setAuthenticated(false);setPayload(null);setSection('overview')}};
 const datasets=payload?.datasets||{}, status=payload?.status||{};
 const portfolio=useMemo(()=>summarizeTrades(datasets.airtable),[datasets.airtable]);
 if(authenticated===null)return <div className="boot-screen"><div className="brand-mark"><TrendingUp size={29}/></div><span>LAN TU</span><div className="spinner"/></div>;
 if(!authenticated)return <Login login={login} loading={loadingLogin} error={loginError} setupError={setupError}/>;
 return <div className="app-shell"><Sidebar section={section} onSection={setSection} openMenu={menu} setOpenMenu={setMenu} status={status}/><div className="main-shell"><Header section={section} refresh={fetchData} refreshing={loading} data={payload} openMenu={menu} setOpenMenu={setMenu} logout={logout}/><main className="main-content">{payload?.fetchError&&<div className="fetch-warning"><CircleAlert size={17}/>{payload.fetchError}，展示上次成功加载的数据。</div>}{!payload?<Skeleton/>:<div className="view-enter" key={section}>{section==='overview'&&<Overview registry={datasets.registry} trendHandoff={datasets.trendHandoff} buy={datasets.buyHandoff} monitor={datasets.monitor} portfolio={portfolio} status={status} onSection={setSection} setSelectedBuy={setSelectedBuy}/ >}{section==='trends'&&<Trends registry={datasets.registry} selected={selectedTrend} setSelected={setSelectedTrend}/ >}{section==='buy'&&<Buy buy={datasets.buyHandoff} selected={selectedBuy} setSelected={setSelectedBuy} status={status}/ >}{section==='monitor'&&<Monitor monitor={datasets.monitor} status={status}/ >}{section==='portfolio'&&<Portfolio data={portfolio} status={status} monitor={datasets.monitor}/>}</div>}<footer className="main-footer"><span>LAN TU MARKET DESK</span><span>数据来自已发布的 GitHub 文件和私有 Airtable 记录 · 仅供研究参考，不构成交易建议</span><span>{payload?.receivedAt?`页面读取于 ${fmtTime(payload.receivedAt)}`:'等待同步'}</span></footer></main></div></div>;
}
