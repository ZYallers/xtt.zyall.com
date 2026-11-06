/**
 * 微信 JS-SDK 签名服务 · Cloudflare Worker
 * ---------------------------------------------------------------------------
 * 作用：前端页面在微信里打开时，拿当前地址来换 wx.config 需要的四个参数。
 *       AppSecret 只存在本 Worker 的环境变量里，永远不下发到浏览器。
 *
 * 部署三件事（具体操作见 Worker 目录下的说明）：
 *   1. KV 命名空间绑定为  WX_KV      （缓存 access_token / jsapi_ticket）
 *   2. 环境变量（加密类型）APPID / APPSECRET
 *   3. 把部署出来的地址填到 assets/js/wxshare.js 的 SIGN_ENDPOINT
 *
 * 路由：GET /sign?url=<encodeURIComponent(页面地址)>  →  { appId, timestamp, nonceStr, signature }
 *       GET /                                       →  健康检查
 */

/* ---------- 只允许给自己的站点签名，防止被别人白用 ---------- */
const ALLOW_HOSTS = ['xtt.zyall.com', 'www.xtt.zyall.com'];
const ALLOW_ORIGINS = ['https://xtt.zyall.com', 'https://www.xtt.zyall.com'];

const TOKEN_KEY = 'wx:token';
const TICKET_KEY = 'wx:ticket';
const SAFETY = 400;          // 提前 400 秒视为过期，避开边界抖动

/* 同一 isolate 内的内存缓存：并发请求不会重复去微信取 token
   （微信的 access_token 是全局唯一的，重复获取会让上一个提前失效，必须防抖） */
const memo = { token: '', tokenExp: 0, ticket: '', ticketExp: 0 };
const inflight = { token: null, ticket: null };

function corsHeaders(origin) {
  const ok = ALLOW_ORIGINS.indexOf(origin) > -1;
  return {
    'Access-Control-Allow-Origin': ok ? origin : 'null',
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400',
    Vary: 'Origin',
  };
}

function json(obj, status, extra) {
  return new Response(JSON.stringify(obj), {
    status: status || 200,
    headers: Object.assign({ 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' }, extra || {}),
  });
}

async function sha1(str) {
  const buf = await crypto.subtle.digest('SHA-1', new TextEncoder().encode(str));
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, '0')).join('');
}

function nonce(len) {
  const s = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
  let out = '';
  const rnd = crypto.getRandomValues(new Uint8Array(len || 16));
  for (let i = 0; i < rnd.length; i++) out += s[rnd[i] % s.length];
  return out;
}

/* ---------- access_token ---------- */
function getToken(env) {
  const now = Date.now() / 1000;
  if (memo.token && memo.tokenExp > now) return Promise.resolve(memo.token);
  if (inflight.token) return inflight.token;

  inflight.token = (async () => {
    const cached = await env.WX_KV.get(TOKEN_KEY, 'json');
    if (cached && cached.exp > now) {
      memo.token = cached.v;
      memo.tokenExp = cached.exp;
      return cached.v;
    }
    const url =
      'https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential' +
      '&appid=' + encodeURIComponent(env.APPID) +
      '&secret=' + encodeURIComponent(env.APPSECRET);
    const res = await fetch(url);
    const data = await res.json();
    if (!data.access_token) throw new Error('token-failed: ' + JSON.stringify(data));
    const exp = now + (data.expires_in || 7200) - SAFETY;
    memo.token = data.access_token;
    memo.tokenExp = exp;
    await env.WX_KV.put(TOKEN_KEY, JSON.stringify({ v: data.access_token, exp }), {
      expirationTtl: Math.max(60, Math.floor(exp - now)),
    });
    return data.access_token;
  })();

  return inflight.token.finally(() => { inflight.token = null; });
}

