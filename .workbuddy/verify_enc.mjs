// 临时校验：用 content.key 解开 data.enc.js（v2=gzip+加密）与 data-legacy.enc.js，确认可解且缩略图路径都在磁盘上
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import zlib from 'node:zlib';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const key = Buffer.from(fs.readFileSync(path.join(ROOT, '.workbuddy/private/content.key'), 'utf8').trim(), 'base64');

function open(file) {
  const src = fs.readFileSync(path.join(ROOT, file), 'utf8');
  const obj = JSON.parse(src.replace(/^[\s\S]*?window\.GALLERY_ENC=/, '').replace(/;\s*$/, ''));
  const iv = Buffer.from(obj.i, 'base64');
  const buf = Buffer.from(obj.d, 'base64');
  const d = crypto.createDecipheriv('aes-256-gcm', key, iv);
  d.setAuthTag(buf.subarray(buf.length - 16));
  let plain = Buffer.concat([d.update(buf.subarray(0, buf.length - 16)), d.final()]);
  if (obj.v >= 2) plain = zlib.gunzipSync(plain);
  return { v: obj.v, data: JSON.parse(plain.toString('utf8')) };
}

const { v, data } = open('gallery/data.enc.js');
const miss = data.items.filter((i) => !i.th || !fs.existsSync(path.join(ROOT, i.th)));
console.log('data.enc.js v' + v, '解密成功，items =', data.items.length, '｜generated =', data.generated);
console.log('th 缺文件 =', miss.length, '｜shard 目录数 =', new Set(data.items.map((i) => i.th.split('/')[2])).size);
console.log('样例：', data.items[0].th, data.items[1].th, data.items[2210].th);

if (fs.existsSync(path.join(ROOT, 'gallery/data-legacy.enc.js'))) {
  const lg = open('gallery/data-legacy.enc.js');
  const ok = JSON.stringify(lg.data) === JSON.stringify(data);
  console.log('data-legacy.enc.js v' + lg.v, '解密成功，与 v2 内容一致 =', ok);
}
