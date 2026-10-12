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


// 结构化风控计划契约：价格/股数/判断时点仅来自 Airtable typed fields。
// "策略说明"和历史交易记录的"失效条件"都只用于人工阅读，决不解析成数值规则。
const selectName = raw => typeof raw==='object'&&raw!==null?raw.name:raw;
const money = value => typeof value==='number'&&Number.isFinite(value)&&value>0?value:null;
const sixDigit = value => /^\d{6}$/.test(String(value??'').trim());
const validDay = value => /^\d{4}-\d{2}-\d{2}$/.test(String(value??''));

export function normalizeRiskPlans(rawPlans, today=shanghaiDay()){
 if(!Array.isArray(rawPlans))return new Map();
 const byCode=new Map();
 for(const row of rawPlans){
  const code=String(row?.['股票代码']??'').trim();
  if(!sixDigit(code))continue;
  const status=String(selectName(row['计划状态'])??'');
  const day=String(row['生效日期']??'');
  const plan={
   id:row.id??null,code,name:String(row['股票名称']??code),
   status,effectiveDate:day,warningPrice:money(row['预警价格']),
   firstPrice:money(row['首道退出价格']),firstAction:String(selectName(row['首道退出动作'])??''),
   firstQuantity:row['首道减仓股数']??null,
   finalPrice:money(row['最终退出价格']),finalAction:String(selectName(row['最终退出动作'])??''),
   basis:String(selectName(row['触发依据'])??''),
   notes:String(row['策略说明']??'')
  };
  if(!byCode.has(code))byCode.set(code,[]);
  byCode.get(code).push(plan);
 }
 const resolved=new Map();
 for(const [code,list] of byCode){
  const active=list.filter(x=>x.status==='生效');
  if(active.length>1){
   resolved.set(code,{state:'invalid',issue:'同一股票存在多条生效计划，请停用旧版本。',plan:null});
   continue;
  }
  if(!active.length){
   resolved.set(code,{state:'missing',issue:'尚无生效的结构化退出计划。',plan:null});
   continue;
  }
  const p=active[0],issues=[];
  if(!validDay(p.effectiveDate))issues.push('生效日期缺失或格式无效');
  else if(p.effectiveDate>today)issues.push('生效日期尚未到达');
  if(!p.firstPrice)issues.push('首道退出价格必须为正数');
  if(!['减仓','清仓剩余'].includes(p.firstAction))issues.push('首道退出动作未指定');
  if(p.firstAction==='减仓'&&(!Number.isInteger(p.firstQuantity)||p.firstQuantity<=0))
   issues.push('首道减仓股数必须为正整数');
  if(p.firstAction==='清仓剩余'&&p.firstQuantity!=null)
   issues.push('清仓剩余时不应填写减仓股数');
  if((p.finalPrice===null)!==(p.finalAction===''))
   issues.push('最终退出价格与动作需要同时填写');
  if(p.finalPrice!==null){
   if(p.firstPrice!==null&&p.finalPrice>=p.firstPrice)issues.push('最终退出价须低于首道退出价');
   if(p.firstAction==='清仓剩余')issues.push('首道已清仓，不能继续设置最终退出');
   if(p.finalAction!=='清仓剩余')issues.push('当前最终退出只支持清仓剩余');
  }
  if(p.warningPrice!==null&&p.firstPrice!==null&&p.warningPrice<=p.firstPrice)
   issues.push('预警价应高于首道退出价');
  if(!['日线收盘','盘中'].includes(p.basis))issues.push('触发依据必须选择日线收盘或盘中');
  resolved.set(code,{state:issues.length?'invalid':'ready',issue:issues.join('；'),plan:p});
 }
 return resolved;
}

export function attachRiskPlans(portfolio,rawPlans,sourceStatus='OK',today=shanghaiDay()){
 const records=normalizeRiskPlans(rawPlans,today);
 return {...portfolio,positions:portfolio.positions.map(position=>{
  if(sourceStatus!=='OK')return {...position,riskPlan:null,planState:'unavailable',planIssue:'风控计划数据源暂不可用（'+formatSource(sourceStatus)+'）。'};
  const entry=records.get(position.code);
  if(!entry)return {...position,riskPlan:null,planState:'missing',planIssue:'尚未在「持仓风控计划」录入生效规则。'};
  if(entry.state!=='ready')return {...position,riskPlan:null,planState:entry.state,planIssue:entry.issue};
  const p=entry.plan;
  if(p.firstAction==='减仓'&&p.firstQuantity>position.shares)
   return {...position,riskPlan:null,planState:'invalid',planIssue:'首道拟减仓股数超过已核实净持仓，请核对交易记录和计划。'};
  return {...position,riskPlan:p,planState:'ready',planIssue:null};
 })};
}

