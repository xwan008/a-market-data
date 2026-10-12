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


// 网站只读关联 Airtable 净持仓与公开盘中快照；不修改记录，也不制造买卖动作。
// 名称锚定：只识别明确写作“退出线/失效线/预警线”的人民币价格，不将日期、成本、历史高低点误作止损价。
export function extractExitLevels(conditions) {
 const list=[...new Set((Array.isArray(conditions)?conditions:[]).map(x=>String(x??'').trim()).filter(Boolean))];
 if(!list.length || list.some(x=>/暂未设置|尚未设置|待设置|未明确|尚无明确/.test(x)))
  return {state:'unconfirmed',levels:[],basis:null};
 const names={'预警线':'warning','核心退出线':'exit','首要退出线':'exit','第一道退出线':'exit','最终失效线':'final'};
 const matches=[];
 for(const rule of list){
  for(const m of rule.matchAll(/(预警线|核心退出线|首要退出线|第一道退出线|最终失效线)\s*[:：]?\s*(\d{1,5}(?:\.\d{1,3})?)\s*元/g)){
   const price=Number(m[2]);
   if(price>0 && Number.isFinite(price))matches.push({name:m[1],kind:names[m[1]],price});
  }
 }
 if(!matches.length)return {state:'unstructured',levels:[],basis:null};
 const dedup=new Map();
 for(const item of matches){
  const prev=dedup.get(item.name);
  if(prev && prev.price!==item.price)return {state:'conflict',levels:[],basis:null};
  dedup.set(item.name,item);
 }
 const levels=[...dedup.values()];
 // 一段解释文字中出现“仅盘中短破不算收盘确认”不意味着规则既是盘中又是收盘触发。
 const whole=list.join(' ');
 const basis=/日线收盘|收盘价严格低于|收盘价低于|收盘确认/.test(whole)?'close':null;
 if(!basis)return {state:'ambiguous',levels,basis:null};
 return {state:'structured',levels,basis};
}

