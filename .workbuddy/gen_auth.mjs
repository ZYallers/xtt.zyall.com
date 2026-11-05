#!/usr/bin/env node
/**
 * 生成登录凭据 + 加密相册清单
 *
 * 日常（只新增了资源，账号不变）：
 *   node .workbuddy/gen_auth.mjs
 *   → 复用 .workbuddy/private/content.key 里的内容密钥，已登录的人不用重新登录
 *
 * 新增/修改账号（密码从 stdin 传入，不落盘）：
 *   printf '[{"u":"账号","p":"密码"}]' | node .workbuddy/gen_auth.mjs
 *
 * 轮换密钥（所有会话强制失效，必须同时给出全部账号）：
 *   printf '[{"u":"账号","p":"密码"}]' | node .workbuddy/gen_auth.mjs --new-key
 *
 * 产出：
 *   assets/js/accounts.js   每个账号：salt + PBKDF2 派生密钥包裹后的内容密钥
 *   gallery/data.enc.js     AES-256-GCM 加密后的清单
 *
 * 说明：脚本本身不含任何明文密码。内容密钥 K 存在 .workbuddy/private/content.key
 *      （权限 600，位于站点目录之外，绝不可上传）。
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

// 仓库根目录 = 本文件所在目录（.workbuddy/）的上一级，不用写死绝对路径
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PLAIN = path.join(ROOT, '.workbuddy', 'private', 'data.json');
const LEGACY = path.join(ROOT, 'gallery', 'data.js');   // 旧版明文清单，存在则读取后删除
const DATA_ENC = path.join(ROOT, 'gallery', 'data.enc.js');
const ACCOUNTS = path.join(ROOT, 'assets', 'js', 'accounts.js');
const PRIVATE = path.join(ROOT, '.workbuddy', 'private');
const KEYFILE = path.join(PRIVATE, 'content.key');
const ITER = 310000;      // PBKDF2-SHA256 迭代次数
const SALT_LEN = 16;

const b64 = (buf) => Buffer.from(buf).toString('base64');

function readStdin() {
  if (process.stdin.isTTY) return '';   // 终端直接运行时不要卡在等输入
  try {
    return fs.readFileSync(0, 'utf8');
  } catch {
    return '';
  }
}

function wrapKey(password, salt, key) {
  const kek = crypto.pbkdf2Sync(Buffer.from(password, 'utf8'), salt, ITER, 32, 'sha256');
  const iv = crypto.randomBytes(12);
  const c = crypto.createCipheriv('aes-256-gcm', kek, iv);
  const ct = Buffer.concat([c.update(key), c.final()]);
  return { iv, ct: Buffer.concat([ct, c.getAuthTag()]) };
}

function encryptPayload(plain, key) {
  const iv = crypto.randomBytes(12);
  const c = crypto.createCipheriv('aes-256-gcm', key, iv);
  const ct = Buffer.concat([c.update(Buffer.from(plain, 'utf8')), c.final()]);
  return { iv, ct: Buffer.concat([ct, c.getAuthTag()]) };
}

const wantNewKey = process.argv.includes('--new-key');

const stdin = readStdin().trim();
const raw = stdin ? JSON.parse(stdin) : [];
if (!Array.isArray(raw)) {
  console.error('stdin 需要是 [{"u":"账号","p":"密码"}]');
  process.exit(1);
}
const hasAccounts = raw.length > 0;

/* ---- 0. 内容密钥 K：默认复用，--new-key 才轮换 ---- */
let key = null;
let rotated = false;
if (!wantNewKey && fs.existsSync(KEYFILE)) {
  const buf = Buffer.from(fs.readFileSync(KEYFILE, 'utf8').trim(), 'base64');
  if (buf.length === 32) key = buf;
}
if (!key) {
  key = crypto.randomBytes(32);
  rotated = true;
}

if (wantNewKey && !hasAccounts) {
  console.error('--new-key 会让所有会话失效，必须同时传入全部账号密码。');
  process.exit(1);
}
if (!hasAccounts && rotated) {
  console.error('没有可复用的内容密钥，必须从 stdin 传入全部账号密码才能生成。');
  console.error('  printf \'[{"u":"账号","p":"密码"}]\' | node .workbuddy/gen_auth.mjs');
  process.exit(1);
}

