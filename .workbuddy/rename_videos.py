#!/usr/bin/env python3
"""视频目录整理：文件名形如 "yyyy-mm-dd hh.mm.ss.mp4"
-> 前缀_yyyymmdd_hhmmss.ext（视频 MOV_ / 图片 IMG_），按 2019 目录方案
-> 按文件名中的年份移动到 resources/<年份>/
重复（含与目标年份目录已有文件同名）时，秒 +2 顺延，仍冲突继续 +2。

用法：python3 rename_videos.py 视频2018 视频2019 视频2022 [--apply]
"""
import os, re, sys, csv, shutil, collections
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "resources")
LOG = os.path.join(ROOT, ".workbuddy", "rename_log_videos.tsv")
IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".tif", ".tiff"}
VID_EXT = {".mp4", ".mov", ".avi", ".m4v", ".3gp", ".mkv", ".wmv", ".flv", ".mpg", ".mpeg"}
P_SRC = re.compile(r"^(\d{4})-(\d{2})-(\d{2}) (\d{2})\.(\d{2})\.(\d{2})")
P_TS = re.compile(r"^(?:IMG|MOV)_(\d{8})_(\d{6})\.[A-Za-z0-9]+$")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 1
    apply_mode = "--apply" in sys.argv
    dirs = [os.path.join(RES, d) for d in args]
    for d in dirs:
        if not os.path.isdir(d):
            print(f"目录不存在：{d}")
            return 1

    records, unknown = [], []
    for d in dirs:
        for f in sorted(x for x in os.listdir(d) if x != ".DS_Store"):
            stem, ext = os.path.splitext(f)
            low = ext.lower()
            prefix = "IMG" if low in IMG_EXT else ("MOV" if low in VID_EXT else None)
            m = P_SRC.match(stem)
            if not prefix or not m:
                unknown.append(f"{os.path.basename(d)}/{f}")
                continue
            try:
                dt = datetime(*(int(x) for x in m.groups()))
            except ValueError:
                unknown.append(f"{os.path.basename(d)}/{f}（非法时间）")
                continue
            records.append({"dir": os.path.basename(d), "old": f, "dt": dt,
                            "prefix": prefix, "ext": low})

    # 目标年份目录已有时间戳
    reserved = collections.defaultdict(set)
    for d in os.listdir(RES):
        p = os.path.join(RES, d)
        if not (d.isdigit() and len(d) == 4 and os.path.isdir(p)):
            continue
        for f in os.listdir(p):
            m = P_TS.match(f)
            if m:
                reserved[d].add(datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S"))

    records.sort(key=lambda r: (r["dt"], r["old"]))
    used, plan, bumped = collections.defaultdict(set), [], []
    for r in records:
        y = f"{r['dt'].year}"
        cand = r["dt"]
        while cand in used[y] or cand in reserved[y]:
            cand += timedelta(seconds=2)
        if cand != r["dt"]:
            bumped.append((r["dir"] + "/" + r["old"], r["dt"], cand))
        used[y].add(cand)
        plan.append((r["dir"], r["old"], y, f"{r['prefix']}_{cand.strftime('%Y%m%d_%H%M%S')}{r['ext']}"))

    per_year = collections.Counter(y for _, _, y, _ in plan)
    total_src = sum(len([f for f in os.listdir(os.path.join(RES, d)) if f != ".DS_Store"]) for d in args)
    print(f"文件 {total_src}｜可处理 {len(plan)}｜未识别 {len(unknown)}")
    for u in unknown[:10]:
        print("  ⚠️", u)
    print(f"按年份：{dict(sorted(per_year.items()))}｜需顺延(秒+2)：{len(bumped)}")
    for o, a, b in bumped[:8]:
        print(f"  {o}  {a:%H:%M:%S} -> {b:%H:%M:%S}")
    for d, o, y, n in plan[:8]:
        print(f"  {d}/{o}  ->  {y}/{n}")
    print(f"  ...（共 {len(plan)} 条）")

    if not apply_mode:
        print("\n[DRY-RUN] 未修改。加 --apply 执行。")
        return 0
    if unknown:
        print("\n❌ 有未识别文件，已中止。")
        return 1

    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["old", "new"])
        for d, o, y, n in plan:
            dst_dir = os.path.join(RES, y)
            os.makedirs(dst_dir, exist_ok=True)
            dst = os.path.join(dst_dir, n)
            if os.path.exists(dst):
                print(f"❌ 目标已存在，跳过：{dst}")
                return 1
            shutil.move(os.path.join(RES, d, o), dst)
            w.writerow([f"{d}/{o}", f"{y}/{n}"])
    print(f"\n✅ 已处理 {len(plan)} 个文件，日志：{LOG}")
    for d in args:
        left = [f for f in os.listdir(os.path.join(RES, d)) if f != ".DS_Store"]
        print(f"   {d} 剩余文件：{len(left)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
