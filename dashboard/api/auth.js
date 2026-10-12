import { authorized, cookieHeader, isConfigured, noStore, validatePassword } from '../lib/auth.js';

export default async function handler(req, res) {
  noStore(res);
  if (!isConfigured()) return res.status(503).json({ authenticated:false, error:'SITE_NOT_CONFIGURED' });
  if (req.method === 'GET') return res.status(200).json({ authenticated: authorized(req) });
  if (req.method === 'DELETE') {
    res.setHeader('Set-Cookie',cookieHeader(req,true));
    return res.status(200).json({ authenticated:false });
  }
  if (req.method !== 'POST') return res.status(405).json({error:'METHOD_NOT_ALLOWED'});
  const body = typeof req.body === 'string' ? (()=>{try{return JSON.parse(req.body)}catch{return {}}})() : req.body || {};
  const password = typeof body.password === 'string' ? body.password : '';
  if (!validatePassword(password)) return res.status(401).json({authenticated:false,error:'INVALID_CREDENTIALS'});
  res.setHeader('Set-Cookie',cookieHeader(req));
  return res.status(200).json({authenticated:true});
}
