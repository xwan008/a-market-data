import React, {useMemo, useState} from 'react';
import {BarChart3, CalendarDays, Clock3, ShieldCheck, AlertCircle} from 'lucide-react';

const num = x => typeof x === 'number' && Number.isFinite(x) ? x.toLocaleString('zh-CN') : '—';
const percent = x => typeof x === 'number' && Number.isFinite(x)
  ? (x > 0 ? '+' : '') + x.toFixed(2) + '%' : '—';
const resultText = result => {
  if (!result) return '—';
  if (result.state === 'matured') return percent(result.excess_vs_market_pct);
  if (result.state === 'pending') return '观察中';
  if (result.state === 'data_gap') return '数据缺失';
  return '无法评估';
};
const tone = result => result?.state === 'matured'
  ? (result.excess_vs_market_pct > 0 ? 'market-up' : result.excess_vs_market_pct < 0 ? 'market-down' : '')
  : 'muted';
const endLabel = row => row.ending === 'lost_confirmation' ? '已失去确认'
  : row.ending === 'censored_data_gap' ? '数据中断' : '仍在观察';

function Stat({label, value, note}) {
  return <div className="metric-card">
    <div className="metric-top"><span>{label}</span></div>
    <div className="metric-number">{value}</div>
    <div className="metric-meta">{note}</div>
  </div>;
}

