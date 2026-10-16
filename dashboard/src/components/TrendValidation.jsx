import React, {useEffect, useMemo, useState} from 'react';
import {
  Activity, AlertCircle, ArrowDownRight, ArrowRight, ArrowUpRight, BarChart3,
  CalendarDays, CheckCircle2, ChevronDown, CircleDotDashed, Clock3,
  GitBranch, Layers3, Search, ShieldCheck, TrendingUp
} from 'lucide-react';

const num = value => typeof value === 'number' && Number.isFinite(value)
  ? value.toLocaleString('zh-CN') : '—';
const percent = value => typeof value === 'number' && Number.isFinite(value)
  ? (value > 0 ? '+' : '') + value.toFixed(2) + '%' : '—';
const performanceTone = value => typeof value !== 'number' || !Number.isFinite(value)
  ? 'neutral' : value > 0 ? 'positive' : value < 0 ? 'negative' : 'neutral';
const horizonResult = result => {
  if (!result) return '暂无样本';
  if (result.state === 'matured') return percent(result.excess_vs_market_pct);
  if (result.state === 'pending') return '观察中';
  if (result.state === 'data_gap') return '数据缺失';
  return '无法评估';
};
const endLabel = row => row.ending === 'lost_confirmation' ? '失去确认'
  : row.ending === 'left_priority_not_failure' ? '退出推荐榜'
  : row.ending === 'censored_data_gap' ? '数据中断' : '持续观察';
const signalState = result => result?.state === 'matured' ? '已完成'
  : result?.state === 'pending' ? '观察中'
  : result?.state === 'data_gap' ? '数据缺失' : '无法评估';

function ObservationCard({icon:Icon,label,value,detail,emphasis=false}) {
  return <div className={'validation-observation'+(emphasis?' is-emphasis':'')}>
    <div className="validation-observation-label"><Icon size={16}/><span>{label}</span></div>
    <strong>{value}</strong><small>{detail}</small>
  </div>;
}

function OutcomeCard({kind,label,count,excess,icon:Icon}) {
  const hasSample=typeof count==='number'&&count>0;
  const valid=hasSample&&typeof excess==='number'&&Number.isFinite(excess);
  const state=valid?performanceTone(excess):'neutral';
  return <article className={'validation-outcome validation-outcome-'+kind}>
    <div className="validation-outcome-top"><span className="validation-outcome-icon"><Icon size={18}/></span><span>未来表现 / 已成熟样本</span><ArrowUpRight size={16}/></div>
    <h3>{label}</h3>
    <div className={'validation-outcome-value is-'+state}>{valid?percent(excess):'尚无成熟结果'}</div>
    <div className="validation-outcome-foot"><span>平均超额收益 · 相对全市场等权基准</span><strong>{num(count)} <small>个样本</small></strong></div>
    <div className="validation-outcome-rule" aria-hidden="true"><span/></div>
    <p>{hasSample?'仅反映历史观察表现，不等于可成交收益或策略胜率。':'观察窗口尚未成熟，不将等待中的信号计入有效性判断。'}</p>
  </article>;
}

function EvidenceTrack({timeline}) {
  const history=Array.isArray(timeline)?timeline.slice(-12):[];
  if(!history.length)return <p className="validation-no-track">尚无逐日状态归档。</p>;
  return <div className="validation-evidence-track" aria-label="已归档的真实趋势状态变化">
    {history.map((point,i)=><div className="validation-track-node" key={point.date+'-'+i}>
      <span className={'validation-track-dot'+(i===history.length-1?' is-latest':'')}/>
      <small>{String(point.date||'').slice(5)||'—'}</small>
      <strong>{point.market_state||'未核验'}</strong>
    </div>)}
  </div>;
}

