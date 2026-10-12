export const asArray = value => Array.isArray(value) ? value : [];
export const safeText = value => value == null || value === '' ? '—' : String(value);
export const fixed = (value,digits=2) => typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString('zh-CN',{minimumFractionDigits:digits,maximumFractionDigits:digits}) : '—';
export const shanghaiDay = (date = new Date()) => new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(date);
export const fmtTime = value => { if (!value) return '—'; const date = new Date(value); return Number.isNaN(date.getTime()) ? String(value) : new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(date); };
export const pct = number => typeof number === 'number' && Number.isFinite(number) ? `${number > 0 ? '+' : ''}${fixed(number)}%` : '—';
export const extractRecords = history => {
  if (Array.isArray(history)) return history;
  if (!history || typeof history !== 'object') return [];
  return Object.entries(history).flatMap(([key, item]) => {
    if (Array.isArray(item)) return item;
    if (item && typeof item === 'object') return [{...item, key}];
    return [];
  });
};
// 同一板块/个股在一天中可能存在多轮记录，只展示该分组最新的已归档轮次。
export const latestMonitorRecords = history => {
  if (Array.isArray(history)) return history;
  if (!history || typeof history !== 'object') return [];
  return Object.entries(history).flatMap(([key,record]) => {
    const latest = Array.isArray(record) ? record.at(-1) : record;
    return latest && typeof latest === 'object' ? [{...latest,key}] : [];
  });
};
const codeOk = code => /^\d{6}$/.test(String(code || '').trim());
function operation(type) {
  const action = typeof type === 'object' && type !== null ? type.name : type;
  if (/清仓|卖出|减仓|止盈|止损/.test(String(action || ''))) return 'sell';
  if (/买入|加仓|建仓|首仓|补仓/.test(String(action || ''))) return 'buy';
  return null;
}
export function summarizeTrades(rawRecords) {
  if (!Array.isArray(rawRecords)) return {positions:[],invalidCount:0,recordCount:0};
  const byCode = new Map(); let invalidCount = 0;
  for (const record of rawRecords) {
    const code = String(record['股票代码'] || '').trim();
    if (!codeOk(code)) { invalidCount++; continue; }
    if (!byCode.has(code)) byCode.set(code,[]);
    byCode.get(code).push(record);
  }
  const positions = [];
  for (const [code, rows] of byCode) {
    rows.sort((a,b) => String(a['交易日期']||a.createdTime||'').localeCompare(String(b['交易日期']||b.createdTime||'')) || String(a.createdTime||'').localeCompare(String(b.createdTime||'')));
    let shares = 0, cost = 0, costKnown = true, valid = true;
    const reasons = [];
    const seenDates = new Map();
    for (const row of rows) {
      const kind = operation(row['操作类型']);
      const qty = Number(row['实际成交股数']);
      const price = Number(row['价格（元）']);
      const day = row['交易日期'];
      if (!day || !kind || !Number.isInteger(qty) || qty <= 0) { valid = false; reasons.push('成交日期、操作类型或股数缺失'); continue; }
      const kinds = seenDates.get(day) || new Set(); kinds.add(kind); seenDates.set(day,kinds);
      if (kind === 'buy') {
        shares += qty;
        if (Number.isFinite(price) && price > 0 && costKnown) cost += qty * price;
        else costKnown = false;
      } else {
        if (qty > shares) { valid = false; reasons.push('卖出股数大于可核实持仓'); continue; }
        if (costKnown && shares) cost -= cost / shares * qty;
        shares -= qty;
      }
    }
    if ([...seenDates.values()].some(v=>v.size > 1)) { costKnown = false; reasons.push('同日买卖顺序需核验，成本暂不估算'); }
    if (shares <= 0 && valid) continue;
    const last = rows.at(-1) || {};
    const name = rows.findLast?.(row=>row['交易标的'])?.['交易标的'] || code;
    const conditions = [...new Set(rows.map(row=>String(row['失效条件']||'').trim()).filter(Boolean))];
    positions.push({code,name,shares:valid?shares:null,avgCost:valid && costKnown && shares > 0 ? cost/shares:null,costValue:valid && costKnown && shares > 0 ? cost:null,verified:valid,issues:[...new Set(reasons)],conditions,lastDate:last['交易日期']||null,recordCount:rows.length});
  }
  positions.sort((a,b)=>Number(b.verified)-Number(a.verified) || b.shares-a.shares || a.code.localeCompare(b.code));
  return {positions,invalidCount,recordCount:rawRecords.length};
}
export const formatSource = state => ({OK:'已连接',NOT_PUBLISHED:'尚未发布',NOT_CONFIGURED:'待配置',UNAUTHORIZED:'无访问权限',UNEXPECTED_SCHEMA:'结构不匹配',PAGINATION_INCOMPLETE:'分页读取未完成'}[state] || (state ? '暂不可用' : '未检查'));


