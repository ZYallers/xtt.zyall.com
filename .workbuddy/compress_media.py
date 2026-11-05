#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compress_media.py —— 压缩 resources/ 下超过指定大小的图片
- 只减小文件体积，不改变像素尺寸；质量优先（90 → 85 → 80，取第一个能省 ≥5% 的档位）
- 按文件头识别真实格式：假图片（实为视频等）直接跳过并记录
- 备份按「相对路径」镜像存放（避免重名文件互相覆盖！），APFS 克隆（cp -c，秒级、写时复制）
- 临时文件用「改名」进 trash 目录，全程不调用删除（本机安全钩子会拦截批量删除）
- 默认 dry-run；--apply 才真正压缩；--skip-after 可跳过某时间点后已处理过的文件（断点续跑）

用法:
  python3 compress_media.py                          # dry-run
  python3 compress_media.py --apply                  # 实际压缩
  python3 compress_media.py --apply --skip-after "2026-11-05 00:00:00"   # 续跑
"""
import argparse
import concurrent.futures as cf
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import date

ROOT_DEFAULT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resources"))
BACKUP_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "backup_compress_" + date.today().strftime("%Y%m%d")))
TRASH_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "compress_trash_" + date.today().strftime("%Y%m%d"))
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "compress_log_" + date.today().strftime("%Y%m%d") + ".tsv")
IMG_EXT = {".jpg", ".jpeg", ".png"}
QUALITIES = [90, 85, 80]      # 从高到低，第一个省到 ≥5% 的档位即用
MIN_SAVING = 0.05

_tls = threading.local()


def human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.1f}{u}" if u != "B" else f"{int(n)}B"
        n /= 1024


def sniff(path):
    """返回 (实际格式 'jpeg'|'png'|None, 备注)"""
    try:
        with open(path, "rb") as f:
            head = f.read(16)
    except OSError:
        return None, "读取失败"
    if head[:3] == b"\xff\xd8\xff":
        return "jpeg", ""
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "png", ""
    if head[4:8] == b"ftyp":
        return None, "实为视频(MP4)"
    return None, "非图片格式"


def sips(*args):
    return subprocess.run(["/usr/bin/sips", *args], capture_output=True, text=True)


def dims(path):
    r = sips("-g", "pixelWidth", "-g", "pixelHeight", path)
    if r.returncode != 0:
        return None
    w = h = None
    for line in r.stdout.splitlines():
        if "pixelWidth" in line:
            w = int(line.split(":")[-1])
        elif "pixelHeight" in line:
            h = int(line.split(":")[-1])
    return (w, h) if w and h else None


def encode(src, dst, fmt, q):
    args = ["-s", "format", fmt]
    if fmt == "jpeg":
        args += ["-s", "formatOptions", str(q)]
    r = sips(*args, src, "--out", dst)
    return r.returncode == 0 and os.path.exists(dst)


def clone_backup(src, backup_file):
    """把原件按镜像路径克隆备份；已存在就视为已备份"""
    if os.path.exists(backup_file):
        return True
    os.makedirs(os.path.dirname(backup_file), exist_ok=True)
    r = subprocess.run(["cp", "-c", src, backup_file], capture_output=True)   # APFS clonefile
    if r.returncode == 0 and os.path.exists(backup_file):
        return True
    try:
        shutil.copy2(src, backup_file)
        return True
    except OSError:
        return False


def park(tmp, trash_dir, tag):
    """不删除：把临时文件改名挪进 trash 目录"""
    try:
        os.makedirs(trash_dir, exist_ok=True)
        os.replace(tmp, os.path.join(trash_dir, f"{tag}_{os.getpid()}.tmp"))
    except OSError:
        pass


def process(path, rel, apply_mode, backup_root, trash_dir):
    size = os.path.getsize(path)
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    ext_fmt = "jpeg" if ext in ("jpg", "jpeg") else "png"
    real, note = sniff(path)
    if real is None:
        return (path, size, size, "", note or "跳过")
    if real != ext_fmt:
        note = f"实际为{real}但扩展名是{ext}，按扩展名格式重编码"

    before = dims(path)
    if not before:
        return (path, size, size, "", "无法读取尺寸，跳过")

    if not apply_mode:
        return (path, size, None, "", "dry-run")

    if not clone_backup(path, os.path.join(backup_root, rel)):
        return (path, size, size, "", "备份失败，跳过")

    # 每线程一个临时文件名，靠 sips --out 覆盖，全程不删除
    if not getattr(_tls, "tag", None):
        _tls.tag = f"w{threading.get_ident()}"
    tag = os.path.basename(rel).replace(" ", "_") + "." + _tls.tag
    tmp = os.path.join(os.path.dirname(path), "." + os.path.basename(path) + f".{_tls.tag}.tmp")

    best = None
    try:
        for q in QUALITIES:
            if not encode(path, tmp, ext_fmt, q):
                park(tmp, trash_dir, tag)
                continue
            nsize = os.path.getsize(tmp)
            if dims(tmp) != before:              # 尺寸必须完全一致
                park(tmp, trash_dir, tag)
                continue
            if nsize < size * (1 - MIN_SAVING):
                best = (nsize, q)
                break                            # 高质量档已达标，不再降档
            park(tmp, trash_dir, tag)            # 没达标也挪走，给下一档腾位置
        if not best:
            return (path, size, size, "", "无可观收益，保持原样")
        shutil.copymode(path, tmp)
        os.replace(tmp, path)                    # 原子替换
        return (path, size, best[0], best[1], note)
    except Exception:                            # noqa: BLE001
        if os.path.exists(tmp):
            park(tmp, trash_dir, tag)
        raise
    finally:
        if os.path.exists(tmp):
            park(tmp, trash_dir, tag)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=ROOT_DEFAULT)
    ap.add_argument("--min-mb", type=float, default=2.0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--skip-after", default="",
                    help='跳过修改时间晚于该时间的文件（断点续跑），如 "2026-11-05 00:00:00"')
    args = ap.parse_args()

    root = args.root
    threshold = args.min_mb * 1024 * 1024
    cutoff = time.mktime(time.strptime(args.skip_after, "%Y-%m-%d %H:%M:%S")) if args.skip_after else 0

    targets, already = [], 0
    for dirpath, _, names in os.walk(root):
        for n in names:
            p = os.path.join(dirpath, n)
            if os.path.splitext(n)[1].lower() not in IMG_EXT:
                continue
            try:
                sz, mt = os.path.getsize(p), os.path.getmtime(p)
            except OSError:
                continue
            if sz > threshold:
                if cutoff and mt >= cutoff:
                    already += 1
                else:
                    targets.append(p)
    targets.sort()
    total = sum(os.path.getsize(p) for p in targets)
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"扫描 {root}：>{args.min_mb}MB 图片 {len(targets)} 个，共 {human(total)}；"
          f"跳过本轮已处理 {already} 个；模式：{mode}")

    backup_root = os.path.join(BACKUP_ROOT, os.path.basename(os.path.normpath(root)))
    t0, saved, rows, skipped = time.time(), 0, [], []
    done = 0
    with cf.ThreadPoolExecutor(args.workers) as ex:
        futs = {ex.submit(process, p, os.path.relpath(p, root), args.apply, backup_root, TRASH_DIR): p for p in targets}
        for fut in cf.as_completed(futs):
            try:
                row = fut.result()
            except Exception as e:                       # noqa: BLE001
                row = (futs[fut], 0, 0, "", f"异常: {e}")
            rows.append(row)
            _, old, new, q, note = row
            done += 1
            if new is not None and new < old:
                saved += old - new
            else:
                skipped.append(note)
            if done % 50 == 0 or done == len(targets):
                print(f"  进度 {done}/{len(targets)}，已省 {human(saved)}，用时 {time.time()-t0:.0f}s")

    rows.sort()
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write("路径\t原字节\t新字节\t质量\t备注\n")
        for path, old, new, q, note in rows:
            f.write(f"{path}\t{old}\t{'' if new is None else new}\t{q}\t{note}\n")

    print(f"\n完成：{len(rows)} 个，省 {human(saved)}"
          f"{'（dry-run 估算，未改动任何文件）' if not args.apply else ''}")
    if skipped:
        cnt = {}
        for s in skipped:
            cnt[s] = cnt.get(s, 0) + 1
        for s, c in cnt.items():
            print(f"  跳过 {c} 个 — {s}")
    print(f"日志: {LOG_PATH}")
    print(f"备份: {backup_root}（相对路径镜像；cp -c 克隆，可用它恢复任一原文件）")


if __name__ == "__main__":
    sys.exit(main())
