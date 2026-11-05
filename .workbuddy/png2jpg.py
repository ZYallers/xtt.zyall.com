#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
png2jpg.py —— 把 resources2 下超过阈值的无透明通道大 PNG 转成高质量 JPEG
- 只处理 > --min-mb（默认 2MB）且 hasAlpha=no 的 PNG；有透明通道的一律跳过
- 保持原始像素尺寸，质量固定 q92（实测 5.6MB -> 1.4MB，肉眼无明显损失）
- 原件按相对路径镜像克隆备份（cp -c），写入 tsv 回滚日志
- 原 PNG 不删除，改名挪进 trash 目录（本机安全钩子禁止批量删除）

用法:
  python3 png2jpg.py            # 预览
  python3 png2jpg.py --apply    # 执行
"""
import argparse
import os
import shutil
import subprocess
import sys
from datetime import date

ROOT_DEFAULT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resources2"))
BASE = os.path.dirname(os.path.abspath(__file__))
BACKUP_ROOT = os.path.join(BASE, "backup_compress_" + date.today().strftime("%Y%m%d"))
TRASH_DIR = os.path.join(BASE, "png2jpg_trash_" + date.today().strftime("%Y%m%d"))
LOG_PATH = os.path.join(BASE, "png2jpg_log_" + date.today().strftime("%Y%m%d") + ".tsv")
QUALITY = 92


def human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.1f}{u}" if u != "B" else f"{int(n)}B"
        n /= 1024


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


def has_alpha(path):
    r = sips("-g", "hasAlpha", path)
    return "yes" in r.stdout.lower()


def clone_backup(src, dst):
    if os.path.exists(dst):
        return True
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    r = subprocess.run(["cp", "-c", src, dst], capture_output=True)
    if r.returncode == 0 and os.path.exists(dst):
        return True
    try:
        shutil.copy2(src, dst)
        return True
    except OSError:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=ROOT_DEFAULT)
    ap.add_argument("--min-mb", type=float, default=2.0)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    root, threshold = args.root, args.min_mb * 1024 * 1024
    targets, skipped, conflicts = [], [], []
    for dirpath, _, names in os.walk(root):
        for n in sorted(names):
            if not n.lower().endswith(".png"):
                continue
            p = os.path.join(dirpath, n)
            if os.path.getsize(p) <= threshold:
                continue
            if has_alpha(p):
                skipped.append((p, "含透明通道"))
                continue
            dst = os.path.splitext(p)[0] + ".jpeg"
            if os.path.exists(dst):
                conflicts.append((p, dst))
                continue
            targets.append(p)

    total = sum(os.path.getsize(p) for p in targets)
    print(f"扫描 {root}：>{args.min_mb}MB 无透明 PNG {len(targets)} 个，共 {human(total)}")
    for p, why in skipped:
        print(f"  跳过（{why}）: {os.path.relpath(p, root)}")
    for p, dst in conflicts:
        print(f"  冲突（同名 .jpeg 已存在）: {os.path.relpath(p, root)}")
    if not args.apply:
        print("\n（dry-run，未改动任何文件；加 --apply 执行）")
        return 0

    rows, saved = [], 0
    for p in targets:
        rel = os.path.relpath(p, root)
        before = dims(p)
        if not before:
            rows.append((rel, os.path.getsize(p), 0, "读取尺寸失败，跳过"))
            continue
        dst = os.path.splitext(p)[0] + ".jpeg"
        if not clone_backup(p, os.path.join(BACKUP_ROOT, os.path.basename(os.path.normpath(root)), rel)):
            rows.append((rel, os.path.getsize(p), 0, "备份失败，跳过"))
            continue
        r = sips("-s", "format", "jpeg", "-s", "formatOptions", str(QUALITY), p, "--out", dst)
        if r.returncode != 0 or not os.path.exists(dst):
            rows.append((rel, os.path.getsize(p), 0, "编码失败，跳过"))
            continue
        if dims(dst) != before:
            os.makedirs(TRASH_DIR, exist_ok=True)
            os.replace(dst, os.path.join(TRASH_DIR, os.path.basename(dst) + ".bad"))
            rows.append((rel, os.path.getsize(p), 0, "尺寸不符，放弃"))
            continue
        nsize = os.path.getsize(dst)
        old = os.path.getsize(p)
        shutil.copymode(p, dst)
        # 原 PNG 不删除，挪进 trash 目录
        os.makedirs(TRASH_DIR, exist_ok=True)
        os.replace(p, os.path.join(TRASH_DIR, rel.replace("/", "__")))
        saved += old - nsize
        rows.append((rel + " -> " + os.path.basename(dst), old, nsize, f"q{QUALITY}"))

    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write("原路径\t原字节\t新字节\t备注\n")
        for rel, old, new, note in rows:
            f.write(f"{rel}\t{old}\t{new}\t{note}\n")

    print(f"\n完成 {len(rows)} 个，省 {human(saved)}")
    for rel, old, new, note in rows:
        if new:
            print(f"  {rel}  {human(old)} -> {human(new)}  ({old/new:.1f}x)")
        else:
            print(f"  {rel}  {note}")
    print(f"日志: {LOG_PATH}\n备份: {os.path.join(BACKUP_ROOT, os.path.basename(os.path.normpath(root)))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