// 仅根据文件中真实的同交易日有效扫描绘图；不插值、不生成合成评分。
export function validSnapshots(history, tradeDate) {
  if (!Array.isArray(history) || !/^\d{4}-\d{2}-\d{2}$/.test(String(tradeDate||''))) return [];
  const byTime = new Map();
  for (const item of history) {
    if (!item || item.data_quality !== 'READY' || typeof item.scan_at !== 'string' ||
        !item.scan_at.startsWith(tradeDate) || Number.isNaN(Date.parse(item.scan_at))) continue;
    byTime.set(item.scan_at, item);
  }
  return [...byTime.values()].sort((a,b)=>Date.parse(a.scan_at)-Date.parse(b.scan_at));
}

export const snapshotChange = (rows, field, multiplier=1) => {
  const samples=rows.filter(row=>typeof row?.[field]==='number' && Number.isFinite(row[field]));
  if(samples.length<2)return null;
  return (samples.at(-1)[field]-samples[0][field])*multiplier;
};

// 只有 trend_handoff 中明确提供的 rank 才是正式名次，其余标为未上榜。
export function rankedTrendRows(registry, handoff, history, tradeDate, mode='formal') {
  const priority=new Map((Array.isArray(handoff?.signals)?handoff.signals:[])
    .filter(x=>Number.isInteger(x?.rank)&&x.rank>0&&x.trend_name)
    .map(x=>[x.trend_name,x.rank]));
  const items=(Array.isArray(registry?.trends)?registry.trends:[]).map((item,index)=>{
    const records=validSnapshots(history?.[item.trend_name],tradeDate);
    return {...item,priorityRank:priority.get(item.trend_name)??null,
      intradayDelta:snapshotChange(records,'up_ratio',100),originalIndex:index};
  });
  const formal=(a,b)=>(a.priorityRank??Infinity)-(b.priorityRank??Infinity) || a.originalIndex-b.originalIndex;
  if(mode==='change') return items.sort((a,b)=>{
    const aa=a.intradayDelta==null?-1:Math.abs(a.intradayDelta);
    const bb=b.intradayDelta==null?-1:Math.abs(b.intradayDelta);
    return bb-aa || formal(a,b);
  });
  return items.sort(formal);
}


// A 股图表语义：只比较同一指标首末两个有效数值，红涨绿跌；不足两点为中性。
export function seriesDirection(rows,field='value') {
  const values=(Array.isArray(rows)?rows:[]).map(row=>row?.[field])
    .filter(value=>typeof value==='number' && Number.isFinite(value));
  if (values.length < 2) return 'neutral';
  return values.at(-1)>values[0]?'rise':values.at(-1)<values[0]?'fall':'neutral';
}

// 研究状态与涨跌分开编码：红色仅用于趋势确认/扩散等正向描述，候选为金、观察为蓝灰。
export function statusTone(raw) {
  const value=String(raw??'').trim();
  if (value==='READY') return 'ready';
  if (/趋势确认|趋势扩散|扩散|增强|走强|上涨/.test(value)) return 'rise';
  if (/候选趋势|候选/.test(value)) return 'candidate';
  if (/观察|待复核/.test(value)) return 'watch';
  if (/分歧|修复|关注|等待确认/.test(value)) return 'caution';
  if (/失效|衰退|退化|破位|收缩|回落|转弱|下跌|减弱/.test(value)) return 'fall';
  if (value==='WAIT'||value==='暂停') return 'neutral';
  return 'neutral';
}


// 研究账本中的 3-5 个历史事件：这是独立于盘中快照的状态核验序列，缺失交易日不补值。
export function trendEvents(trend,limit=5){
 const records=Array.isArray(trend?.state_history)?trend.state_history:[];
 const byDay=new Map();
 for(const record of records){
  if(!record || !/^\d{4}-\d{2}-\d{2}$/.test(String(record.trade_date||'')))continue;
  byDay.set(record.trade_date,{...record,market_state:record.to||null});
 }
 return [...byDay.values()].sort((a,b)=>a.trade_date.localeCompare(b.trade_date)).slice(-Math.max(1,Math.min(30,limit)));
}

