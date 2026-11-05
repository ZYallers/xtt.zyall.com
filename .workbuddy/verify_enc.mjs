// 临时校验：用 content.key 解开 data.enc.js，确认清单可解且缩略图路径都在磁盘上
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const key = Buffer.from(fs.readFileSync(path.join(ROOT, '.workbuddy/private/content.key'), 'utf8').trim(), 'base64');
const src = fs.readFileSync(path.join(ROOT, 'gallery/data.enc.js'), 'utf8');
const obj = JSON.parse(src.replace(/^[\s\S]*?window\.GALLERY_ENC=/, '').replace(/;\s*$/, ''));

const iv = Buffer.from(obj.i, 'base64');
const buf = Buffer.from(obj.d, 'base64');
const d = crypto.createDecipheriv('aes-256-gcm', key, iv);
d.setAuthTag(buf.subarray(buf.length - 16));
const plain = Buffer.concat([d.update(buf.subarray(0, buf.length - 16)), d.final()]).toString('utf8');
const data = JSON.parse(plain);

const miss = data.items.filter((i) => !i.th || !fs.existsSync(path.join(ROOT, i.th)));
console.log('解密成功，items =', data.items.length, '｜generated =', data.generated);
console.log('th 缺文件 =', miss.length, '｜shard 目录数 =', new Set(data.items.map((i) => i.th.split('/')[2])).size);
console.log('样例：', data.items[0].th, data.items[1].th, data.items[2210].th);
