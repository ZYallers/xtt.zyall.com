#!/usr/bin/env python3
"""resources/2020 规范化：YYYY-M月/* -> IMG|MOV_yyyymm-dd.ext，全部平铺到 2020 根目录

规则：
- 图片 -> IMG_ 前缀，视频 -> MOV_ 前缀
- yyyymm 取自子目录名（2020-1月 -> 202001），mm 两位补零
- dd 为原文件名里的编号，两位补零（2-1.mp4 -> 01，53.mp4 -> 53）
- 原名无编号的（如中文名视频），编号顺延到该目录最大编号之后
- 完成后删除空的子目录
用法：python3 rename_2020.py [--apply]
"""
import os, re, sys, csv, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "resources", "2020")
LOG = os.path.join(ROOT, ".workbuddy", "rename_log_2020.tsv")
IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".tif", ".tiff"}
VID_EXT = {".mp4", ".mov", ".avi", ".m4v", ".3gp", ".mkv", ".wmv", ".flv", ".mpg", ".mpeg"}
MONTH_DIR = re.compile(r"^(\d{4})-(\d{1,2})月$")


def seq_of(stem):
    """取文件名中最后一个数字串作为编号：2-1 -> 1；01 -> 1；中文名 -> None"""
    m = re.search(r"(\d+)(?!.*\d)", stem)
    return int(m.group(1)) if m else None


def main():
    apply_mode = "--apply" in sys.argv
    dirs = sorted(d for d in os.listdir(BASE)
                  if os.path.isdir(os.path.join(BASE, d)) and MONTH_DIR.match(d))
    plan, unknown, dup = [], [], []

    for d in dirs:
        y, mo = MONTH_DIR.match(d).groups()
        ym = f"{y}{int(mo):02d}"
        path = os.path.join(BASE, d)
        entries = sorted(f for f in os.listdir(path) if f != ".DS_Store")
        maxn = max((seq_of(os.path.splitext(f)[0]) or 0) for f in entries) if entries else 0
        seen = {}
        for f in entries:
            stem, ext = os.path.splitext(f)
            low = ext.lower()
            if low in IMG_EXT:
                prefix, ext = "IMG", low
            elif low in VID_EXT:
                prefix, ext = "MOV", low
            else:
                unknown.append(f"{d}/{f}")
                continue
            n = seq_of(stem)
            if n is None:
                maxn += 1
                n = maxn
            new = f"{prefix}_{ym}-{n:02d}{ext}"
            if new in seen:
                dup.append((f"{d}/{f}", f"{d}/{seen[new]}", new))
            seen.setdefault(new, f)
            plan.append((d, f, new))

    root_files = {f for f in os.listdir(BASE)
                  if os.path.isfile(os.path.join(BASE, f)) and f != ".DS_Store"}
    clash = [new for _, _, new in plan if new in root_files]

    n_img = sum(1 for _, _, n in plan if n.startswith("IMG_"))
    n_mov = sum(1 for _, _, n in plan if n.startswith("MOV_"))
    print(f"子目录 {len(dirs)}｜文件 {len(plan)}（图片 {n_img} / 视频 {n_mov}）")
    print(f"未识别类型 {len(unknown)}{unknown}｜同目录编号冲突 {len(dup)}｜根目录重名 {len(clash)}")
    for a, b, n in dup:
        print("  冲突:", a, "<->", b, "=>", n)
    for d, f, n in plan[:10]:
        print(f"  {d}/{f}  ->  {n}")
    if len(plan) > 10:
        print(f"  ...（共 {len(plan)} 条）")

    if not apply_mode:
        print("\n[DRY-RUN] 未修改。加 --apply 执行。")
        return 0
    if unknown or dup or clash:
        print("\n❌ 存在未识别/冲突项，已中止。")
        return 1

    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["old", "new"])
        for d, f, new in plan:
            src = os.path.join(BASE, d, f)
            dst = os.path.join(BASE, new)
            shutil.move(src, dst)
            w.writerow([f"{d}/{f}", new])
    print(f"\n✅ 已重命名并移动 {len(plan)} 个文件 -> {BASE}")
    print(f"   回滚日志：{LOG}")

    removed = 0
    for d in dirs:
        p = os.path.join(BASE, d)
        junk = os.path.join(p, ".DS_Store")
        if os.path.exists(junk):
            os.remove(junk)
        try:
            os.rmdir(p)
            removed += 1
        except OSError as e:
            print(f"   ⚠️ 子目录未删除 {d}：{e}")
    print(f"✅ 已删除空子目录 {removed}/{len(dirs)} 个")
    return 0


if __name__ == "__main__":
    sys.exit(main())