// 盘中历史只来自已归档的最后一次盘中扫描，不能当作历史收盘价或重算走势。
export function archivedDays(archive,monitor,identifier,kind='sector',limit=5){
 const source=archive?.result_kind==='a_share_intraday_crossday_archive'&&Array.isArray(archive?.days)?archive.days:[];
 const map=new Map();
 const selector=kind==='stock'?'stocks':'trends';
 for(const day of source){
  const date=day?.trade_date;
  if(!/^\d{4}-\d{2}-\d{2}$/.test(String(date||'')))continue;
  const record=day[selector]?.[identifier];
  if(!record || typeof record!=='object' || typeof record.scan_at!=='string' || !record.scan_at.startsWith(date))continue;
  if(record.data_quality && record.data_quality!=='READY' && record.data_quality!=='DEGRADED')continue;
  map.set(date,{trade_date:date,source:'archived_last_scan',...record});
 }
 const date=monitor?.trade_date;
 if(monitor?.result_kind==='a_share_intraday_monitor_state'&&/^\d{4}-\d{2}-\d{2}$/.test(String(date||''))){
  const rows=validSnapshots((kind==='stock'?monitor.stock_history:monitor.industry_history)?.[identifier],date);
  const last=rows.at(-1);
  if(last)map.set(date,{...last,trade_date:date,source:'today_scans'});
 }
 return [...map.values()].sort((a,b)=>a.trade_date.localeCompare(b.trade_date)).slice(-Math.max(1,Math.min(30,limit)));
}


// 已认证前端对 Airtable 净持仓与当日公共行情的只读关联；不落盘、不补行情、不生成交易指令。
// 只有明确标注盘中硬触发的用户退出条件，才可以被盘中采样判为“触及”。
export function evaluateExitCondition(conditions, price) {
 const list=(Array.isArray(conditions)?conditions:[]).map(x=>String(x||'').trim()).filter(Boolean);
 if(!list.length || list.some(x=>/暂未设置|尚未设置|待设置|待结合|未明确|尚无明确/.test(x))){
  return {state:'unconfirmed',label:'退出条件未明确',detail:'Airtable 未记录可核验的具体退出规则。不能依据买点榜价格自行设置止损线。'};
 }
 if(list.length!==1)return {state:'review',label:'退出规则待复核',detail:'存在多条退出条件，需确认适用顺序及触发口径。'};
 const rule=list[0];
 // 不解析多目标区间、止盈止损混用或无明确时间口径的文字；宁可提示待复核。
 const matches=[...rule.matchAll(/(?:跌破|低于|小于)\\s*(?:人民币|[¥￥])?\\s*(\\d{1,5}(?:\\.\\d{1,3})?)\\s*(?:元)?/g)];
 const threshold=matches.length===1?Number(matches[0][1]):null;
 if(!(threshold>0) || !Number.isFinite(threshold) ||
   /止盈|上穿|高于|涨到|达到|区间|或者|或低于|\/|－|～/.test(rule)){
  return {state:'review',label:'退出规则待复核',detail:'已记录文字条件，但缺少可唯一验证的下破价格或存在复合条件。'};
 }
 const close=/收盘|收市|日线/.test(rule);
 const intraday=/盘中|实时|即时/.test(rule);
 if((close&&intraday)||(!close&&!intraday))return {state:'review',label:'退出规则待复核',detail:'退出条件的判断时点不明确，不能将盘中采样当成已确认触发。'};
 if(typeof price!=='number'||!Number.isFinite(price)||price<=0){
  return {state:'unavailable',label:'缺少有效报价',detail:'无法用无效盘中报价核验预设价格条件。'};
 }
 if(close){
  return {state:price<threshold?'close_pending':'close_not_yet',label:price<threshold?'盘中触及 · 待收盘确认':'待收盘核验',
   detail:price<threshold?`盘中快照价 ${fixed(price)} 元低于预设 ${fixed(threshold)} 元，但需有效日线收盘确认，不构成已触发退出。`:
   `盘中快照价 ${fixed(price)} 元未跌破预设 ${fixed(threshold)} 元；收盘条件仍待当日有效收盘核验。`,
   threshold,basis:'close'};
 }
 if(!/止损|退出|卖出|清仓|减仓|硬止损/.test(rule)){
  return {state:'review',label:'退出规则待复核',detail:'盘中价格观察规则并未明确指定退出动作，不自动转成止损指令。'};
 }
 return {state:price<threshold?'intraday_touched':'intraday_not_touched',
  label:price<threshold?'预设盘中条件已触及':'盘中条件未触及',
  detail:price<threshold?`最新有效盘中快照价 ${fixed(price)} 元低于预设 ${fixed(threshold)} 元；只报告触及情况，不代表已成交。`:
    `最新有效盘中快照价 ${fixed(price)} 元未跌破预设 ${fixed(threshold)} 元。`,
  threshold,basis:'intraday'};
}

