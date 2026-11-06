/**
 * 微信 JS-SDK 签名服务 · 阿里云函数计算 FC（事件函数 + HTTP 触发器）
 * ---------------------------------------------------------------------------
 * 为什么不用 Cloudflare：workers.dev 在国内实测完全不通（请求超时），
 * 微信内页面调不到签名接口，等于白做。国内节点才行。
 *
 * 运行环境：Node.js 18 或 20，入口 index.handler，无需任何第三方依赖
 * 环境变量：APPID / APPSECRET（在函数配置里加，类型选「加密」）
 *
 * 部署步骤见回复里的说明。部署完访问  https://<你的触发器域名>/  可自检。
 */

'use strict';

const crypto = require('crypto');
const https = require('https');

/* ---------- 只给自己的站点签名 ---------- */
const ALLOW_HOSTS = ['xtt.zyall.com', 'www.xtt.zyall.com'];
const ALLOW_ORIGINS = ['https://xtt.zyall.com', 'https://www.xtt.zyall.com'];

const SAFETY = 400;   // 提前 400 秒视为过期

/* 函数实例热复用时复用凭证；冷启动重新取一次，代价是两次 HTTPS 请求 */
const memo = { token: '', tokenExp: 0, ticket: '', ticketExp: 0 };
const inflight = { token: null, ticket: null };

function httpGetJson(url) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { timeout: 8000 }, (res) => {
      let buf = '';
      res.setEncoding('utf8');
      res.on('data', (d) => { buf += d; });
      res.on('end', () => {
        try { resolve(JSON.parse(buf)); }
        catch (e) { reject(new Error('bad-json: ' + buf.slice(0, 120))); }
      });
    });
    req.on('timeout', () => { req.destroy(new Error('wx-api-timeout')); });
    req.on('error', reject);
  });
}

function getToken() {
  const now = Math.floor(Date.now() / 1000);
  if (memo.token && memo.tokenExp > now) return Promise.resolve(memo.token);
  if (inflight.token) return inflight.token;

  const appid = process.env.APPID;
  const secret = process.env.APPSECRET;
  inflight.token = httpGetJson(
    'https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential' +
    '&appid=' + encodeURIComponent(appid) +
    '&secret=' + encodeURIComponent(secret)
  ).then((data) => {
    if (!data.access_token) throw new Error('token-failed: ' + JSON.stringify(data));
    memo.token = data.access_token;
    memo.tokenExp = now + (data.expires_in || 7200) - SAFETY;
    return memo.token;
  }).finally(() => { inflight.token = null; });

  return inflight.token;
}

function getTicket(force) {
  const now = Math.floor(Date.now() / 1000);
  if (!force && memo.ticket && memo.ticketExp > now) return Promise.resolve(memo.ticket);
  if (!force && inflight.ticket) return inflight.ticket;

  inflight.ticket = getToken().then((token) =>
    httpGetJson('https://api.weixin.qq.com/cgi-bin/ticket/getticket?access_token=' +
      encodeURIComponent(token) + '&type=jsapi')
  ).then((data) => {
    if (data.errcode !== 0 || !data.ticket) {
      if ([40001, 40014, 42001].indexOf(data.errcode) > -1) {
        memo.token = ''; memo.tokenExp = 0;      // token 失效，下次重新取
      }
      throw new Error('ticket-failed: ' + JSON.stringify(data));
    }
    memo.ticket = data.ticket;
    memo.ticketExp = now + (data.expires_in || 7200) - SAFETY;
    return memo.ticket;
  }).finally(() => { inflight.ticket = null; });

  return inflight.ticket;
}

function sha1(str) {
  return crypto.createHash('sha1').update(str, 'utf8').digest('hex');
}

function nonce(len) {
  const s = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
  const rnd = crypto.randomBytes(len || 16);
  let out = '';
  for (let i = 0; i < rnd.length; i++) out += s[rnd[i] % s.length];
  return out;
}

