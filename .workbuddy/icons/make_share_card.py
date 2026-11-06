#!/usr/bin/env python3
"""生成微信转发卡片的缩略图 assets/img/share-card.jpg（640×640）。

微信在「转发给朋友」时读取 og:image（或页面首图）作为卡片缩略图，
尺寸需要 ≥300×300，正方形观感最好。这里用站点里的真实照片拼一张
和首页同款暖色调的卡片，不依赖任何在线服务。

构建期依赖（不进仓库）：
    pip3 install --target /tmp/qrlib pillow
    PYTHONPATH=/tmp/qrlib python3 .workbuddy/icons/make_share_card.py
"""
import json
import os
import sys

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:
    sys.exit('缺少 Pillow：PYTHONPATH=/tmp/qrlib python3 .workbuddy/icons/make_share_card.py')

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, '.workbuddy', 'private', 'data.json')
OUT = os.path.join(ROOT, 'assets', 'img', 'share-card.jpg')

S = 640
SERIF = '/System/Library/Fonts/Supplemental/Songti.ttc'
SANS = '/System/Library/Fonts/Hiragino Sans GB.ttc'   # 本机无 PingFang.ttc，用冬青黑体代替

CREAM_TOP = (253, 248, 238)
CREAM_BOT = (237, 219, 192)
INK = (58, 42, 26)
INK_SOFT = (141, 119, 97)
AMBER = (176, 106, 34)


def vertical_gradient(size, top, bottom):
    w, h = size
    grad = Image.new('RGB', (1, h))
    px = grad.load()
    for y in range(h):
        t = y / max(1, h - 1)
        px[0, y] = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    return grad.resize((w, h), Image.BILINEAR)


def warm_glow(size):
    """左上角一团暖光，和站点首页同方向"""
    w, h = size
    layer = Image.new('L', (w, h), 0)
    d = ImageDraw.Draw(layer)
    cx, cy, r = int(w * 0.16), int(h * 0.04), int(w * 0.78)
    for i in range(26, 0, -1):
        rr = int(r * i / 26)
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=int(58 * (1 - i / 26) ** 1.6))
    layer = layer.filter(ImageFilter.GaussianBlur(60))
    glow = Image.new('RGB', (w, h), (255, 214, 150))
    return glow, layer


def polaroid(photo, w=196, h=242, pad=11, tail=24):
    """白框 + 照片（等比裁切）+ 底部留白"""
    card = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=9, fill=(255, 253, 247, 255))

    iw, ih = w - pad * 2, h - pad * 2 - tail
    scale = max(iw / photo.width, ih / photo.height)
    pw, ph = int(photo.width * scale + 0.5), int(photo.height * scale + 0.5)
    img = photo.resize((pw, ph), Image.LANCZOS)
    left = (pw - iw) // 2
    top = (ph - ih) // 2
    img = img.crop([left, top, left + iw, top + ih]).convert('RGBA')

    mask = Image.new('L', (iw, ih), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, iw - 1, ih - 1], radius=5, fill=255)
    card.paste(img, (pad, pad), mask)
    return card


def pick_photos(n=3):
    with open(DATA, encoding='utf-8') as f:
        items = json.load(f)['items']
    pool = [it for it in items if it.get('th') and it.get('t') == 'i']
    if not pool:
        return []
    picks = []
    for f in (0.08, 0.42, 0.78):
        it = pool[min(len(pool) - 1, int(len(pool) * f))]
        picks.append(os.path.join(ROOT, it['th']))
    return picks[:n]


def main():
    canvas = vertical_gradient((S, S), CREAM_TOP, CREAM_BOT)
    glow, mask = warm_glow((S, S))
    canvas = Image.composite(glow, canvas, mask).convert('RGBA')

    d = ImageDraw.Draw(canvas)
    f_kick = ImageFont.truetype(SANS, 17)
    f_title = ImageFont.truetype(SERIF, 74, index=1)
    f_sub = ImageFont.truetype(SANS, 21)
    f_foot = ImageFont.truetype(SANS, 17)

    def center(text, font, y, fill):
        w = d.textlength(text, font=font)
        d.text(((S - w) / 2, y), text, font=font, fill=fill)

    center('仅 限 家 人  ·  PRIVATE ALBUM', f_kick, 58, AMBER)
    center('时光小屋', f_title, 96, INK)
    center('2017 — 2026 · 家庭影像', f_sub, 190, INK_SOFT)

    photos = pick_photos(3)
    slots = [(-118, -7), (0, 2), (118, -6)]
    base_y = 250
    for i, (dx, rot) in enumerate(slots):
        if i >= len(photos):
            break
        try:
            ph = Image.open(photos[i]).convert('RGB')
        except Exception:
            continue
        card = polaroid(ph).rotate(rot, resample=Image.BICUBIC, expand=True)
        x = int(S / 2 + dx - card.width / 2)
        y = int(base_y + (242 - card.height) / 2)
        shadow = Image.new('L', card.size, 0)
        shadow.paste(Image.new('L', card.size, 120), (0, 10),
                     card.split()[3].point(lambda a: int(a * 0.55)))
        shadow = shadow.filter(ImageFilter.GaussianBlur(12))
        canvas.paste(Image.new('RGBA', card.size, (96, 64, 32, 255)), (x, y), shadow)
        canvas.paste(card, (x, y), card)

    center('十年成长影像，只在家人之间', ImageFont.truetype(SERIF, 27, index=1), 528, (74, 56, 38))
    center('xtt.zyall.com · 微信里转发给家人', f_foot, 574, INK_SOFT)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    canvas.convert('RGB').save(OUT, 'JPEG', quality=88, optimize=True, progressive=True)
    print(f'{OUT}  {S}×{S}  {os.path.getsize(OUT) / 1024:.1f} KB  照片 {len(photos)} 张')


if __name__ == '__main__':
    main()