export function assessHoldingRisk(position, monitor, today=shanghaiDay()) {
 const base={state:'unavailable',tone:'neutral',label:'暂无可核验风险判断',rule:{state:'unavailable',label:'规则未评估',detail:'暂无当日行情'},evidence:[],last:null,marketDay:null};
 if(!position?.verified || !Number.isInteger(position.shares) || position.shares<=0)
  return {...base,state:'unverified',label:'持仓待核验',rule:{state:'unavailable',label:'待核验',detail:'持仓数量未核实，不判断退出条件。'}};
 const ruleText=Array.isArray(position.conditions)?position.conditions:[];
 if(monitor?.result_kind!=='a_share_intraday_monitor_state' || monitor?.trade_date!==today)
  return {...base,state:'stale',label:'暂无当日持仓评估',
   rule:{state:'unavailable',label:'等待当日数据',detail:'不能使用前一交易日盘中报价触发今天的退出条件。'}};
 const scans=validSnapshots(monitor.stock_history?.[position.code],today);
 if(!scans.length)return {...base,state:'not_covered',marketDay:today,label:'本轮未覆盖持仓',
   rule:{state:'unavailable',label:'行情未覆盖',detail:'当天冻结的监测股票池缺少该股票的有效扫描，不根据其他标的推断风险。'}};
 const last=scans.at(-1);
 if(typeof last.price!=='number'||!Number.isFinite(last.price)||last.price<=0)
  return {...base,state:'no_price',marketDay:today,last,label:'盘中报价不足',
   rule:{state:'unavailable',label:'报价不足',detail:'无有效盘中成交参考价，无法核验价格退出条件。'}};
 const rule=evaluateExitCondition(ruleText,last.price);
 const evidence=[];
 if(typeof last.change_pct==='number'&&Number.isFinite(last.change_pct))
  evidence.push(`盘中快照涨跌幅 ${pct(last.change_pct)}（非收盘涨跌幅）`);
 if(last.price_behavior)evidence.push(`价格行为：${last.price_behavior}`);
 if(typeof last.relative_to_industry_pct==='number'&&Number.isFinite(last.relative_to_industry_pct))
  evidence.push(`相对所属行业 ${pct(last.relative_to_industry_pct)}`);
 const lastLow=last.latest_low?.price;
 if(typeof lastLow==='number'&&Number.isFinite(lastLow)&&lastLow>0)
  evidence.push(last.price<lastLow?
   `盘中价低于历史结构低点 ${fixed(lastLow)} 元；是否有效破位仍需确认`:
   `历史结构低点 ${fixed(lastLow)} 元；当前快照价尚未跌破`);
 const industry=monitor.industry_history?.[last.trend_name];
 const sectorLast=validSnapshots(industry,today).at(-1);
 if(sectorLast?.current_state==='衰退预警'||sectorLast?.current_state==='分歧')
  evidence.push(`所属板块盘中状态：${sectorLast.current_state}（单独不触发卖出）`);
 const weak=last.price_behavior==='转弱' ||
   (typeof last.change_pct==='number'&&last.change_pct<0&&typeof last.relative_to_industry_pct==='number'&&last.relative_to_industry_pct<0);
 const touched=rule.state==='intraday_touched';
 const pending=rule.state==='close_pending';
 const label=touched?'预设盘中条件已触及':pending?'盘中触及 · 待收盘确认':
   weak?'盘中走弱 · '+(rule.state==='unconfirmed'?'退出规则待设':'风险观察'):
   rule.state==='unconfirmed'?'退出条件待明确':rule.state==='review'?'退出规则待复核':'持仓观察';
 return {state:touched?'triggered':pending?'pending':weak?'watch':'observing',
  tone:touched?'fall':pending?'caution':weak?'caution':'neutral',
  label,rule,evidence,last,marketDay:today,
  note:'仅基于已发布的盘中快照与 Airtable 登记；不替代有效收盘核验或自动买卖。'};
}
