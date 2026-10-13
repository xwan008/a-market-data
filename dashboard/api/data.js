import { authorized, noStore } from '../lib/auth.js';

const FILES = {
  registry: ['research/trend_registry.json','a_share_trend_registry'],
  trendHandoff: ['research/trend_handoff.json','a_share_trend_handoff'],
  buyHandoff: ['research/trend_buy_handoff.json',null],
  monitor: ['research/intraday_monitor_state.json','a_share_intraday_monitor_state'],
  holdingSnapshot: ['research/intraday_market_snapshot.json','a_share_intraday_market_snapshot'],
  holdingCharts: ['research/holding_chart_data.json','a_share_holding_charts'],
  crossdayArchive: ['research/intraday_crossday_archive.json','a_share_intraday_crossday_archive']
};
const TIMEOUT_MS = 12000;
const FIELDS = ['股票代码','交易标的','操作类型','价格（元）','实际成交股数','金额（元）','交易日期','记录日期','失效条件','复盘备注'];
const RISK_TABLE_NAME = '持仓风控计划';
const RISK_FIELDS = ['股票代码','股票名称','计划状态','生效日期','预警价格','首道退出价格','首道退出动作','首道减仓股数','最终退出价格','最终退出动作','触发依据','策略说明'];

async function getJson(url, headers = {}) {
  const response = await fetch(url, { headers, signal: AbortSignal.timeout(TIMEOUT_MS), cache:'no-store' });
  if (response.status === 404) return {error:'NOT_PUBLISHED'};
  if (!response.ok) return {error:`HTTP_${response.status}`};
  try { return {data:await response.json()}; } catch { return {error:'INVALID_JSON'}; }
}
async function getGithub(key) {
  const [path, kind] = FILES[key];
  const repo = process.env.GITHUB_REPOSITORY || 'xwan008/a-market-data';
  const ref = process.env.GITHUB_REF || 'main';
  if (!/^[\w.-]+\/[\w.-]+$/.test(repo) || !/^[\w./-]+$/.test(ref) || ref.includes('..')) return {error:'INVALID_REPOSITORY_CONFIG'};
  const url = `https://raw.githubusercontent.com/${repo}/${ref}/${path}`;
  const result = await getJson(url);
  if (result.data && ((kind && result.data.result_kind !== kind) || (key === 'buyHandoff' && result.data.schema_version !== 'trend_buy_handoff_v2')))
    return {error:'UNEXPECTED_SCHEMA'};
  return result;
}
async function getAirtable(kind='trades') {
  const { AIRTABLE_TOKEN: token, AIRTABLE_BASE_ID: base, AIRTABLE_TABLE_ID: table } = process.env;
  if (!token || !base || !table) return {error:'NOT_CONFIGURED'};
  if (!/^app[A-Za-z0-9]{14}$/.test(base) || !/^tbl[A-Za-z0-9]{14}$/.test(table)) return {error:'INVALID_CONFIG'};
  const records = [];
  let offset = null;
  const seen = new Set();
  do {
    const tablePath=kind==='riskPlans'?encodeURIComponent(RISK_TABLE_NAME):table;
    const url = new URL(`https://api.airtable.com/v0/${base}/${tablePath}`);
    url.searchParams.set('pageSize','100');
    for (const field of kind==='riskPlans'?RISK_FIELDS:FIELDS) url.searchParams.append('fields[]',field);
    if (offset) url.searchParams.set('offset',offset);
    const result = await getJson(url.toString(),{Authorization:`Bearer ${token}`});
    if (result.error) return {error:result.error};
    if (!Array.isArray(result.data?.records)) return {error:'INVALID_RESPONSE'};
    records.push(...result.data.records.map(record => ({ id:record.id, createdTime:record.createdTime, ...record.fields })));
    offset = result.data.offset || null;
    if (offset && seen.has(offset)) return {error:'PAGINATION_LOOP'};
    if (offset) seen.add(offset);
  } while (offset && seen.size < 50);
  if (offset) return {error:'PAGINATION_INCOMPLETE'};
  return {data:records};
}
export default async function handler(req, res) {
  noStore(res);
  if (req.method !== 'GET') return res.status(405).json({error:'METHOD_NOT_ALLOWED'});
  if (!authorized(req)) return res.status(401).json({error:'UNAUTHORIZED'});
  const keys = [...Object.keys(FILES),'airtable','riskPlans'];
  const results = await Promise.allSettled(keys.map(key => key === 'airtable'?getAirtable('trades'):key==='riskPlans'?getAirtable('riskPlans'):getGithub(key)));
  const datasets = {}, status = {};
  for (let i=0;i<keys.length;i++) {
    const result = results[i].status === 'fulfilled' ? results[i].value : {error:'SOURCE_UNAVAILABLE'};
    if ('data' in result) { datasets[keys[i]] = result.data; status[keys[i]] = 'OK'; }
    else { datasets[keys[i]] = null; status[keys[i]] = result.error; }
  }
  return res.status(200).json({ receivedAt:new Date().toISOString(), datasets, status });
}
