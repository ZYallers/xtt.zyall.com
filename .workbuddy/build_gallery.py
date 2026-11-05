#!/usr/bin/env python3
"""扫描 resources/ 生成前端相册数据与缩略图

输出：
  .workbuddy/private/data.json    明文清单（站点目录之外，禁止上传）
  gallery/thumbs/<xx>/<md5>.webp  缩略图（长边 480，WebP，自适应质量，单张 ≤20KB）
                                  图片直接缩放编码；视频取 0.1s 处一帧再编码
                                  xx 是文件名的前 2 位，见下方「分片」说明
加密与登录凭据由 .workbuddy/gen_auth.mjs 完成，生成后站点才能读到数据：
  printf '[{"u":"账号","p":"密码"}]' | node .workbuddy/gen_auth.mjs
用法：python3 build_gallery.py [--no-thumbs]
"""
import os, re, sys, json, hashlib, subprocess, shutil, tempfile, threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

_local = threading.local()   # 每线程独立临时目录

SIPS = shutil.which("sips") or "/usr/bin/sips"   # PATH 精简时也能找到
FFMPEG = (shutil.which("ffmpeg")
          or os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin", "ffmpeg"))

# 仓库根目录 = 本文件所在目录（.workbuddy/）的上一级；不用写死绝对路径，clone 到哪都能跑
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "resources")
OUT = os.path.join(ROOT, "gallery")
THUMBS = os.path.join(OUT, "thumbs")
PRIVATE = os.path.join(ROOT, ".workbuddy", "private", "data.json")
IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic"}
VID_EXT = {".mp4", ".mov", ".avi", ".m4v", ".3gp", ".mkv", ".webm"}

# 缩略图：WebP 同等体积下画质远好于 JPEG（q75 约 13KB，观感与 JPEG q68 的 36KB 持平）
# 超过 THUMB_MAX 就从 q75 逐档往下压；实测 96% 的图停在 q75，最狠的也只用到 q44
THUMB_EDGE = 480
THUMB_MAX = 20 * 1024
# 先降质量（480px 保持不变），到底还超标才缩尺寸——实测 97% 停在 q75～q60
THUMB_STEPS = ((480, 75), (480, 68), (480, 60), (480, 52), (480, 44),
               (420, 62), (380, 58), (340, 55), (300, 50))

# 顺序很关键：越具体的模式越靠前
PATTERNS = [
    # 2020-10月/29.jpg 之外的：视频目录 2022-09-07 20.03.41.mp4
    (re.compile(r"(\d{4})-(\d{2})-(\d{2}) (\d{2})\.(\d{2})\.(\d{2})"), "ymdhm s"),
    # WuTa_2019-06-04_19-14-12.jpg
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})[_ ](\d{2})-(\d{2})-(\d{2})"), "ymdhm s"),
    # Screenshot_20200413-233224__01.jpg
    (re.compile(r"Screenshot_(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})"), "ymdhm s"),
    # IMG_20180118_211518  /  MYXJ_20180316124315_fast
    (re.compile(r"(?:IMG|MOV|MYXJ)_(\d{4})(\d{2})(\d{2})_?(\d{2})(\d{2})(\d{2})"), "ymdhm s"),
    # 13 位毫秒时间戳
    (re.compile(r"^(\d{13})"), "ms"),
]


def parse_date(name):
    """返回 (datetime|None, exact_bool)"""
    for pat, kind in PATTERNS:
        m = pat.search(name)
        if not m:
            continue
        g = m.groups()
        if kind == "ms":
            try:
                return datetime.fromtimestamp(int(g[0]) / 1000).replace(microsecond=0), True
            except (ValueError, OSError, OverflowError):
                return None, False
        try:
            return datetime(*[int(x) for x in g]), True
        except ValueError:
            return None, False
    # 年份目录下的 yyyymm-dd（dd 是月内序号，不是日，故只记到月，日置 1）
    m = re.search(r"^(?:IMG|MOV)_(\d{4})(\d{2})-(\d{2,3})", name)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            return datetime(y, mo, 1), False
    return None, False


def kind(ext):
    low = ext.lower()
    if low in IMG_EXT:
        return "IMG", low
    if low in VID_EXT:
        return "MOV", low
    return None, low


def sniff(path):
    """按文件头判断真实类型，返回 'i' / 'v' / None（用于纠正扩展名错误的文件）"""
    try:
        with open(path, "rb") as fh:
            head = fh.read(16)
    except OSError:
        return None
    if head[:3] == b"\xff\xd8\xff" or head[:4] == b"\x89PNG" or head[:4] == b"GIF8":
        return "i"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "i"
    if head[4:8] == b"ftyp":
        return "v"
    return None


