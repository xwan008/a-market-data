import { createHmac, timingSafeEqual } from 'node:crypto';

const TTL_SECONDS = 12 * 60 * 60;
const COOKIE = 'ash_session';
const configured = () => Boolean(process.env.DASHBOARD_PASSWORD?.length >= 12 && process.env.SESSION_SECRET?.length >= 32);
const digest = (value) => createHmac('sha256', process.env.SESSION_SECRET).update(value).digest('base64url');
const equal = (a, b) => {
  const aa = Buffer.from(String(a));
  const bb = Buffer.from(String(b));
  return aa.length === bb.length && timingSafeEqual(aa, bb);
};
export const isConfigured = configured;
export function validatePassword(password) { return configured() && equal(password || '', process.env.DASHBOARD_PASSWORD); }
export function cookieHeader(req, clear = false) {
  const expires = Math.floor(Date.now() / 1000) + TTL_SECONDS;
  const value = clear ? '' : `${expires}.${digest(`v1.${expires}`)}`;
  const secure = process.env.VERCEL || req.headers['x-forwarded-proto'] === 'https' ? '; Secure' : '';
  return `${COOKIE}=${value}; HttpOnly; SameSite=Strict; Path=/api; Max-Age=${clear ? 0 : TTL_SECONDS}${secure}`;
}
export function authorized(req) {
  if (!configured()) return false;
  const cookie = (req.headers.cookie || '').split(';').map(v => v.trim()).find(v => v.startsWith(`${COOKIE}=`));
  if (!cookie) return false;
  const [expire, signature, ...extra] = cookie.slice(COOKIE.length + 1).split('.');
  if (extra.length || !/^\d{10,}$/.test(expire || '') || !signature || Number(expire) <= Date.now() / 1000) return false;
  return equal(signature, digest(`v1.${expire}`));
}
export function noStore(res) { res.setHeader('Cache-Control', 'private, no-store, max-age=0');res.setHeader('X-Content-Type-Options','nosniff'); }
