#!/usr/bin/env python3
"""生成「发到家庭群」的海报 assets/img/share-poster.jpg（1080×1580）。

上半部分 = share-card 的同一套版式（同一份 render，1050 → 1080 宽重绘），
下半部分接二维码 + 一句操作提示。

用途：微信聊天框里粘贴网址只会是纯链接（2021 外链新规没放开「传播」），
      所以把海报发进群，家人长按识别二维码进站，再点右上角「···」转发
      出去才是带标题带图的卡片。

构建期依赖（不进仓库）：
    pip3 install --target /tmp/qrlib pillow numpy segno opencv-python-headless
    PYTHONPATH=/tmp/qrlib python3 .workbuddy/icons/make_poster.py
"""
import io
import os
import sys

try:
    import segno
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit('缺少依赖：pip3 install --target /tmp/qrlib pillow segno')

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_share_card as card                             # noqa: E402  同目录，复用卡片版式

ROOT = card.ROOT
OUT = os.path.join(ROOT, 'assets', 'img', 'share-poster.jpg')
SITE = 'https://xtt.zyall.com/'

W = 1080
TOP_H = W                      # 上方卡片区是正方形，与 share-card 版式同源
GAP = 66                       # 卡片区到二维码卡片的间距
QR = 260                       # 二维码边长（微信长按识别实测 200 以上就稳）
QBOX = 18                      # 二维码白底卡片的内边距
TIP = 34                       # 提示文案字号
TIP_GAP = 34                   # 二维码卡片下沿到文案的间距
BOTTOM = 72                    # 文案到画布底边的留白

H = TOP_H + GAP + QR + QBOX * 2 + TIP_GAP + int(TIP * 1.5) + BOTTOM

SERIF = card.SERIF
SANS = card.SANS
INK = card.INK
INK_DEEP = (74, 56, 38)

TIP_TEXT = '长按图片 → 识别图中二维码 → 转发给朋友'


def qr_image(text, px):
    """按整数模块渲染，避免 resize 把模块边缘糊掉（糊了长按识别会变慢）"""
    q = segno.make(text, error='h')
    modules = q.symbol_size(scale=1, border=2)[0]
    scale = max(1, px // modules)
    buf = io.BytesIO()
    q.save(buf, kind='png', scale=scale, border=2,
           dark='#3a2a1a', light='#fffdf7')
    buf.seek(0)
    return Image.open(buf).convert('RGBA')


def main():
    # 渐变按整幅海报的高度铺，卡片区只取顶部 1080——接缝处底色天然连续
    canvas = card.vertical_gradient((W, H), card.CREAM_TOP, card.CREAM_BOT)
    glow, mask = card.warm_glow((W, H))
    canvas = Image.composite(glow, canvas, mask).convert('RGB')

    top, photos = card.render(W, hires=True, bg_height=H)   # 1080×1080，用原图重绘
    canvas.paste(top.convert('RGB'), (0, 0))

    d = ImageDraw.Draw(canvas)

    qx = (W - QR) // 2
    qy = TOP_H + GAP
    d.rounded_rectangle([qx - QBOX, qy - QBOX, qx + QR + QBOX, qy + QR + QBOX],
                        radius=26, fill=(255, 253, 247))
    qr = qr_image(SITE, QR)
    canvas.paste(qr, (qx + (QR - qr.width) // 2, qy + (QR - qr.height) // 2), qr)

    f_tip = ImageFont.truetype(SANS, TIP)
    tw = d.textlength(TIP_TEXT, font=f_tip)
    d.text(((W - tw) / 2, qy + QR + QBOX + TIP_GAP), TIP_TEXT, font=f_tip, fill=INK_DEEP)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    # q80：SSIM 0.9988（对比 q92），二维码仍能稳定解码；体积 143KB → 96KB
    canvas.save(OUT, 'JPEG', quality=80, optimize=True, progressive=True)
    print(f'{OUT}  {W}×{H}  {os.path.getsize(OUT) / 1024:.1f} KB  照片 {len(photos)} 张')
    for p in photos:
        print('  ', os.path.relpath(p, ROOT))


if __name__ == '__main__':
    main()