fs.mkdirSync(PRIVATE, { recursive: true });
if (rotated) {
  fs.writeFileSync(KEYFILE, key.toString('base64') + '\n', 'utf8');
  try { fs.chmodSync(KEYFILE, 0o600); } catch {}
}

if (!hasAccounts && !fs.existsSync(ACCOUNTS)) {
  console.error('assets/js/accounts.js 不存在，必须传入账号密码。');
  process.exit(1);
}

let plain;
if (fs.existsSync(PLAIN)) {
  plain = fs.readFileSync(PLAIN, 'utf8');
} else if (fs.existsSync(LEGACY)) {
  const src = fs.readFileSync(LEGACY, 'utf8');
  plain = JSON.stringify(JSON.parse(src.replace(/^window\.GALLERY_DATA\s*=\s*/, '').replace(/;\s*$/, '')));
} else {
  console.error('缺少明文清单，请先运行 build_gallery.py');
  process.exit(1);
}
const json = JSON.parse(plain);

/* ---- 1. 账号（没传就保留原文件，不动已登录的人） ---- */
let accountsJs = null;
if (hasAccounts) {
  const users = raw.map(({ u, p }) => {
    const salt = crypto.randomBytes(SALT_LEN);
    const { iv, ct } = wrapKey(p, salt, key);
    return { u, s: b64(salt), i: b64(iv), k: b64(ct) };
  });
  accountsJs =
    '/* 登录凭据：仅存 PBKDF2 派生后的密文，不含明文密码 */\n' +
    'window.ACCOUNTS=' + JSON.stringify({ v: 1, it: ITER, users }) + ';\n';
  fs.writeFileSync(ACCOUNTS, accountsJs, 'utf8');
}

/* ---- 2. 加密清单 ---- */
// 每次加密的 IV 都是随机的，所以哪怕明文一字未改，产物也不同。
// 明文没变就跳过写盘：否则每次重建都多出一个全新的 data.enc.js（约 0.9MB），白撑大 git。
// 轮换密钥时必须重写（旧密文用新密钥解不开）。
const SHAFILE = path.join(PRIVATE, 'data.sha');
const plainSha = crypto.createHash('sha256').update(plain).digest('hex');
const prevSha = fs.existsSync(SHAFILE) ? fs.readFileSync(SHAFILE, 'utf8').trim() : '';
const skipEnc = !rotated && prevSha === plainSha && fs.existsSync(DATA_ENC);

let encSize = 0;
if (skipEnc) {
  encSize = fs.statSync(DATA_ENC).size;
} else {
  const { iv, ct } = encryptPayload(plain, key);
  const encJs =
    '/* 加密后的相册清单（AES-256-GCM），密钥需登录后派生 */\n' +
    'window.GALLERY_ENC=' + JSON.stringify({ v: 1, i: b64(iv), d: b64(ct) }) + ';\n';
  fs.writeFileSync(DATA_ENC, encJs, 'utf8');
  fs.writeFileSync(SHAFILE, plainSha + '\n', 'utf8');
  encSize = encJs.length;
}

/* ---- 3. 明文下线 ---- */
fs.mkdirSync(PRIVATE, { recursive: true });
fs.writeFileSync(PLAIN, plain, 'utf8');
if (fs.existsSync(LEGACY)) fs.unlinkSync(LEGACY);

console.log(accountsJs
  ? `账号 ${raw.length} 个 → assets/js/accounts.js (${(accountsJs.length / 1024).toFixed(1)} KB)`
  : '账号：未改动（复用 assets/js/accounts.js）');
console.log(`密钥：${rotated ? '已轮换（所有会话失效，需重新登录）' : '复用 content.key（已登录的人不受影响）'}`);
console.log(`清单 ${json.items.length} 项 → gallery/data.enc.js (${(encSize / 1e6).toFixed(2)} MB)${
  skipEnc ? '，明文未变化已跳过重写' : ''}，明文 sha256:${plainSha.slice(0, 16)}`);
console.log('明文清单只保存在 .workbuddy/private/data.json（禁止上传到站点）');
