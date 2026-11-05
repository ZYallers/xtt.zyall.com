#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_prefix.py —— 按文件真实格式修正 resources2 下文件名的前缀
- 图片（jpeg/png/gif/heic/webp）前缀统一为 IMG_
- 视频（mp4/mov/m4v/avi/3gp/mkv）前缀统一为 MOV_
- 真实格式按文件头判断：扩展名与实际内容不一致时，先把扩展名纠正过来，再定前缀
- 默认 dry-run，--apply 才真正改名；改动写入 tsv 回滚日志

用法:
  python3 fix_prefix.py            # 预览
  python3 fix_prefix.py --apply    # 执行
"""
import argparse
import os
import sys

ROOT_DEFAULT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resources2"))
LOG_PATH = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "rename_prefix_resources2.tsv"))

# 真实格式 -> (前缀, 规范扩展名)
FMT_MAP = {
    "jpeg": ("IMG", ".jpeg"),
    "png": ("IMG", ".png"),
    "gif": ("IMG", ".gif"),
    "heic": ("IMG", ".heic"),
    "webp": ("IMG", ".webp"),
    "bmp": ("IMG", ".bmp"),
    "mp4": ("MOV", ".mp4"),
    "mov": ("MOV", ".mov"),
    "m4v": ("MOV", ".m4v"),
    "avi": ("MOV", ".avi"),
    "3gp": ("MOV", ".3gp"),
    "mkv": ("MOV", ".mkv"),
    "webm": ("MOV", ".webm"),
}
IMG_EXT_AS_JPG = {"jpg", "jpeg"}


def sniff(path):
    """按文件头返回真实格式名，无法识别返回 None"""
    try:
        with open(path, "rb") as f:
            head = f.read(32)
    except OSError:
        return None
    if head[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if head[:4] == b"GIF8":
        return "gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head[4:8] == b"ftyp":
        brand = head[8:12].lower()
        if brand in (b"heic", b"heix", b"mif1", b"msf1"):
            return "heic"
        if brand in (b"qt  ",):
            return "mov"
        if brand in (b"m4v ",):
            return "m4v"
        if brand in (b"3gp4", b"3gp5", b"3g2a"):
            return "3gp"
        return "mp4"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "mkv"
    if head[:4] == b"RIFF" and head[8:12] == b"AVI ":
        return "avi"
    if head[:4] == b"BM":
        return "bmp"
    return None


def target_name(path, real_fmt):
    """返回 (新文件名, 说明)"""
    d, base = os.path.split(path)
    stem, ext = os.path.splitext(base)
    ext_l = ext.lower().lstrip(".")
    want_prefix, want_ext = FMT_MAP[real_fmt]

    notes = []
    # 扩展名归一：.jpg/.jpeg 视作同一族，不强行互换，避免无意义改动
    if real_fmt == "jpeg" and ext_l in IMG_EXT_AS_JPG:
        new_ext = ext
    elif ext_l != want_ext.lstrip("."):
        new_ext = want_ext
        notes.append(f"扩展名 .{ext_l} -> {want_ext}")
    else:
        new_ext = ext

    # 前缀替换：第一个 _ 之前的部分
    if "_" in stem:
        cur_prefix, rest = stem.split("_", 1)
        new_stem = f"{want_prefix}_{rest}"
    else:
        cur_prefix, new_stem = stem, f"{want_prefix}_{stem}"
    if cur_prefix != want_prefix:
        notes.append(f"前缀 {cur_prefix} -> {want_prefix}")

    return new_stem + new_ext, "；".join(notes)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=ROOT_DEFAULT)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    root = args.root
    plan, unknown, skip_junk = [], [], []
    for dirpath, dirnames, names in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for n in sorted(names):
            if n in (".DS_Store", "Thumbs.db"):
                skip_junk.append(os.path.join(dirpath, n))
                continue
            p = os.path.join(dirpath, n)
            real = sniff(p)
            if real is None:
                unknown.append(p)
                continue
            newn, note = target_name(p, real)
            if newn != n:
                plan.append((p, os.path.join(dirpath, newn), note, real))

    # 冲突检测：目标名已被占用（且不是自己）
    occupied = {}
    for dirpath, _, names in os.walk(root):
        for n in names:
            occupied.setdefault(os.path.join(dirpath, n), True)
    conflicts = [x for x in plan if x[1] in occupied and x[1] != x[0]]
    # 目标之间互撞
    seen = {}
    dup = []
    for src, dst, note, real in plan:
        if dst in seen:
            dup.append((seen[dst], src, dst))
        seen[dst] = src

    print(f"扫描 {root}")
    print(f"需要改名：{len(plan)} 个")
    for src, dst, note, real in plan:
        print(f"  {os.path.relpath(src, root)}")
        print(f"    -> {os.path.basename(dst)}   [{note}]")
    if unknown:
        print(f"\n无法识别格式（跳过）：{len(unknown)}")
        for p in unknown:
            print("  " + os.path.relpath(p, root))
    if skip_junk:
        print(f"\n系统垃圾文件（忽略，不改名）：{len(skip_junk)}")
    if conflicts:
        print(f"\n⚠️ 目标名已存在（冲突，不会覆盖）：{len(conflicts)}")
        for src, dst, note, real in conflicts:
            print("  " + os.path.relpath(src, root) + " -> " + os.path.basename(dst))
    if dup:
        print(f"\n⚠️ 多个文件改到同名：{len(dup)} 组")
        for a, b, dst in dup:
            print(f"  {a} / {b} -> {os.path.basename(dst)}")

    if not args.apply:
        print("\n（dry-run，未改动任何文件；加 --apply 执行）")
        return 0
    if conflicts or dup:
        print("\n存在冲突，已中止，未改动任何文件。")
        return 1

    done = []
    for src, dst, note, real in plan:
        try:
            os.rename(src, dst)
            done.append((src, dst, note))
        except OSError as e:
            print(f"  失败 {src}: {e}")
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write("原路径\t新路径\t说明\n")
        for src, dst, note in done:
            f.write(f"{os.path.relpath(src, root)}\t{os.path.relpath(dst, root)}\t{note}\n")
    print(f"\n已改名 {len(done)}/{len(plan)} 个；回滚日志：{LOG_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