function ExpandedEvidence({row,tab,trendMode,result}) {
  return <div className="validation-record-detail">
    <div className="validation-record-detail-heading"><GitBranch size={16}/><strong>完整核验轨迹</strong><span>原始归档 · 不填补缺失交易日</span></div>
    {tab==='trend'&&<EvidenceTrack timeline={row.state_timeline}/>}
    <div className="validation-record-facts">
      {tab==='trend'?<>
        <div><small>{trendMode==='recommendation'?'推荐起点':'确认起点'}</small><strong>{row.start_date||'—'}</strong></div>
        <div><small>最后在榜</small><strong>{row.last_date||'—'}</strong></div>
        <div><small>{trendMode==='recommendation'?'首次退出榜单':'首次降级'}</small><strong>{(trendMode==='recommendation'?row.first_removed_date:row.first_downgrade_date)||'未观察到'}</strong></div>
        <div><small>正式失效</small><strong>{row.first_invalidated_date||'未观察到'}</strong></div>
        <div><small>冻结成分股</small><strong>{num(row.frozen_constituent_count)} 只</strong></div>
      </>:<>
        <div><small>研究日</small><strong>{row.trade_date||'—'}</strong></div>
        <div><small>原始研究批次</small><strong className="validation-wrap-text">{row.source_run_id||'—'}</strong></div>
        <div><small>相对所属冻结板块</small><strong>{percent(result?.excess_vs_sector_pct)}</strong></div>
      </>}
      <div><small>观察收益</small><strong>{percent(result?.return_pct)}</strong></div>
      <div><small>全市场基准</small><strong>{percent(result?.market_return_pct)}</strong></div>
      <div><small>对照交易日</small><strong>{result?.target_date||'窗口未完成'}</strong></div>
    </div>
    <div className="validation-record-caveat"><ShieldCheck size={15}/><span>状态 {result?.state||'unavailable'} · READY 未模拟实际买入、止损与成交条件，观察收益不能等同实盘收益。</span></div>
  </div>;
}