export function evaluateExitCondition(conditions, price) {
 const list=(Array.isArray(conditions)?conditions:[]).map(x=>String(x||'').trim()).filter(Boolean);
 const extracted=extractExitLevels(list);
 const usable=typeof price==='number'&&Number.isFinite(price)&&price>0;
 if(extracted.state==='structured'){
  const levels=extracted.levels.map(level=>({...level,
   observation:usable?(price<level.price?'below':'not_below'):'no_quote'}));
  const exitLevels=levels.filter(x=>x.kind!=='warning');
  const warning=levels.filter(x=>x.kind==='warning'&&x.observation==='below');
  const breached=exitLevels.filter(x=>x.observation==='below');
  const printed=levels.map(x=>x.name+fixed(x.price)+'元').join(' · ');
  const first=exitLevels[0];
  if(!first)return {state:'review',label:'仅有预警线，尚无明确退出线',
   detail:'已保存 '+printed+'；无法将预警线自动升级为退出指令。',
   levels,threshold:null,basis:'close'};
  if(!usable)return {state:'await_price',label:'退出计划已记录 · 待有效盘中行情',
   detail:printed+'。条件需日线收盘严格低于相应价格才可确认，当前没有可用于核验的当日有效盘中报价。',
   levels,threshold:first.price,basis:'close'};
  if(breached.length){
   return {state:'close_pending',label:'盘中低于'+breached.map(x=>x.name+fixed(x.price)).join('、')+' · 待收盘确认',
    detail:'已发布的盘中快照价 '+fixed(price)+' 元低于 '+breached.map(x=>x.name+' '+fixed(x.price)+' 元').join('、')+
     '。这些退出条件要求有效日线收盘确认；不能把盘中触及当作已经触发卖出或完成减仓。',
    levels,threshold:first.price,basis:'close'};
  }
  if(warning.length){
   return {state:'warning_only',label:'盘中低于预警线'+fixed(warning[0].price)+' · 退出线待核验',
    detail:'盘中快照价 '+fixed(price)+' 元低于'+warning.map(x=>x.name+fixed(x.price)+'元').join('、')+
     '；但尚未低于已记录的退出线。所有正式退出条件仍须日线收盘确认。',
    levels,threshold:first.price,basis:'close'};
  }
  return {state:'close_not_yet',label:first.name+fixed(first.price)+' · 待收盘核验',
   detail:'盘中快照价 '+fixed(price)+' 元尚未低于已记录的退出线；是否满足日线退出条件，仍须依据有效收盘价格判断。',
   levels,threshold:first.price,basis:'close'};
 }
 if(extracted.state==='unconfirmed')return {state:'unconfirmed',label:'退出条件未明确',
  detail:'Airtable 尚无可核验的具体退出规则。不能用买点计划或历史结构低点自行替代。',
  levels:[]};
 if(extracted.state==='conflict')return {state:'review',label:'退出规则存在冲突',
  detail:'同名退出线出现不同价格，请先核实 Airtable 的规则版本。',levels:[]};
 if(extracted.state==='ambiguous')return {state:'review',label:'退出时点待核验',
  detail:'已记录 '+extracted.levels.map(x=>x.name+fixed(x.price)+'元').join(' · ')+'，但尚无明确收盘或盘中判定口径。',
  levels:extracted.levels.map(x=>({...x,observation:'unverified'}))};
 // 兼容此前的简单单线规则，其他复合文本保守地退回人工核验。
 if(list.length!==1)return {state:'review',label:'退出规则待复核',
  detail:'存在多条无法统一解析的退出条件，需确认顺序和生效口径。',levels:[]};
 const rule=list[0];
 const matches=[...rule.matchAll(/(?:跌破|低于|小于)\s*(?:人民币|[¥￥])?\s*(\d{1,5}(?:\.\d{1,3})?)\s*(?:元)?/g)];
 const threshold=matches.length===1?Number(matches[0][1]):null;
 if(!(threshold>0)||!Number.isFinite(threshold)||
   /止盈|上穿|高于|涨到|达到|区间|或者|或低于|\/|－|～/.test(rule))
  return {state:'review',label:'退出规则待复核',detail:'文本存在多目标或复杂条件，暂无法自动核验。',levels:[]};
 const close=/收盘|收市|日线/.test(rule),intraday=/盘中|实时|即时/.test(rule);
 if((close&&intraday)||(!close&&!intraday))
  return {state:'review',label:'退出时点待核验',detail:'不能用盘中报价替代收盘确认。',levels:[]};
 const levels=[{name:'预设退出线',kind:'exit',price:threshold,observation:usable?(price<threshold?'below':'not_below'):'no_quote'}];
 if(!usable)return {state:'await_price',label:'退出线'+fixed(threshold)+' · 待行情',
  detail:'已记录退出条件，但缺少有效当日报价；不推断是否触发。',levels,threshold,basis:close?'close':'intraday'};
 if(close)return {state:price<threshold?'close_pending':'close_not_yet',
  label:price<threshold?'盘中低于退出线'+fixed(threshold)+' · 待收盘确认':'退出线'+fixed(threshold)+' · 待收盘核验',
  detail:price<threshold?'盘中报价已低于预设退出线，但须有效收盘确认，不构成已触发退出。':'盘中报价未低于预设退出线；仍需有效收盘确认。',
  levels,threshold,basis:'close'};
 if(!/止损|退出|卖出|清仓|减仓|硬止损/.test(rule))
  return {state:'review',label:'退出规则待复核',detail:'盘中价格观察条件并非明确的退出动作。',levels};
 return {state:price<threshold?'intraday_touched':'intraday_not_touched',
  label:price<threshold?'预设盘中退出线'+fixed(threshold)+'已触及':'盘中退出线'+fixed(threshold)+'未触及',
  detail:price<threshold?'有效盘中快照价低于明确预设的盘中硬止损线，仅提示观察，不代表已经成交。':'最新有效盘中快照价未低于预设盘中退出线。',
  levels,threshold,basis:'intraday'};
}

