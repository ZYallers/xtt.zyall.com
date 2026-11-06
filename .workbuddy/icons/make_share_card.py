#!/usr/bin/env python3
"""生成微信转发卡片的缩略图 assets/img/share-card.jpg（640×640）。

微信在「转发给朋友」时读取 og:image（或页面首图）作为卡片缩略图，
尺寸需要 ≥300×300，正方形观感最好。这里用站点里的真实照片拼一张
和首页同款暖色调的卡片，不依赖任何在线服务。

选片规则（2026-11-06）：
- 卡片里不出现任何数字/年份——文案会随年份和素材数量过时
- 照片必须与奶油色背景同调：按「暖度 + 亮度 + 饱和度 + 人脸面积」打分挑片，
  挑完再统一做一次暖调偏移，避免冷色照片（室内白光、蓝色校服）跳出来

构建期依赖（不进仓库）：
    pip3 install --target /tmp/qrlib pillow numpy opencv-python-headless
    PYTHONPATH=/tmp/qrlib python3 .workbuddy/icons/make_share_card.py

人脸检测模型 models/face_detection_yunet_2023mar.onnx（232KB，随脚本入库）：
opencv 5 已经删掉 haarcascade（cv2/data 是空目录，CascadeClassifier 也没了），
只剩 YuNet，所以模型必须自带，否则人脸检测会静默返回 0、选片门槛形同虚设。
来源：https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet
"""
import json
import os
import sys

try:
    from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
except ImportError:
    sys.exit('缺少 Pillow：PYTHONPATH=/tmp/qrlib python3 .workbuddy/icons/make_share_card.py')

try:
    import numpy as np
except ImportError:
    sys.exit('缺少 numpy：PYTHONPATH=/tmp/qrlib python3 .workbuddy/icons/make_share_card.py')

try:
    import cv2
    # opencv 5 已经不含 haarcascade（cv2/data 是空的），CascadeClassifier 也移除了，
    # 只剩 YuNet——模型文件 232KB，随脚本一起入库，保证换机器能复现
    _MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          'models', 'face_detection_yunet_2023mar.onnx')
    _DET = cv2.FaceDetectorYN_create(_MODEL, '', (320, 320), 0.7, 0.3, 5000) \
        if os.path.exists(_MODEL) else None
except Exception:                                     # 没有 opencv 就退化为无脸评分
    cv2 = None
    _DET = None

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, '.workbuddy', 'private', 'data.json')
OUT = os.path.join(ROOT, 'assets', 'img', 'share-card.jpg')

S = 640
SERIF = '/System/Library/Fonts/Supplemental/Songti.ttc'
SANS = '/System/Library/Fonts/Hiragino Sans GB.ttc'   # 本机无 PingFang.ttc，用冬青黑体代替

CREAM_TOP = (253, 248, 238)
CREAM_BOT = (237, 219, 192)
CREAM_AVG = tuple(round((a + b) / 2) for a, b in zip(CREAM_TOP, CREAM_BOT))
INK = (58, 42, 26)
INK_SOFT = (141, 119, 97)
AMBER = (176, 106, 34)

SAMPLE = 140          # 从全量里抽样评估的张数（全量 2000+，逐张跑人脸太慢）

# 定稿选片：2026-11-06 用户从 48 张候选表里手挑的 46 / 47 / 48，
# 同一套国风写真，米白底 + 圆形构图，和奶油色卡片底色几乎同源。
# 自动打分能判「有没有人、颜色搭不搭」，判不了「好不好看」，所以定稿写死。
DEFAULT_PHOTOS = [
    'gallery/thumbs/d3/d36ced41d17b13da.webp',   # 46 竹椅上
    'gallery/thumbs/b6/b6550124ee58c5fa.webp',   # 47 提竹篮
    'gallery/thumbs/1e/1edf8e46ce964bc1.webp',   # 48 持折扇
]


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


