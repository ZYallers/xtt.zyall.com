#!/usr/bin/env python3
"""按年份目录平铺规范化：resources/<年>/<YYYY-M月|YYYY-MM>/* -> 前缀_yyyymm-dd.ext

规则：
- 图片 -> IMG_ 前缀，视频 -> MOV_ 前缀
- yyyymm 取自子目录名（2020-1月 / 2021-01 -> 202001 / 202101），mm 两位补零
- dd 为原文件名里的编号，两位补零（2-1.mp4 -> 01，53.mp4 -> 53）
- 原名无编号的（如中文名视频），编号顺延到该目录最大编号之后
- 全部平铺到年份根目录，完成后删除空的子目录

用法：python3 rename_month_dir.py <年份> [--apply]
"""
import os, re, sys, csv, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".tif", ".tiff"}
VID_EXT = {".mp4", ".mov", ".avi", ".m4v", ".3gp", ".mkv", ".wmv", ".flv", ".mpg", ".mpeg"}
MONTH_DIR = re.compile(r"^(\d{4})-(\d{1,2})月?$")


def seq_of(stem):
    m = re.search(r"(\d+)(?!.*\d)", stem)
    return int(m.group(1)) if m else None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 1
    year = args[0]
    apply_mode = "--apply" in sys.argv
    base = os.path.join(ROOT, "resources", year)
    log = os.path.join(ROOT, ".workbuddy", f"rename_log_{year}.tsv")
    if not os.path.isdir(base):
        print(f"目录不存在：{base}")
        return 1

    dirs = sorted(d for d in os.listdir(base)
                  if os.path.isdir(os.path.join(base, d)) and MONTH_DIR.match(d))
    plan, unknown, dup = [], [], []

    for d in dirs:
        y, mo = MONTH_DIR.match(d).groups()
        ym = f"{y}{int(mo):02d}"
        path = os.path.join(base, d)
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

    root_files = {f for f in os.listdir(base)
                  if os.path.isfile(os.path.join(base, f)) and f != ".DS_Store"}
    clash = [new for _, _, new in plan if new in root_files]

    n_img = sum(1 for _, _, n in plan if n.startswith("IMG_"))
    n_mov = sum(1 for _, _, n in plan if n.startswith("MOV_"))
    print(f"[{year}] 子目录 {len(dirs)}｜文件 {len(plan)}（图片 {n_img} / 视频 {n_mov}）")
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

    os.makedirs(os.path.dirname(log), exist_ok=True)
    with open(log, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["old", "new"])
        for d, f, new in plan:
            shutil.move(os.path.join(base, d, f), os.path.join(base, new))
            w.writerow([f"{d}/{f}", new])
    print(f"\n✅ 已重命名并移动 {len(plan)} 个文件 -> {base}")
    print(f"   回滚日志：{log}")

    removed = 0
    for d in dirs:
        p = os.path.join(base, d)
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
