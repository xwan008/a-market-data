import {authorized, noStore} from '../lib/auth.js';

const FILES = {
  validationSummary: 'validation/results/summary.json',
  validationTrends: 'validation/results/trends.json',
  validationStocks: 'validation/results/stocks.json'
};

async function readPublished(path) {
  const repo = process.env.GITHUB_REPOSITORY || 'xwan008/a-market-data';
  const ref = process.env.GITHUB_REF || 'main';
  if (!/^[\w.-]+\/[\w.-]+$/.test(repo) || !/^[\w./-]+$/.test(ref) || ref.includes('..'))
    return {error: 'INVALID_REPOSITORY_CONFIG'};
  try {
    const response = await fetch('https://raw.githubusercontent.com/' + repo + '/' + ref + '/' + path,
      {cache:'no-store',signal:AbortSignal.timeout(12000)});
    if (response.status === 404) return {error:'NOT_PUBLISHED'};
    if (!response.ok) return {error:'HTTP_' + response.status};
    const value = await response.json();
    if (value.schema_version !== 1) return {error:'UNEXPECTED_SCHEMA'};
    return {data:value};
  } catch {
    return {error:'SOURCE_UNAVAILABLE'};
  }
}

export default async function handler(req, res) {
  noStore(res);
  if (req.method !== 'GET') return res.status(405).json({error:'METHOD_NOT_ALLOWED'});
  if (!authorized(req)) return res.status(401).json({error:'UNAUTHORIZED'});
  const keys = Object.keys(FILES);
  const answers = await Promise.all(keys.map(key => readPublished(FILES[key])));
  const datasets = {}, status = {};
  for (const [i, key] of keys.entries()) {
    const result = answers[i];
    datasets[key] = result.data || null;
    status[key] = result.data ? 'OK' : result.error;
  }
  return res.status(200).json({status,datasets,receivedAt:new Date().toISOString()});
}
