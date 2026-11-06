#!/usr/bin/env python3
"""生成候选照片接触表，供人工挑选分享卡片的配图。

分享图的「好看」没法靠打分完全判断（表情、构图、有没有意思），所以把候选
铺成一张带编号的网格，人工圈号最省事。每格已经过 warmify，看到的就是成品效果。

用法：
    PYTHONPATH=/tmp/qrlib python3 .workbuddy/icons/make_contact_sheet.py [候选张数]
输出：
    /tmp/cards/candidates.jpg   编号网格
    /tmp/cards/candidates.json  编号 → 原图路径
"""
import importlib.util
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('card', os.path.join(HERE, 'make_share_card.py'))
card = importlib.util.module_from_spec(spec)
spec.loader.exec_module(card)

import numpy as np

CELL, PAD, COLS = 200, 10, 6
SANS = card.SANS
OUT_DIR = '/tmp/cards'

WANT = int(sys.argv[1]) if len(sys.argv) > 1 else 48
POOL = 420          # 参与打分的抽样张数


def sharpness(img):
    import cv2
    g = cv2.cvtColor(np.asarray(img.convert('RGB')), cv2.COLOR_RGB2GRAY)
    return float(cv2.Laplacian(g, cv2.CV_64F).var())


def square(img, size):
    w, h = img.size
    s = min(w, h)
    img = img.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2))
    return img.resize((size, size), Image.LANCZOS)


def main():
    with open(card.DATA, encoding='utf-8') as f:
        items = json.load(f)['items']
    pool = [it for it in items if it.get('th') and it.get('t') == 'i']
    if not pool:
        sys.exit('清单里没有照片')

    step = max(1, len(pool) // POOL)
    cand = [(i * step, it) for i, it in enumerate(pool[::step][:POOL])]

    rows = []
    for idx, it in cand:
        path = os.path.join(card.ROOT, it['th'])
        try:
            im = Image.open(path).convert('RGB')
        except Exception:
            continue
        small = im.copy()
        small.thumbnail((320, 320), Image.LANCZOS)
        base, has_face = card.photo_score(small)
        if not has_face:                       # 只要画面里能看见人的
            continue
        rows.append({'i': idx, 'score': base + min(1.0, sharpness(small) / 320) * 16,
                     'path': path})

    if not rows:
        sys.exit('没有可用候选')

    # 按时间分 8 段各取若干，避免 48 张全挤在同一年
    rows.sort(key=lambda r: r['i'])
    segs = 8
    per = max(1, WANT // segs)
    picks = []
    n = len(rows)
    for k in range(segs):
        seg = rows[n * k // segs: n * (k + 1) // segs]
        seg.sort(key=lambda r: -r['score'])
        picks.extend(seg[:per])
    picks = picks[:WANT]
    picks.sort(key=lambda r: r['i'])

    grid_r = (len(picks) + COLS - 1) // COLS
    W = COLS * (CELL + PAD) + PAD
    H = grid_r * (CELL + PAD) + PAD
    sheet = Image.new('RGB', (W, H), (250, 245, 236))
    d = ImageDraw.Draw(sheet)
    f_no = ImageFont.truetype(SANS, 26)
    mapping = {}

    for n, r in enumerate(picks, 1):
        try:
            im = card.warmify(Image.open(r['path']).convert('RGB'))
        except Exception:
            continue
        im = square(im, CELL)
        x = PAD + (n - 1) % COLS * (CELL + PAD)
        y = PAD + (n - 1) // COLS * (CELL + PAD)
        sheet.paste(im, (x, y))
        # 编号：半透明白底压在左上角，深色数字
        tag = str(n)
        tw = d.textlength(tag, font=f_no)
        d.rounded_rectangle([x + 6, y + 6, x + 6 + tw + 16, y + 6 + 36], radius=8,
                            fill=(255, 253, 247))
        d.text((x + 14, y + 8), tag, font=f_no, fill=(58, 42, 26))
        mapping[n] = os.path.relpath(r['path'], card.ROOT)

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, 'candidates.jpg')
    sheet.save(out, 'JPEG', quality=90, optimize=True, progressive=True)
    with open(os.path.join(OUT_DIR, 'candidates.json'), 'w', encoding='utf-8') as f:
        json.dump(mapping, f, ensure_ascii=False, indent=1)
    print(f'{out}  {W}×{H}  {os.path.getsize(out) / 1024:.0f} KB  {len(mapping)} 张')


if __name__ == '__main__':
    main()
