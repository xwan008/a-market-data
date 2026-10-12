import test from 'node:test';
import assert from 'node:assert/strict';
import {authorized,cookieHeader,validatePassword} from '../lib/auth.js';
import authHandler from '../api/auth.js';
import dataHandler from '../api/data.js';

function response(){return {headers:{},code:200,setHeader(k,v){this.headers[k]=v},status(n){this.code=n;return this},json(v){this.data=v;return this}}}
test('未配置安全密钥时默认拒绝',()=>{const original={...process.env};delete process.env.DASHBOARD_PASSWORD;delete process.env.SESSION_SECRET;assert.equal(authorized({headers:{}}),false);Object.assign(process.env,original)});
test('密码登录、Cookie 签名及篡改拒绝', async()=>{
 process.env.DASHBOARD_PASSWORD='a_strong_password_123';process.env.SESSION_SECRET='0123456789abcdef0123456789abcdef';
 assert.equal(validatePassword('wrong'),false);assert.equal(validatePassword('a_strong_password_123'),true);
 const res=response();await authHandler({method:'POST',headers:{},body:{password:'a_strong_password_123'}},res);
 assert.equal(res.code,200);
 const cookie=res.headers['Set-Cookie'].split(';')[0];assert.equal(authorized({headers:{cookie}}),true);
 assert.equal(authorized({headers:{cookie:cookie.replace(/.$/,'X')}}),false);
 const out=response();await dataHandler({method:'GET',headers:{}},out);assert.equal(out.code,401);
});