function cors(origin) {
  const ok = ALLOW_ORIGINS.indexOf(origin) > -1;
  return {
    'Access-Control-Allow-Origin': ok ? origin : 'null',
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400',
    Vary: 'Origin',
  };
}

function reply(statusCode, obj, extraHeaders) {
  return {
    statusCode,
    headers: Object.assign({
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
    }, extraHeaders || {}),
    body: JSON.stringify(obj),
    isBase64Encoded: false,
  };
}

/* HTTP 触发器把请求信息放在 event 里；不同版本 FC 结构略有差异，都兼容一下 */
function parseEvent(event) {
  let e = event;
  if (Buffer.isBuffer(e)) e = JSON.parse(e.toString('utf8'));
  if (typeof e === 'string') e = JSON.parse(e);
  const method = (e.requestContext && e.requestContext.http && e.requestContext.http.method) ||
                 e.httpMethod || 'GET';
  const qs = e.queryParameters || {};
  let url = e.rawPath || e.path || '/';
  // 有的版本把查询串带在 path 里
  let query = Object.assign({}, qs);
  if (url.indexOf('?') > -1) {
    const [p, q] = url.split('?');
    url = p;
    q.split('&').forEach((kv) => {
      const [k, v] = kv.split('=');
      if (k && !(k in query)) query[k] = decodeURIComponent(v || '');
    });
  }
  const headers = e.headers || {};
  return { method: method.toUpperCase(), path: url, query, headers };
}

exports.handler = async function (event) {
  let req;
  try {
    req = parseEvent(event);
  } catch (e) {
    return reply(400, { ok: false, err: 'bad-event' });
  }

  const origin = req.headers.origin || req.headers.Origin || '';
  const headers = cors(origin);

  if (req.method === 'OPTIONS') return { statusCode: 204, headers, body: '', isBase64Encoded: false };

  const path = (req.path || '/').replace(/\/+$/, '') || '/';

  if (path === '/') {
    return reply(200, {
      ok: true,
      service: 'wx-js-sdk-sign',
      appid: process.env.APPID ? process.env.APPID.slice(0, 6) + '***' : '(未配置 APPID)',
      secret: process.env.APPSECRET ? 'set' : '(未配置 APPSECRET)',
    }, headers);
  }

  if (path !== '/sign') return reply(404, { ok: false, err: 'not-found' }, headers);
  if (!process.env.APPID || !process.env.APPSECRET) {
    return reply(500, { ok: false, err: 'appid-or-secret-missing' }, headers);
  }

  const raw = req.query.url || '';
  let page;
  try { page = new URL(decodeURIComponent(raw)); }
  catch (e) { return reply(400, { ok: false, err: 'bad-url' }, headers); }

  if (page.protocol !== 'https:') return reply(400, { ok: false, err: 'https-only' }, headers);
  if (ALLOW_HOSTS.indexOf(page.hostname) === -1) {
    return reply(403, { ok: false, err: 'host-not-allowed' }, headers);
  }
  const pageUrl = page.origin + page.pathname + page.search;   // 去掉 hash

  try {
    let ticket;
    try { ticket = await getTicket(false); }
    catch (e) { ticket = await getTicket(true); }              // token 失效则重试一次

    const timestamp = Math.floor(Date.now() / 1000);
    const noncestr = nonce(16);
    /* 参数顺序与大小写固定，改了就签名不通过 */
    const signature = sha1(
      'jsapi_ticket=' + ticket +
      '&noncestr=' + noncestr +
      '&timestamp=' + timestamp +
      '&url=' + pageUrl
    );
    return reply(200, {
      ok: true, appId: process.env.APPID, timestamp, nonceStr: noncestr, signature, url: pageUrl,
    }, headers);
  } catch (e) {
    return reply(502, { ok: false, err: String(e && e.message ? e.message : e) }, headers);
  }
};
