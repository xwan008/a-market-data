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