def main():
    no_thumbs = "--no-thumbs" in sys.argv
    album_order = []
    items = []
    for album in sorted(os.listdir(RES)):
        p = os.path.join(RES, album)
        if not os.path.isdir(p) or album.startswith("."):
            continue
        album_order.append(album)
        for f in sorted(os.listdir(p)):
            if f == ".DS_Store":
                continue
            fp = os.path.join(p, f)
            if not os.path.isfile(fp):
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext in IMG_EXT:
                typ = "i"
            elif ext in VID_EXT:
                typ = "v"
            else:
                continue
            dt, exact = parse_date(f)
            real = sniff(fp)
            wrong_ext = 0
            if real and real != typ:
                typ, wrong_ext = real, 1
            items.append({
                "p": f"{album}/{f}",
                "a": album,
                "t": typ,
                "y": dt.year if dt else 0,
                "mo": dt.month if dt else 0,
                "d": dt.strftime("%Y-%m-%d %H:%M:%S") if dt else "",
                "x": 1 if exact else 0,
                "w": wrong_ext,
                "n": os.path.splitext(f)[0],
                "s": os.path.getsize(fp),
            })

    # 排序：有时间在前（按时间），无时间在后（按相册、文件名）
    items.sort(key=lambda i: (i["d"] == "", i["d"], i["a"], i["n"]))

    os.makedirs(OUT, exist_ok=True)
    os.makedirs(THUMBS, exist_ok=True)

    albums = []
    for a in album_order:
        sub = [i for i in items if i["a"] == a]
        if not sub:
            continue
        years = sorted({i["y"] for i in sub if i["y"]})
        albums.append({"k": a, "n": len(sub), "y": years,
                       "vid": sum(1 for i in sub if i["t"] == "v")})
    years_all = sorted({i["y"] for i in items if i["y"]})

    # 缩略图路径必须在这里定下来（--no-thumbs 也要有），否则前端会把图片当视频卡
    # 视频同样预生成封面缩略图：列表页只加载缩略图，点开预览才拉 CDN 原视频
    #
    # 分片：文件名是 md5(相对路径)[:16]，取前 2 位当子目录 → 最多 256 个目录。
    # 单目录实测只有十几张（4210 张最挤的也只有 30 出头），远低于「一个目录上千文件」；
    # 而且哈希前缀与资源顺序无关，增删照片只影响自己那一格，已有文件永不搬迁，
    # git 只会记成新增/删除，不会出现整片改名。
    jobs = []
    for it in items:
        key = hashlib.md5(it["p"].encode()).hexdigest()[:16]
        it["th"] = f"gallery/thumbs/{key[:2]}/{key}.webp"
        dst = os.path.join(ROOT, it["th"])
        if not os.path.exists(dst):
            jobs.append((os.path.join(RES, it["p"]), dst, it["t"]))

    # 内容没变就沿用上次的生成时间，让清单逐字节稳定：
    # 否则光是时间戳变化，每次重建都会产出一个全新的 data.enc.js（约 0.9MB），白撑大 git
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(PRIVATE, encoding="utf-8") as fh:
            old = json.load(fh)
        if (old.get("generated") and old.get("albums") == albums
                and old.get("years") == years_all and old.get("items") == items):
            generated = old["generated"]
    except (OSError, ValueError):
        pass

    data = {
        "generated": generated,
        "albums": albums,
        "years": years_all,
        "items": items,
    }

    def write_private():
        os.makedirs(os.path.dirname(PRIVATE), exist_ok=True)
        with open(PRIVATE, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))

    write_private()
    print(f"清单：{len(items)} 项 / {len(albums)} 个相册 -> .workbuddy/private/data.json")
    print("  有日期:", sum(1 for i in items if i["d"]), "｜无日期:", sum(1 for i in items if not i["d"]))

    # 只识别 resources/<相册名>/<文件> 这一层，其余位置会被静默忽略，这里给出提醒
    stray = [f for f in os.listdir(RES)
             if os.path.isfile(os.path.join(RES, f)) and not f.startswith(".")]
    nested = []
    for album in album_order:
        base = os.path.join(RES, album)
        for root, _dirs, files in os.walk(base):
            if root == base:
                continue
            for f in files:
                if not f.startswith("."):
                    nested.append(os.path.relpath(os.path.join(root, f), RES))
    if stray:
        print(f"\n⚠️ resources 根目录有 {len(stray)} 个文件不在相册子目录里，已被忽略：{stray[:5]}")
        print("   请把它们放进 resources/<相册名>/ 下再重建")
    if nested:
        print(f"\n⚠️ 有 {len(nested)} 个文件位于二级及更深目录，已被忽略：{nested[:5]}")
        print("   相册只取 resources 下一层目录，请把文件上移一层")
    # 缩略图路径已在上面算好；这里只提示缺多少张
    if jobs:
        print(f"缩略图：待生成 {len(jobs)} 张")

    if no_thumbs:
        print(f"缩略图：跳过生成（缺 {len(jobs)} 张，这部分会临时回退加载原图）")
        print("\n下一步：node .workbuddy/gen_auth.mjs  # 加密清单（账号未变，无需密码）")
        return

    if jobs and not os.access(FFMPEG, os.X_OK):
        print(f"❌ 找不到 ffmpeg（{FFMPEG}），WebP 缩略图依赖它。")
        print("   macOS 可下载静态版：")
        print("   curl -sL -o /tmp/ffmpeg.gz https://github.com/eugeneware/ffmpeg-static/releases/download/b6.1.1/ffmpeg-darwin-arm64.gz")
        print("   gunzip -f /tmp/ffmpeg.gz && mkdir -p .workbuddy/bin && mv /tmp/ffmpeg .workbuddy/bin/ && chmod +x .workbuddy/bin/ffmpeg")
        return

    def scratch(name):
        """每线程一个临时文件，反复覆盖写；不删除文件（safe-delete 钩子有每轮删除上限）"""
        d = getattr(_local, "dir", None)
        if d is None:
            d = tempfile.mkdtemp(prefix="xtt-thumb-")
            _local.dir = d
        return os.path.join(d, name)

    def encode(src, dst):
        """WebP 缩略图：先按 480+q75 编，超 20KB 逐档降质量，最后才缩尺寸"""
        tmp = f"{dst}.part"          # -f webp 显式指定，否则 ffmpeg 认不出 .part
        for edge, q in THUMB_STEPS:
            vf = (f"scale='min({edge},iw)':'min({edge},ih)'"
                  ":force_original_aspect_ratio=decrease")
            subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
                            "-i", src, "-frames:v", "1", "-vf", vf,
                            "-c:v", "libwebp", "-quality", str(q),
                            "-compression_level", "6", "-f", "webp", tmp],
                           check=True, capture_output=True, timeout=180)
            if os.path.getsize(tmp) <= THUMB_MAX:
                break
        os.replace(tmp, dst)

    def make(job):
        src, dst, typ = job
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)   # 分片子目录按需创建
            if typ == "v":
                # 先抽一帧，再按质量阶梯编码（避免每档都重新 seek 视频）
                frame = scratch("frame.png")
                subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
                                "-ss", "0.1", "-i", src, "-frames:v", "1",
                                "-vf", (f"scale='min({THUMB_EDGE},iw)':'min({THUMB_EDGE},ih)'"
                                        ":force_original_aspect_ratio=decrease"),
                                frame],
                               check=True, capture_output=True, timeout=180)
                encode(frame, dst)
            else:
                try:
                    encode(src, dst)
                except Exception:
                    # 个别刁钻的 PNG/EXIF 组合 ffmpeg 啃不动，先让 sips 转成普通 JPEG 再编
                    frame = scratch("fallback.jpg")
                    subprocess.run([SIPS, "-Z", str(THUMB_EDGE), "-s", "format", "jpeg",
                                    "-s", "formatOptions", "95", src, "--out", frame],
                                   check=True, capture_output=True, timeout=90)
                    encode(frame, dst)
            return True
        except Exception:
            return False

    ok = 0
    n_vid = sum(1 for j in jobs if j[2] == "v")
    with ThreadPoolExecutor(max_workers=8) as ex:
        for i, r in enumerate(ex.map(make, jobs), 1):
            ok += 1 if r else 0
            if i % 200 == 0:
                print(f"  缩略图 {i}/{len(jobs)}")
    print(f"缩略图：新生成 {ok}/{len(jobs)} 张（图片 {len(jobs) - n_vid}、视频 {n_vid}）")

    # 生成失败的（多半是坏视频）去掉缩略图路径，前端会标「格式异常」而不去请求原文件
    bad = 0
    for it in items:
        out = os.path.join(ROOT, it["th"])
        if not os.path.exists(out):
            it["th"] = None
            bad += 1
    if bad:
        print(f"  ⚠️ {bad} 个文件没生成出缩略图（多半是损坏/异常视频），已标记")

    # 缩略图路径写入后需重写清单
    write_private()
    print("data.json 已写入缩略图路径（下一步：node .workbuddy/gen_auth.mjs 加密）")


if __name__ == "__main__":
    main()