export function evaluateExitCondition(positionOrPlan,price){
 const position=positionOrPlan?.riskPlan!==undefined?positionOrPlan:{riskPlan:positionOrPlan,planState:positionOrPlan?'ready':'missing'};
 const plan=position.riskPlan;
 const hasQuote=typeof price==='number'&&Number.isFinite(price)&&price>0;
 if(position.planState!=='ready'||!plan)return {state:'no_plan',
  label:position.planState==='unavailable'?'风控计划数据源不可用':
   position.planState==='invalid'?'退出计划待核对':'退出计划待录入',
  detail:position.planIssue||'请在 Airtable「持仓风控计划」填写结构化字段，文字备注不用于解析退出线。',
  levels:[],basis:null};
 const basis=plan.basis==='日线收盘'?'close':'intraday';
 const levels=[
  ...(plan.warningPrice!==null?[{name:'预警价',kind:'warning',price:plan.warningPrice,action:null,quantity:null}]:[]),
  {name:'首道退出价',kind:'exit',price:plan.firstPrice,action:plan.firstAction,
   quantity:plan.firstAction==='减仓'?plan.firstQuantity:null},
  ...(plan.finalPrice!==null?[{name:'最终退出价',kind:'final',price:plan.finalPrice,
   action:plan.finalAction,quantity:null}]:[])
 ].map(x=>({...x,observation:hasQuote?(price<x.price?'below':'not_below'):'no_quote'}));
 const exit=levels.filter(x=>x.kind!=='warning'&&x.observation==='below');
 const warning=levels.find(x=>x.kind==='warning'&&x.observation==='below');
 const primary=levels.find(x=>x.kind==='exit');
 const describe=line=>line.name+fixed(line.price)+'元';
 if(!hasQuote)return {state:'await_price',label:'退出计划已记录 · 待有效行情',
  detail:levels.map(describe).join(' · ')+'；未取得有效同日行情，不计算退出条件是否触及。',
  levels,basis};
 if(exit.length){
  const highest=exit.at(-1);
  const action=highest.action==='减仓'?'拟减仓 '+highest.quantity+' 股':'拟清仓剩余';
  return {state:basis==='close'?'close_pending':'intraday_touched',
   label:(basis==='close'?'盘中低于':'已触及')+describe(highest)+(basis==='close'?' · 待收盘确认':' · 盘中条件'),
   detail:'已发布盘中快照价 '+fixed(price)+' 元低于 '+describe(highest)+'（'+action+'）。'+
    (basis==='close'?'此规则要求有效日线收盘严格低于退出线，盘中触及不等于正式触发。':
     '仅表示盘中快照观察到越线，不代表已委托或成交。'),
   levels,basis};
 }
 if(warning)return {state:'warning_only',label:'盘中低于'+describe(warning)+' · 关注退出线',
  detail:'已发布盘中快照价 '+fixed(price)+' 元低于预警价，但尚未低于退出价。'+
    (basis==='close'?'正式退出仍须日线收盘确认。':'预警不等于退出条件。'),
  levels,basis};
 return {state:basis==='close'?'close_not_yet':'intraday_not_touched',
  label:describe(primary)+(basis==='close'?' · 待收盘核验':' · 未触及'),
  detail:'最新有效盘中快照价 '+fixed(price)+' 元尚未低于已登记的退出价。'+
   (basis==='close'?'是否满足退出条件仍以有效日线收盘为准。':'本轮盘中条件未触及。'),
  levels,basis};
}

export function assessHoldingRisk(position,monitor,today=shanghaiDay()){
 const ruleBase=evaluateExitCondition(position,null);
 const base={state:'unavailable',tone:'neutral',label:ruleBase.label,rule:ruleBase,evidence:[],last:null,marketDay:null};
 if(!position?.verified||!Number.isInteger(position.shares)||position.shares<=0)
  return {...base,state:'unverified',label:'持仓待核验',
   rule:{...ruleBase,detail:'持仓股数尚未核实；'+ruleBase.detail}};
 if(monitor?.result_kind!=='a_share_intraday_monitor_state'||monitor?.trade_date!==today)
  return {...base,state:'stale',note:'无当日有效盘中扫描，不能用历史价格判定今天的退出条件。'};
 const scans=validSnapshots(monitor.stock_history?.[position.code],today);
 if(!scans.length)return {...base,state:'not_covered',marketDay:today,
  note:'该持仓未进入当日冻结个股监测池；仍可查看结构化退出规则。'};
 const last=scans.at(-1);
 if(typeof last.price!=='number'||!Number.isFinite(last.price)||last.price<=0)
  return {...base,state:'no_price',marketDay:today,last,note:'无有效当日报价，退出规则仅展示，不计算是否触及。'};
 const rule=evaluateExitCondition(position,last.price);
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
 if(weak)evidence.push('盘中走弱是辅助证据，不能替代预设退出价格与触发依据。');
 const state=rule.state==='intraday_touched'?'triggered':rule.state==='close_pending'?'pending':
  rule.state==='warning_only'?'warning':rule.state==='no_plan'?'missing':weak?'watch':'observing';
 const tone=state==='triggered'?'fall':state==='pending'||state==='warning'?'caution':weak?'caution':'neutral';
 return {state,tone,label:rule.label,rule,evidence,last,marketDay:today,
  note:'只比较 Airtable 结构化价格与同日已发布行情；需要收盘确认的条件不代表已触发退出，更不代表自动成交。'};
}
