#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
resize_2mb.py —— 把仍超过阈值的图片按「宽 1920、高等比」缩小；缩完仍超阈值再降质量压缩
- 只处理 > --min-mb（默认 2MB）的 jpg/jpeg/png，且原宽度 > 1920（绝不放大）
- 等比缩放：sips --resampleWidth 1920，高度自动按比例
- 缩放后仍 > 阈值：q92 -> 88 -> 84 逐档重编码，取第一个能降到阈值以下的档位；
  都降不下来就保留最小档结果（不为凑体积牺牲到失真）
- 原件镜像克隆备份（cp -c），写入 tsv 日志

用法:
  python3 resize_2mb.py            # 预览
  python3 resize_2mb.py --apply    # 执行
"""
import argparse
import os
import shutil
import subprocess
import sys
import threading
from datetime import date

ROOT_DEFAULT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resources2"))
BASE = os.path.dirname(os.path.abspath(__file__))
BACKUP_ROOT = os.path.join(BASE, "backup_resize_" + date.today().strftime("%Y%m%d"))
TRASH_DIR = os.path.join(BASE, "resize_trash_" + date.today().strftime("%Y%m%d"))
LOG_PATH = os.path.join(BASE, "resize_log_" + date.today().strftime("%Y%m%d") + ".tsv")
TARGET_W = 1920
QUALITIES = [92, 88, 84]
IMG_EXT = {".jpg", ".jpeg", ".png"}
_tls = threading.local()


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


def fmt_of(path):
    return "jpeg" if os.path.splitext(path)[1].lower() in (".jpg", ".jpeg") else "png"


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


def park(tmp, tag):
    try:
        os.makedirs(TRASH_DIR, exist_ok=True)
        os.replace(tmp, os.path.join(TRASH_DIR, f"{tag}.tmp"))
    except OSError:
        pass


def tmp_name(path):
    if not getattr(_tls, "tag", None):
        _tls.tag = f"w{threading.get_ident()}"
    return os.path.join(os.path.dirname(path), "." + os.path.basename(path) + f".{_tls.tag}.tmp")


def process(path, rel, apply_mode, threshold, backup_root):
    old_size = os.path.getsize(path)
    before = dims(path)
    if not before:
        return (rel, old_size, old_size, "", "读尺寸失败，跳过")
    w, h = before
    if w <= TARGET_W:
        return (rel, old_size, old_size, f"{w}x{h}", "宽度已 ≤1920，跳过")

    new_h = round(h * TARGET_W / w)
    if not apply_mode:
        return (rel, old_size, None, f"{w}x{h} -> {TARGET_W}x{new_h}", "dry-run")

    if not clone_backup(path, os.path.join(backup_root, rel)):
        return (rel, old_size, old_size, f"{w}x{h}", "备份失败，跳过")

    fmt = fmt_of(path)
    tmp = tmp_name(path)
    try:
        # 1) 等比缩放到宽 1920
        r = sips("--resampleWidth", str(TARGET_W), "-s", "format", fmt, path, "--out", tmp)
        if r.returncode != 0 or not os.path.exists(tmp):
            park(tmp, os.path.basename(rel))
            return (rel, old_size, old_size, f"{w}x{h}", "缩放失败，跳过")
        d = dims(tmp)
        if not d or d[0] != TARGET_W or abs(d[1] - new_h) > 2:
            park(tmp, os.path.basename(rel))
            return (rel, old_size, old_size, f"{w}x{h}", "缩放尺寸校验失败，跳过")

        size = os.path.getsize(tmp)
        used_q = "-"

        # 2) 仍超阈值则降质量
        if size > threshold and fmt == "jpeg":
            best = None
            for q in QUALITIES:
                tmp2 = tmp + f".q{q}"
                r2 = sips("-s", "format", "jpeg", "-s", "formatOptions", str(q), tmp, "--out", tmp2)
                if r2.returncode != 0 or not os.path.exists(tmp2):
                    park(tmp2, os.path.basename(rel) + f".q{q}")
                    continue
                s2 = os.path.getsize(tmp2)
                if best is None or s2 < best[0]:
                    if best:
                        park(best[2], os.path.basename(rel) + f".q{best[1]}")
                    best = (s2, q, tmp2)
                else:
                    park(tmp2, os.path.basename(rel) + f".q{q}")
                if s2 <= threshold:
                    break
            if best:
                size, used_q, tmp = best[0], best[1], best[2]

        shutil.copymode(path, tmp)
        os.replace(tmp, path)
        note = f"缩到 {d[0]}x{d[1]}" + (f"，q{used_q}" if used_q != "-" else "，未再压")
        return (rel, old_size, size, f"{w}x{h} -> {d[0]}x{d[1]}", note)
    except Exception as e:  # noqa: BLE001
        if os.path.exists(tmp):
            park(tmp, os.path.basename(rel))
        return (rel, old_size, old_size, f"{w}x{h}", f"异常: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=ROOT_DEFAULT)
    ap.add_argument("--min-mb", type=float, default=2.0)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    root, threshold = args.root, args.min_mb * 1024 * 1024
    targets = []
    for dirpath, _, names in os.walk(root):
        for n in names:
            if os.path.splitext(n)[1].lower() not in IMG_EXT:
                continue
            p = os.path.join(dirpath, n)
            if os.path.getsize(p) > threshold:
                targets.append(p)
    targets.sort()
    total = sum(os.path.getsize(p) for p in targets)
    print(f"扫描 {root}：>{args.min_mb}MB 图片 {len(targets)} 个，共 {human(total)}"
          f"；目标宽度 {TARGET_W}px；模式：{'APPLY' if args.apply else 'DRY-RUN'}")

    backup_root = os.path.join(BACKUP_ROOT, os.path.basename(os.path.normpath(root)))
    rows, saved = [], 0
    for p in targets:
        row = process(p, os.path.relpath(p, root), args.apply, threshold, backup_root)
        rows.append(row)
        rel, old, new, dim_note, note = row
        line = f"  {rel}\n    {dim_note}  {human(old)} -> {human(new) if new else '-'}  {note}"
        print(line)
        if new and new < old:
            saved += old - new

    if args.apply:
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write("路径\t尺寸\t原字节\t新字节\t备注\n")
            for rel, old, new, dim_note, note in rows:
                f.write(f"{rel}\t{dim_note}\t{old}\t{new or ''}\t{note}\n")
        print(f"\n完成 {len(rows)} 个，省 {human(saved)}")
        print(f"日志: {LOG_PATH}\n备份: {backup_root}")
    else:
        print("\n（dry-run，未改动任何文件；加 --apply 执行）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