def face_ratio(img):
    """最大人脸占画面的比例（YuNet，人脸比 Haar 稳得多）"""
    if _DET is None:
        return 0.0
    rgb = img.convert('RGB')
    w, h = rgb.size
    try:
        _DET.setInputSize((w, h))
        _, faces = _DET.detect(cv2.cvtColor(np.asarray(rgb), cv2.COLOR_RGB2BGR))
    except Exception:
        return 0.0
    if faces is None or len(faces) == 0:
        return 0.0
    return max(float(f[2] * f[3]) for f in faces) / float(w * h)


def photo_score(img):
    """分数越高越适合放进暖色卡片；第二个返回值是「画面里有没有脸」"""
    small = img.convert('RGB').copy()
    small.thumbnail((320, 320), Image.LANCZOS)
    arr = np.asarray(small, dtype=np.float32)

    warm = float(arr[..., 0].mean() - arr[..., 2].mean())     # 红蓝差，正值偏暖
    bright = float(arr.mean())
    mx = arr.max(axis=2)
    mn = arr.min(axis=2)
    sat = float(((mx - mn) / np.maximum(mx, 1.0)).mean() * 100)

    score = 0.0
    score += 30 * max(0.0, min(1.0, (warm - 4) / 22))          # 冷光照片基本选不上
    # 边缘色温：拍立得里画面边缘多半是环境（垫子、墙、桌布），偏蓝就整张都在跟奶油底打架
    hh, ww = arr.shape[:2]
    band = max(4, int(min(hh, ww) * 0.10))
    edge = np.concatenate([arr[:band].reshape(-1, 3), arr[-band:].reshape(-1, 3),
                           arr[:, :band].reshape(-1, 3), arr[:, -band:].reshape(-1, 3)])
    ewarm = float(edge[:, 0].mean() - edge[:, 2].mean())
    score += 22 * max(0.0, min(1.0, (ewarm + 2) / 24))
    # 边缘太花（彩色爬行垫、花色墙纸）会把奶油底衬得很乱，扣分让干净背景优先
    emx, emn = edge.max(axis=1), edge.min(axis=1)
    esat = float(((emx - emn) / np.maximum(emx, 1.0)).mean() * 100)
    score += 10 * max(0.0, 1 - esat / 42)
    score += 20 * max(0.0, 1 - abs(bright - 145) / 95)         # 避开过暗/过曝
    score += 10 * max(0.0, 1 - abs(sat - 34) / 34)             # 太灰、太花都扣分
    r = face_ratio(small)
    if r > 0:
        # 中景（孩子半身）最好看：脸太小看不出人，脸太大成了家长大头照
        score += 26 + 16 * max(0.0, 1 - abs(r - 0.09) / 0.16)
    return score, r > 0


def warmify(img):
    """统一暖调：中和色偏 → 推向暖 → 叠一层暖褐调，把三张照片拉进同一色系"""
    arr = np.asarray(img.convert('RGB'), dtype=np.float32)
    # 灰世界白平衡：室内白炽灯/蓝色桌布会把整张照片压冷，先中和掉。
    # 画面里大色块会骗到算法，所以增益限幅，不做彻底校正。
    means = arr.reshape(-1, 3).mean(axis=0)
    gain = np.clip(means.mean() / np.maximum(means, 1.0), 0.84, 1.20)
    arr *= gain
    arr[..., 0] *= 1.035
    arr[..., 2] *= 0.955
    out = Image.fromarray(np.clip(arr, 0, 255).astype('uint8'))
    out = ImageEnhance.Contrast(out).enhance(1.02)
    # 暖光：乘法直接压蓝通道，比加法混合更不容易削掉高光，蓝椅子/彩色垫子会真正退到背景里
    out = ImageChops.multiply(out, Image.new('RGB', out.size, (255, 234, 204)))
    out = ImageEnhance.Brightness(out).enhance(1.11)
    # 再混一点暖褐，把年代不同的照片拉到同一色系
    sepia = ImageOps.colorize(out.convert('L'),
                              black=(46, 32, 18), mid=(198, 164, 126), white=(255, 248, 236))
    out = Image.blend(out, sepia, 0.22)
    tint = Image.new('RGB', out.size, CREAM_AVG)
    return Image.blend(out, tint, 0.05)