/* ---------- jsapi_ticket ---------- */
function getTicket(env, force) {
  const now = Date.now() / 1000;
  if (!force && memo.ticket && memo.ticketExp > now) return Promise.resolve(memo.ticket);
  if (!force && inflight.ticket) return inflight.ticket;

  inflight.ticket = (async () => {
    if (!force) {
      const cached = await env.WX_KV.get(TICKET_KEY, 'json');
      if (cached && cached.exp > now) {
        memo.ticket = cached.v;
        memo.ticketExp = cached.exp;
        return cached.v;
      }
    }
    const token = await getToken(env);
    const res = await fetch(
      'https://api.weixin.qq.com/cgi-bin/ticket/getticket?access_token=' +
        encodeURIComponent(token) + '&type=jsapi'
    );
    const data = await res.json();
    if (data.errcode !== 0 || !data.ticket) {
      /* 40001/42001 = token 失效：清掉 token 缓存重来一次 */
      if (data.errcode === 40001 || data.errcode === 42001 || data.errcode === 40014) {
        memo.token = '';
        memo.tokenExp = 0;
        await env.WX_KV.delete(TOKEN_KEY);
      }
      throw new Error('ticket-failed: ' + JSON.stringify(data));
    }
    const exp = now + (data.expires_in || 7200) - SAFETY;
    memo.ticket = data.ticket;
    memo.ticketExp = exp;
    await env.WX_KV.put(TICKET_KEY, JSON.stringify({ v: data.ticket, exp }), {
      expirationTtl: Math.max(60, Math.floor(exp - now)),
    });
    return data.ticket;
  })();

  return inflight.ticket.finally(() => { inflight.ticket = null; });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = request.headers.get('Origin') || '';
    const cors = corsHeaders(origin);

    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
    if (request.method !== 'GET') return json({ ok: false, err: 'method-not-allowed' }, 405, cors);

    if (url.pathname === '/' || url.pathname === '') {
      return json({
        ok: true,
        service: 'wx-js-sdk-sign',
        appid: env.APPID ? env.APPID.slice(0, 6) + '***' : '(未配置 APPID)',
        kv: env.WX_KV ? 'bound' : '(未绑定 WX_KV)',
      }, 200, cors);
    }

    if (url.pathname !== '/sign') return json({ ok: false, err: 'not-found' }, 404, cors);
    if (!env.APPID || !env.APPSECRET) return json({ ok: false, err: 'appid-or-secret-missing' }, 500, cors);

    /* 待签名地址：必须是 https + 白名单域名，去掉 hash（微信签名的 url 不含 #） */
    const raw = url.searchParams.get('url') || '';
    let page;
    try {
      page = new URL(raw);
    } catch (e) {
      return json({ ok: false, err: 'bad-url' }, 400, cors);
    }
    if (page.protocol !== 'https:') return json({ ok: false, err: 'https-only' }, 400, cors);
    if (ALLOW_HOSTS.indexOf(page.hostname) === -1) return json({ ok: false, err: 'host-not-allowed' }, 403, cors);
    const pageUrl = page.origin + page.pathname + page.search;   // 丢掉 hash

    try {
      let ticket;
      try {
        ticket = await getTicket(env, false);
      } catch (e) {
        ticket = await getTicket(env, true);      // token 失效类错误，清缓存重试一次
      }
      const timestamp = Math.floor(Date.now() / 1000);
      const noncestr = nonce(16);
      /* 顺序与大小写都不能改：jsapi_ticket=..&noncestr=..&timestamp=..&url=.. */
      const signature = await sha1(
        'jsapi_ticket=' + ticket +
        '&noncestr=' + noncestr +
        '&timestamp=' + timestamp +
        '&url=' + pageUrl
      );
      return json({ ok: true, appId: env.APPID, timestamp, nonceStr: noncestr, signature, url: pageUrl }, 200, cors);
    } catch (e) {
      return json({ ok: false, err: String(e && e.message ? e.message : e) }, 502, cors);
    }
  },
};
