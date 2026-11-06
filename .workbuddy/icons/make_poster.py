#!/usr/bin/env python3
"""生成微信分享海报 assets/img/share-poster.jpg（1080×1440 竖版）。

用途：个人订阅号没有 JS-SDK 分享权限，微信内无法自定义转发卡片。
      改为「图片 + 二维码」的实体卡片：在微信里长按保存，发到家庭群，
      家人长按图片即可识别二维码进入相册。也可以直接当公众号文章封面。

构建期依赖（不进仓库）：
    pip3 install --target /tmp/qrlib pillow segno
    PYTHONPATH=/tmp/qrlib python3 .workbuddy/icons/make_poster.py
"""
import io
import json
import os
import sys

try:
    import segno
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:
    sys.exit('缺少依赖：pip3 install --target /tmp/qrlib pillow segno')

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, '.workbuddy', 'private', 'data.json')
OUT = os.path.join(ROOT, 'assets', 'img', 'share-poster.jpg')

SITE = 'https://xtt.zyall.com/'

W, H = 1080, 1440
SERIF = '/System/Library/Fonts/Supplemental/Songti.ttc'
SANS = '/System/Library/Fonts/Hiragino Sans GB.ttc'

CREAM_TOP = (253, 249, 240)
CREAM_BOT = (232, 212, 184)
INK = (58, 42, 26)
INK_SOFT = (139, 117, 95)
AMBER = (176, 106, 34)
AMBER_DEEP = (150, 86, 22)


def vertical_gradient(size, top, bottom):
    w, h = size
    grad = Image.new('RGB', (1, h))
    px = grad.load()
    for y in range(h):
        t = y / max(1, h - 1)
        px[0, y] = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    return grad.resize((w, h), Image.BILINEAR)


def warm_glow(size):
    w, h = size
    layer = Image.new('L', (w, h), 0)
    d = ImageDraw.Draw(layer)
    cx, cy, r = int(w * 0.18), int(h * 0.03), int(w * 0.80)
    for i in range(26, 0, -1):
        rr = int(r * i / 26)
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=int(54 * (1 - i / 26) ** 1.6))
    layer = layer.filter(ImageFilter.GaussianBlur(80))
    glow = Image.new('RGB', (w, h), (255, 214, 150))
    return glow, layer


def polaroid(photo, w=306, h=382, pad=15, tail=40):
    card = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=13, fill=(255, 253, 247, 255))
    iw, ih = w - pad * 2, h - pad * 2 - tail
    scale = max(iw / photo.width, ih / photo.height)
    pw, ph = int(photo.width * scale + 0.5), int(photo.height * scale + 0.5)
    img = photo.resize((pw, ph), Image.LANCZOS)
    left, top = (pw - iw) // 2, (ph - ih) // 2
    img = img.crop([left, top, left + iw, top + ih]).convert('RGBA')
    mask = Image.new('L', (iw, ih), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, iw - 1, ih - 1], radius=7, fill=255)
    card.paste(img, (pad, pad), mask)
    return card


def pick_photos(n=3):
    """按位置取样，并就近换成竖构图——横图塞进竖版拍立得会被裁得只剩中间一条，
    人物容易看着像"躺倒"，观感不自然。"""
    with open(DATA, encoding='utf-8') as f:
        items = json.load(f)['items']
    pool = [it for it in items if it.get('th') and it.get('t') == 'i']
    if not pool:
        return []

    def is_tall(path):
        try:
            with Image.open(path) as im:
                return im.height >= im.width * 1.02
        except Exception:
            return False

    picks = []
    for f in (0.09, 0.44, 0.79):
        start = min(len(pool) - 1, int(len(pool) * f))
        chosen = None
        for step in range(0, 40):
            for idx in (start + step, start - step):
                if 0 <= idx < len(pool):
                    p = os.path.join(ROOT, pool[idx]['th'])
                    if is_tall(p):
                        chosen = p
                        break
            if chosen:
                break
        picks.append(chosen or os.path.join(ROOT, pool[start]['th']))
    return picks[:n]


def qr_image(text, px=300):
    buf = io.BytesIO()
    segno.make(text, error='h').save(
        buf, kind='png', scale=12, border=2, dark='#3a2a1a', light='#fffdf7')
    buf.seek(0)
    return Image.open(buf).convert('RGBA').resize((px, px), Image.LANCZOS)


def main():
    canvas = vertical_gradient((W, H), CREAM_TOP, CREAM_BOT)
    glow, mask = warm_glow((W, H))
    canvas = Image.composite(glow, canvas, mask).convert('RGBA')
    d = ImageDraw.Draw(canvas)

    f_kick = ImageFont.truetype(SANS, 24)
    f_title = ImageFont.truetype(SERIF, 120, index=1)
    f_sub = ImageFont.truetype(SANS, 33)
    f_line = ImageFont.truetype(SERIF, 40, index=1)
    f_qr = ImageFont.truetype(SANS, 26)
    f_foot = ImageFont.truetype(SANS, 22)

    def center(text, font, y, fill):
        w = d.textlength(text, font=font)
        d.text(((W - w) / 2, y), text, font=font, fill=fill)

    center('仅 限 家 人    ·    P R I V A T E   A L B U M', f_kick, 92, AMBER)
    center('时光小屋', f_title, 146, INK)
    center('家 庭 相 册    ·    2 0 1 7  —  2 0 2 6', f_sub, 300, INK_SOFT)

    # 三张宝丽来，重叠摆位，模仿首页拼贴
    photos = pick_photos(3)
    slots = [(-196, -8), (0, 3), (196, -7)]
    base_y = 424
    for i, (dx, rot) in enumerate(slots):
        if i >= len(photos):
            break
        try:
            ph = Image.open(photos[i]).convert('RGB')
        except Exception:
            continue
        card = polaroid(ph).rotate(rot, resample=Image.BICUBIC, expand=True)
        x = int(W / 2 + dx - card.width / 2)
        y = int(base_y + (382 - card.height) / 2)
        sh = Image.new('L', card.size, 0)
        sh.paste(Image.new('L', card.size, 130), (0, 16),
                 card.split()[3].point(lambda a: int(a * 0.55)))
        sh = sh.filter(ImageFilter.GaussianBlur(18))
        canvas.paste(Image.new('RGBA', card.size, (96, 64, 32, 255)), (x, y), sh)
        canvas.paste(card, (x, y), card)

    center('十年成长影像，只在家人之间', f_line, 900, (74, 56, 38))

    # 二维码卡片
    qs = 236
    qx, qy = (W - qs) // 2, 1006
    d.rounded_rectangle([qx - 16, qy - 16, qx + qs + 16, qy + qs + 16],
                        radius=22, fill=(255, 253, 247, 255))
    canvas.paste(qr_image(SITE, qs), (qx, qy), qr_image(SITE, qs))

    center('长按识别二维码 · 凭密码进入相册', f_qr, qy + qs + 46, INK)
    center('xtt.zyall.com', f_foot, qy + qs + 92, AMBER_DEEP)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    canvas.convert('RGB').save(OUT, 'JPEG', quality=90, optimize=True, progressive=True)
    print(f'{OUT}  {W}×{H}  {os.path.getsize(OUT) / 1024:.1f} KB  照片 {len(photos)} 张')


if __name__ == '__main__':
    main()