def pick_photos(n=3, rank=0):
    """按时间三等分，每段挑一张最暖、最像「孩子照片」的，保证跨年份但不写明。
    rank=1/2 取该段的次优、第三优，用来出多个候选版本。"""
    with open(DATA, encoding='utf-8') as f:
        items = json.load(f)['items']
    pool = [it for it in items if it.get('th') and it.get('t') == 'i']
    if not pool:
        return []

    step = max(1, len(pool) // SAMPLE)
    cand = [(i * step, it) for i, it in enumerate(pool[::step][:SAMPLE])]

    scored = []
    for idx, it in cand:
        path = os.path.join(ROOT, it['th'])
        try:
            with Image.open(path) as im:
                score, has_face = photo_score(im)
        except Exception:
            continue
        scored.append({'i': idx, 'score': score, 'face': has_face, 'path': path})

    # 硬门槛：卡片是给家里人看孩子的，没检测到人脸的（风景、建筑、玩具特写）不要
    facial = [x for x in scored if x['face']]
    base = facial if len(facial) >= n else scored

    picks, used = [], set()
    total = max(x['i'] for x in base) or 1
    for k in range(n):
        lo, hi = total * k / n, total * (k + 1) / n
        seg = [x for x in base if lo <= x['i'] < hi and x['path'] not in used]
        seg = seg or [x for x in base if x['path'] not in used]
        if not seg:
            break
        best = sorted(seg, key=lambda x: -x['score'])[min(rank, len(seg) - 1)]
        picks.append(best['path'])
        used.add(best['path'])
    return picks[:n]


def main(out=OUT, rank=0, manual=None):
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

    # 文字全部取自这句：把散落在年月里孩子长大的瞬间收起来，沿着时光看看那个小小滴娃
    # 上中下三行互不重复，也不出现「仅限家人」和网址
    center('散 落 在 年 月 里', f_kick, 58, AMBER)
    center('时光小屋', f_title, 96, INK)
    center('孩子长大的瞬间', f_sub, 195, INK_SOFT)

    if manual:
        photos = [p if os.path.isabs(p) else os.path.join(ROOT, p) for p in manual]
    elif rank == 0:
        # 正式图用定稿三张；rank>0 才回去跑自动选片，方便再出候选
        photos = [os.path.join(ROOT, p) for p in DEFAULT_PHOTOS]
    else:
        photos = pick_photos(3, rank)
    slots = [(-118, -7), (0, 2), (118, -6)]
    base_y = 250
    for i, (dx, rot) in enumerate(slots):
        if i >= len(photos):
            break
        try:
            with Image.open(photos[i]) as im:
                ph = warmify(im.convert('RGB'))
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

    center('沿着时光，看看那个小小滴娃', ImageFont.truetype(SERIF, 28, index=1), 532, (74, 56, 38))

    os.makedirs(os.path.dirname(out), exist_ok=True)
    canvas.convert('RGB').save(out, 'JPEG', quality=88, optimize=True, progressive=True)
    print(f'{out}  {S}×{S}  {os.path.getsize(out) / 1024:.1f} KB  照片 {len(photos)} 张')
    for p in photos:
        print('  ', os.path.relpath(p, ROOT))


if __name__ == '__main__':
    # 用法：python3 make_share_card.py [输出路径] [rank] [图1,图2,图3]
    # rank=0 最优选片（默认产出正式图），1/2 取次优；给了第三参数就直接用指定照片
    _out = sys.argv[1] if len(sys.argv) > 1 else OUT
    _rank = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    _manual = sys.argv[3].split(',') if len(sys.argv) > 3 and sys.argv[3] else None
    main(_out, _rank, _manual)
