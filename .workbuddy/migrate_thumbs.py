#!/usr/bin/env python3
"""一次性迁移：gallery/thumbs/<md5>.webp -> gallery/thumbs/<md5前2位>/<md5>.webp

只做 rename（不复制、不删除），文件名本身就是 md5 前 16 位，所以直接取文件名前 2 位当目录，
与 build_gallery.py 里 key[:2] 的分片规则完全一致。
"""
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T = os.path.join(ROOT, "gallery", "thumbs")

files = [f for f in os.listdir(T) if f.endswith(".webp") and os.path.isfile(os.path.join(T, f))]
print(f"待迁移 {len(files)} 个文件")

done = Counter()
for f in files:
    shard = f[:2]
    d = os.path.join(T, shard)
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, f)
    if os.path.exists(dst):
        print(f"⚠️ 目标已存在，跳过：{shard}/{f}", file=sys.stderr)
        continue
    os.replace(os.path.join(T, f), dst)
    done[shard] += 1

print(f"已迁入 {sum(done.values())} 个文件 / {len(done)} 个子目录")
if done:
    top = done.most_common(3)
    print("  最多的子目录:", ", ".join(f"{k}({v})" for k, v in top))
left = [f for f in os.listdir(T) if f.endswith(".webp")]
print(f"thumbs 根目录残留 .webp：{len(left)}")