export function assessHoldingRisk(position,monitor,today=shanghaiDay()){
 const original=Array.isArray(position?.conditions)?position.conditions:[];
 const ruleBase=evaluateExitCondition(original,null);
 const base={state:'unavailable',tone:'neutral',label:'暂无可核验风险判断',rule:ruleBase,evidence:[],last:null,marketDay:null};
 if(!position?.verified || !Number.isInteger(position.shares) || position.shares<=0)
  return {...base,state:'unverified',label:'持仓待核验',rule:{...ruleBase,detail:'持仓股数尚未核实；'+ruleBase.detail}};
 if(monitor?.result_kind!=='a_share_intraday_monitor_state'||monitor?.trade_date!==today)
  return {...base,state:'stale',label:ruleBase.state==='await_price'?ruleBase.label:'暂无当日持仓评估',
   rule:ruleBase,note:'未获取当日有效盘中扫描；不会拿历史行情核验今日退出条件。'};
 const scans=validSnapshots(monitor.stock_history?.[position.code],today);
 if(!scans.length)return {...base,state:'not_covered',marketDay:today,
  label:ruleBase.state==='await_price'?ruleBase.label:'本轮未覆盖持仓',
  rule:ruleBase,note:'当日冻结监测股票池未提供该股票的有效扫描。'};
 const last=scans.at(-1);
 if(typeof last.price!=='number'||!Number.isFinite(last.price)||last.price<=0)
  return {...base,state:'no_price',marketDay:today,last,
   label:ruleBase.state==='await_price'?ruleBase.label:'盘中报价不足',
   rule:ruleBase,note:'没有有效盘中快照价，退出线仅作为已登记计划展示。'};
 const rule=evaluateExitCondition(original,last.price);
 const evidence=[];
 if(typeof last.change_pct==='number'&&Number.isFinite(last.change_pct))
  evidence.push('盘中快照涨跌幅 '+pct(last.change_pct)+'（非有效收盘）');
 if(last.price_behavior)evidence.push('价格行为：'+last.price_behavior);
 if(typeof last.relative_to_industry_pct==='number'&&Number.isFinite(last.relative_to_industry_pct))
  evidence.push('相对所属行业 '+pct(last.relative_to_industry_pct));
 const low=last.latest_low?.price;
 if(typeof low==='number'&&Number.isFinite(low)&&low>0)
  evidence.push(last.price<low?'盘中价低于历史结构低点 '+fixed(low)+' 元；仍须结构确认':
   '历史结构低点 '+fixed(low)+' 元；盘中快照价尚未跌破');
 const sector=validSnapshots(monitor.industry_history?.[last.trend_name],today).at(-1);
 if(['衰退预警','分歧'].includes(sector?.current_state))
  evidence.push('所属板块盘中状态：'+sector.current_state+'（不独立触发退出）');
 const weak=last.price_behavior==='转弱'||
  (typeof last.change_pct==='number'&&last.change_pct<0&&
   typeof last.relative_to_industry_pct==='number'&&last.relative_to_industry_pct<0);
 const exitFocus=['intraday_touched','close_pending','warning_only','close_not_yet','intraday_not_touched','review','await_price'].includes(rule.state);
 const label=exitFocus?rule.label:
  rule.state==='unconfirmed'?(weak?'退出条件待明确 · 盘中走弱':'退出条件待明确'):
  rule.label;
 const state=rule.state==='intraday_touched'?'triggered':rule.state==='close_pending'?'pending':
  rule.state==='warning_only'?'warning':weak?'watch':'observing';
 const tone=state==='triggered'?'fall':state==='pending'||state==='warning'?'caution':weak?'caution':'neutral';
 if(weak)evidence.push('盘中走弱仅作为辅助风险信息，不能单独替代退出规则。');
 return {state,tone,label,rule,evidence,last,marketDay:today,
  note:'基于 Airtable 登记与当日已发布盘中快照；若需有效收盘确认，不代表已触发退出或自动成交。'};
}