export default function TrendValidation({summary, trends, stocks, status}) {
  const [tab, setTab] = useState('trend');
  const [horizon, setHorizon] = useState('5');
  const [search, setSearch] = useState('');
  const [signalFilter, setSignalFilter] = useState('ALL');
  const [expanded, setExpanded] = useState(null);
  const ok = status?.validationSummary === 'OK' &&
    status?.validationTrends === 'OK' && status?.validationStocks === 'OK';
  const data = summary || {};
  const trendRows = Array.isArray(trends?.items) ? trends.items : [];
  const stockRows = Array.isArray(stocks?.items) ? stocks.items : [];
  const rows = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (tab === 'trend') return trendRows.filter(x =>
      (x.trend_name || '').toLowerCase().includes(term))
      .slice().sort((a,b) => b.start_date.localeCompare(a.start_date));
    return stockRows.filter(x =>
      (signalFilter === 'ALL' || x.status === signalFilter) &&
      [x.company_name, x.code, x.trend_name].some(v => String(v || '').toLowerCase().includes(term)))
      .slice().sort((a,b) => b.trade_date.localeCompare(a.trade_date));
  }, [tab, search, signalFilter, trendRows, stockRows]);
  const selected = rows.find(x => (tab === 'trend'
    ? x.trend_name + '#' + x.start_date : x.code + '#' + x.trade_date + '#' + x.source_run_id) === expanded);
  const matured = data.horizon_stats?.[horizon] || {};

  return <div className="validation-page">
    <div className="page-intro">
      <div><h1>趋势验证</h1>
        <p>独立审查历史正式信号的持续性和未来表现，不参与当前选股。</p></div>
      <div className="asof"><CalendarDays size={15}/> 截至 {data.as_of_trade_date || '尚无完成样本'}</div>
    </div>
    <div className="decision-bottom" style={{marginBottom:16}}>
      <ShieldCheck size={15}/> 仅使用发布后行情；信号日收盘至未来收盘属于观察收益，并非可成交收益。
      归档断档不算趋势失败；未完成样本不计算成功率。
    </div>
    {!ok ? <section className="panel" style={{padding:30}}>
      <div className="empty"><AlertCircle size={23}/>
        <strong>验证结果正在积累</strong>
        <p>独立归档在首个完整收盘研究完成后生成；不会用未经核实的历史数据填充结果。</p>
        <small>归档 {status?.validationSummary || '待发布'} · 趋势 {status?.validationTrends || '待发布'} · 个股 {status?.validationStocks || '待发布'}</small>
      </div>
    </section> : <>
      <div className="metrics-grid" style={{marginBottom:16}}>
        <Stat label="归档交易日" value={num(data.archive_days)} note="完整正式研究的每日存档"/>
        <Stat label="趋势确认事件" value={num(data.trend_episodes)} note="按连续确认区间去重"/>
        <Stat label="已结束确认" value={num(data.closed_confirmations)} note="正式降级，不等于产业失效"/>
        <Stat label="确认一天即降级" value={num(data.one_day_confirmations)} note={data.one_day_confirmation_pct == null ? '样本不足' : percent(data.one_day_confirmation_pct) + ' · 仅已观察到降级的事件'}/>
      </div>
      <section className="panel" style={{padding:16,marginBottom:16}}>
        <div className="panel-head"><div><h3>未来表现</h3><p>统一对比全市场等权日收益代理基准；样本尚未充分成熟时不作有效性结论。</p></div></div>
        <div className="intraday-tab-switch" role="group" aria-label="收益观察窗口">
          {['1','3','5','10','20'].map(n => <button key={n} type="button"
            className={horizon === n ? 'active' : ''}
            aria-pressed={horizon === n} onClick={() => setHorizon(n)}>{n} 日</button>)}
        </div>
        <div className="portfolio-overview">
          <div><span>已成熟趋势样本</span><strong>{num(matured.trend_matured)}</strong><small>平均超额 {percent(matured.trend_avg_excess_vs_market_pct)}</small></div>
          <div><span>已成熟个股样本</span><strong>{num(matured.stock_matured)}</strong><small>平均超额 {percent(matured.stock_avg_excess_vs_market_pct)}</small></div>
        </div>
      </section>
      <section className="panel" style={{padding:16}}>
        <div className="panel-head"><div><h3>历史信号观察</h3>
          <p>一个板块每次连续确认形成一个事件；个股按每日正式研究信号记录。</p></div></div>
        <div className="intraday-tab-switch" role="group" aria-label="验证对象">
          <button type="button" className={tab === 'trend' ? 'active' : ''} aria-pressed={tab === 'trend'}
            onClick={() => {setTab('trend');setExpanded(null)}}>板块验证 · {trendRows.length}</button>
          <button type="button" className={tab === 'stock' ? 'active' : ''} aria-pressed={tab === 'stock'}
            onClick={() => {setTab('stock');setExpanded(null)}}>个股验证 · {stockRows.length}</button>
        </div>
        <div className="table-controls" style={{marginTop:12}}>
          <div className="search"><input value={search} onChange={e => setSearch(e.target.value)}
            placeholder={tab === 'trend' ? '搜索趋势名称' : '搜索股票、代码或所属板块'} /></div>
          {tab === 'stock' && <div className="filter-select"><select value={signalFilter}
            onChange={e => setSignalFilter(e.target.value)}>
            <option value="ALL">全部状态</option><option value="READY">READY</option>
            <option value="WAIT">WAIT</option><option value="UNCERTAIN">UNCERTAIN</option>
            <option value="DROP">DROP</option>
          </select></div>}
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <thead><tr>
              <th>{tab === 'trend' ? '趋势' : '股票 / 板块'}</th>
              <th>信号日</th><th>{tab === 'trend' ? '确认天数' : '状态'}</th>
              <th>未来 {horizon} 日超额</th><th>进度</th>
            </tr></thead>
            <tbody>{rows.slice(0,120).map(row => {
              const key = tab === 'trend' ? row.trend_name + '#' + row.start_date
                : row.code + '#' + row.trade_date + '#' + row.source_run_id;
              const r = row.horizons?.[horizon];
              return <React.Fragment key={key}><tr className={key === expanded ? 'row-selected' : ''}
                onClick={() => setExpanded(key === expanded ? null : key)} style={{cursor:'pointer'}}>
                <td><strong>{tab === 'trend' ? row.trend_name : row.company_name || row.code}</strong>
                  {tab === 'stock' && <small>{row.code} · {row.trend_name}</small>}</td>
                <td>{tab === 'trend' ? row.start_date : row.trade_date}</td>
                <td>{tab === 'trend' ? row.confirmed_sessions + ' 日' : row.status}</td>
                <td className={tone(r)}>{resultText(r)}</td>
                <td className="soft-text">{tab === 'trend' ? endLabel(row) : r?.state === 'matured' ? '已完成' : r?.state === 'pending' ? '观察中' : '数据待核验'}</td>
              </tr>{key === expanded && <tr><td colSpan={5}>
                <div style={{padding:'10px 4px',lineHeight:1.9}}>
                  {tab === 'trend'
                    ? <span>确认始于 {row.start_date} · 最后确认 {row.last_date} · 首次降级 {row.first_downgrade_date || '未观察到'} · 冻结成分股 {row.frozen_constituent_count} 只</span>
                    : <span>研究日期 {row.trade_date} · 源 run_id {row.source_run_id} · 相对冻结板块超额 {percent(r?.excess_vs_sector_pct)}</span>}
                  <div>观察收益 {percent(r?.return_pct)} · 市场基准 {percent(r?.market_return_pct)} · 对照日期 {r?.target_date || '尚未满足窗口'}</div>
                  <small className="muted"><Clock3 size={12}/> 状态：{r?.state || 'unavailable'}。READY 尚未模拟交易触发和止损，不代表实际可得收益。</small>
                </div>
              </td></tr>}</React.Fragment>;
            })}</tbody>
          </table>
        </div>
        {!rows.length && <p className="muted" style={{padding:20}}>暂无符合筛选条件的有效验证样本。</p>}
        {rows.length > 120 && <p className="muted" style={{padding:12}}>为控制页面长度，仅展示最新 120 条；统计包含完整已归档样本。</p>}
      </section>
    </>}
  </div>;
}