export default function TrendValidation(){
  const [response,setResponse]=useState(null);
  const [tab,setTab]=useState('trend');
  const [trendMode,setTrendMode]=useState('recommendation');
  const [horizon,setHorizon]=useState('1');
  const [search,setSearch]=useState('');
  const [signalFilter,setSignalFilter]=useState('ALL');
  const [expanded,setExpanded]=useState(null);
  useEffect(()=>{
    let alive=true;
    fetch('/api/validation',{cache:'no-store'})
      .then(async result=>{if(!result.ok)throw new Error('数据接口 HTTP '+result.status);return result.json()})
      .then(result=>{if(alive)setResponse(result)})
      .catch(error=>{if(alive)setResponse({status:{},datasets:{},error:error.message})});
    return ()=>{alive=false};
  },[]);
  const {datasets={},status={}}=response||{};
  const summary=datasets.validationSummary||{};
  const confirmedRows=Array.isArray(datasets.validationTrends?.items)?datasets.validationTrends.items:[];
  const recommendationRows=Array.isArray(datasets.validationTrends?.recommendations)?datasets.validationTrends.recommendations:[];
  const stockRows=Array.isArray(datasets.validationStocks?.items)?datasets.validationStocks.items:[];
  const trendRows=trendMode==='recommendation'?recommendationRows:confirmedRows;
  const ok=status.validationSummary==='OK'&&status.validationTrends==='OK'&&status.validationStocks==='OK';
  const matured=summary.horizon_stats?.[horizon]||{};
  const rows=useMemo(()=>{
    const term=search.trim().toLowerCase();
    return tab==='trend'
      ?trendRows.filter(x=>String(x.trend_name||'').toLowerCase().includes(term))
        .slice().sort((a,b)=>String(b.start_date||'').localeCompare(String(a.start_date||'')))
      :stockRows.filter(x=>(signalFilter==='ALL'||x.status===signalFilter)&&
          [x.company_name,x.code,x.trend_name].some(v=>String(v||'').toLowerCase().includes(term)))
        .slice().sort((a,b)=>String(b.trade_date||'').localeCompare(String(a.trade_date||'')));
  },[tab,search,signalFilter,trendRows,stockRows]);

  return <div className="validation-page">
    <section className="validation-hero">
      <div className="validation-hero-inner">
        <div className="validation-hero-copy">
          <div className="validation-hero-eyebrow"><span className="validation-live-dot"/> X / VALIDATION LAB <span className="validation-eyebrow-separator"/> 历史信号审计</div>
          <h1>一条趋势，<br/><em>究竟能走多远？</em></h1>
          <p>追踪正式信号从出现、持续到结束的真实轨迹；用发布后的行情检验，而非事后挑选成功案例。</p>
          <div className="validation-hero-caption"><CalendarDays size={15}/><span>数据截至 {summary.as_of_trade_date||'尚无完成样本'}</span><span className="validation-hero-caption-dot"/> 不参与当前选股</div>
        </div>
        <div className="validation-hero-graphic" aria-hidden="true">
          <span className="validation-graph-orbit orbit-a"/><span className="validation-graph-orbit orbit-b"/>
          <svg viewBox="0 0 380 218" fill="none" preserveAspectRatio="xMidYMid meet">
            <path d="M8 180 L55 153 L100 161 L143 113 L186 129 L232 73 L276 90 L330 38 L372 54" stroke="#7DE4C3" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M8 180 L55 153 L100 161 L143 113 L186 129 L232 73 L276 90 L330 38 L372 54 L372 218 L8 218Z" fill="url(#v-fill)"/>
            <path d="M8 210 H372 M8 155 H372 M8 100 H372 M8 45 H372" stroke="#C5D5F1" strokeOpacity=".11" strokeDasharray="3 7"/>
            <circle cx="143" cy="113" r="5" fill="#DCE8FE"/><circle cx="232" cy="73" r="5" fill="#DCE8FE"/><circle cx="330" cy="38" r="7" fill="#7DE4C3" stroke="#244E5C" strokeWidth="5"/>
            <defs><linearGradient id="v-fill" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#4DDCB6" stopOpacity=".19"/><stop offset="1" stopColor="#4DDCB6" stopOpacity="0"/></linearGradient></defs>
          </svg>
          <span className="validation-graph-label label-a">SIGNAL</span><span className="validation-graph-label label-b">OBSERVE</span><span className="validation-graph-label label-c">VERIFY</span>
        </div>
      </div>
      <div className="validation-hero-foot"><ShieldCheck size={15}/><span>数据规则：仅使用信号发布后的行情；断档不算失败，未成熟样本不计算成功率。</span><span className="validation-hero-foot-id">RESEARCH INTEGRITY / 01</span></div>
    </section>

    {!ok?<section className="validation-empty-state">
      <div className="validation-empty-icon"><CircleDotDashed size={27}/></div>
      <span className="eyebrow">AWAITING VERIFIED DATA</span>
      <h2>证据仍在积累</h2>
      <p>{response?.error||'独立归档在完整的收盘研究完成后生成。暂时不使用无法核实的历史结果填充图表。'}</p>
      <div>归档 {status.validationSummary||'待发布'} <span/> 趋势 {status.validationTrends||'待发布'} <span/> 个股 {status.validationStocks||'待发布'}</div>
    </section>:<>
      <section className="validation-observations" aria-label="历史覆盖概况">
        <ObservationCard icon={CalendarDays} label="归档交易日" value={num(summary.archive_days)} detail="完整研究日存档"/>
        <ObservationCard icon={Layers3} label="正式推荐事件" value={num(summary.recommendation_episodes)} detail="候选与确认趋势"/>
        <ObservationCard icon={GitBranch} label="已结束推荐" value={num(summary.closed_recommendations)} detail="退出推荐不等于趋势失效"/>
        <ObservationCard icon={Activity} label="一日后退出" value={num(summary.one_day_recommendations)} detail={summary.one_day_recommendation_pct==null?'样本不足':percent(summary.one_day_recommendation_pct)+' · 已结束推荐样本'} emphasis/>
      </section>

      <section className="validation-measurement">
        <div className="validation-section-head">
          <div><span className="eyebrow">01 / FORWARD PERFORMANCE</span><h2>信号发布后，表现如何？</h2><p>相对全市场等权日收益代理基准；同一观察窗口下分别检验趋势和个股。</p></div>
          <div className="validation-horizon" role="group" aria-label="未来观察窗口">
            {['1','3','5','10','20'].map(n=><button key={n} type="button" aria-pressed={horizon===n} className={horizon===n?'active':''} onClick={()=>{setHorizon(n);setExpanded(null)}}>{n}<small>日</small></button>)}
          </div>
        </div>
        <div className="validation-outcomes">
          <OutcomeCard kind="trend" icon={TrendingUp} label="已确认趋势" count={matured.trend_matured} excess={matured.trend_avg_excess_vs_market_pct}/>
          <OutcomeCard kind="stock" icon={BarChart3} label="个股信号" count={matured.stock_matured} excess={matured.stock_avg_excess_vs_market_pct}/>
        </div>
        <div className="validation-measurement-note"><AlertCircle size={16}/><span>这是历史超额收益的描述性统计。样本量、样本选择和市场阶段会影响解释；不将正收益直接称为胜率或可复制优势。</span></div>
      </section>

      <section className="validation-history">
        <div className="validation-section-head validation-history-head">
          <div><span className="eyebrow">02 / SIGNAL ARCHIVE</span><h2>每一条信号，都有迹可循</h2><p>追溯持续时间、转折状态与观察区间，点击记录查看完整证据。</p></div>
          <span className="validation-record-count">{rows.length} <small>条匹配记录</small></span>
        </div>
        <div className="validation-history-controls">
          <div className="validation-main-tabs" role="group" aria-label="验证对象">
            <button type="button" aria-pressed={tab==='trend'} className={tab==='trend'?'active':''} onClick={()=>{setTab('trend');setExpanded(null)}}><Layers3 size={15}/> 板块趋势 <span>{trendRows.length}</span></button>
            <button type="button" aria-pressed={tab==='stock'} className={tab==='stock'?'active':''} onClick={()=>{setTab('stock');setExpanded(null)}}><Activity size={15}/> 个股信号 <span>{stockRows.length}</span></button>
          </div>
          {tab==='trend'&&<div className="validation-subtabs" role="group" aria-label="趋势区间口径">
            <button type="button" aria-pressed={trendMode==='recommendation'} className={trendMode==='recommendation'?'active':''} onClick={()=>{setTrendMode('recommendation');setExpanded(null)}}>推荐区间 · {recommendationRows.length}</button>
            <button type="button" aria-pressed={trendMode==='confirmed'} className={trendMode==='confirmed'?'active':''} onClick={()=>{setTrendMode('confirmed');setExpanded(null)}}>确认区间 · {confirmedRows.length}</button>
          </div>}
          <div className="validation-search"><Search size={16}/><input value={search} onChange={event=>setSearch(event.target.value)} aria-label="搜索验证记录" placeholder={tab==='trend'?'搜索趋势名称':'搜索股票、代码或板块'}/></div>
          {tab==='stock'&&<div className="validation-filter"><select aria-label="按信号状态筛选" value={signalFilter} onChange={event=>setSignalFilter(event.target.value)}><option value="ALL">全部状态</option><option value="READY">READY</option><option value="WAIT">WAIT</option><option value="UNCERTAIN">UNCERTAIN</option><option value="DROP">DROP</option></select><ChevronDown size={14}/></div>}
        </div>
        <div className="validation-list">
          <div className="validation-list-head" aria-hidden="true"><span>信号与归属</span><span>起始交易日</span><span>{tab==='trend'?'持续天数':'正式状态'}</span><span>未来 {horizon} 日超额</span><span>验证进度</span><span/></div>
          {rows.slice(0,120).map(row=>{
            const key=tab==='trend'?row.trend_name+'#'+row.start_date+'#'+trendMode:row.code+'#'+row.trade_date+'#'+row.source_run_id;
            const result=row.horizons?.[horizon],open=key===expanded;
            const value=typeof result?.excess_vs_market_pct==='number'?result.excess_vs_market_pct:null;
            return <div className={'validation-record'+(open?' is-open':'')} key={key}>
              <button type="button" className="validation-record-trigger" aria-expanded={open} aria-controls={'validation-record-'+rows.indexOf(row)} onClick={()=>setExpanded(open?null:key)}>
                <span className="validation-record-name"><strong>{tab==='trend'?row.trend_name:row.company_name||row.code}</strong><small>{tab==='trend'?(trendMode==='recommendation'?'正式推荐历史':'趋势确认历史'):row.code+' · '+(row.trend_name||'未归属板块')}</small></span>
                <span className="validation-record-date">{tab==='trend'?row.start_date||'—':row.trade_date||'—'}</span>
                <span className="validation-record-duration">{tab==='trend'?(num(trendMode==='recommendation'?row.recommended_sessions:row.confirmed_sessions)+' 日'):<span className="validation-signal-tag">{row.status||'—'}</span>}</span>
                <span className={'validation-record-return is-'+(result?.state==='matured'?performanceTone(value):'neutral')}>{horizonResult(result)}</span>
                <span className="validation-record-state"><span className={'validation-progress-dot '+(result?.state||'unknown')}/>{tab==='trend'?endLabel(row):signalState(result)}</span>
                <span className="validation-record-arrow">{open?<ChevronDown size={17}/>:<ArrowRight size={17}/>}</span>
              </button>
              {open&&<div id={'validation-record-'+rows.indexOf(row)}><ExpandedEvidence row={row} tab={tab} trendMode={trendMode} result={result}/></div>}
            </div>;
          })}
          {!rows.length&&<div className="validation-list-empty"><Search size={19}/> 当前条件下没有有效验证样本，试试调整搜索或状态。</div>}
          {rows.length>120&&<div className="validation-list-foot">仅显示最新 120 条记录；上方统计覆盖所有已归档有效样本。</div>}
        </div>
      </section>
    </>}
  </div>;
}
