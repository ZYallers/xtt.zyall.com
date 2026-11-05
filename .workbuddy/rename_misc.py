#!/usr/bin/env python3
"""resources/杂七杂八 整理：
文件名是毫秒时间戳（13 位，可能带 "+<hash>" 尾巴）
-> 前缀_yyyymmdd_hhmmss.ext（图片 IMG_ / 视频 MOV_），按 2019 规则
-> 按时间戳年份移动到 resources/<年份>/ 下
时间戳重复（含与目标年份目录已有文件撞名）时，秒 +2 顺延，仍冲突继续 +2。

用法：python3 rename_misc.py [--apply]
"""
import os, re, sys, csv, shutil, collections
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "resources", "杂七杂八")
LOG = os.path.join(ROOT, ".workbuddy", "rename_log_misc.tsv")
IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".tif", ".tiff"}
VID_EXT = {".mp4", ".mov", ".avi", ".m4v", ".3gp", ".mkv", ".wmv", ".flv", ".mpg", ".mpeg"}
P_MS = re.compile(r"^(\d{13})")
P_TS = re.compile(r"^(?:IMG|MOV)_(\d{8})_(\d{6})\.[A-Za-z0-9]+$")


def main():
    apply_mode = "--apply" in sys.argv
    files = sorted(f for f in os.listdir(SRC) if f != ".DS_Store")
    records, unknown = [], []
    for f in files:
        stem, ext = os.path.splitext(f)
        low = ext.lower()
        prefix = "IMG" if low in IMG_EXT else ("MOV" if low in VID_EXT else None)
        m = P_MS.match(stem)
        if not prefix or not m:
            unknown.append(f)
            continue
        ms = int(m.group(1))
        try:
            dt = datetime.fromtimestamp(ms / 1000).replace(microsecond=0)  # 命名只到秒
        except (OverflowError, OSError, ValueError):
            unknown.append(f)
            continue
        if not (2000 <= dt.year <= 2100):
            unknown.append(f)
            continue
        records.append({"old": f, "dt": dt, "prefix": prefix, "ext": low})

    # 目标年份目录已有时间戳（避免覆盖）
    reserved = collections.defaultdict(set)
    for d in os.listdir(os.path.join(ROOT, "resources")):
        p = os.path.join(ROOT, "resources", d)
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
            bumped.append((r["old"], r["dt"], cand, y))
        used[y].add(cand)
        new = f"{r['prefix']}_{cand.strftime('%Y%m%d_%H%M%S')}{r['ext']}"
        plan.append((r["old"], y, new))

    per_year = collections.Counter(y for _, y, _ in plan)
    print(f"文件 {len(files)}｜可处理 {len(plan)}｜未识别 {len(unknown)} {unknown[:5]}")
    print(f"按年份：{dict(sorted(per_year.items()))}")
    print(f"需顺延（秒+2）：{len(bumped)}")
    for o, a, b, y in bumped[:10]:
        print(f"  {o}  {a:%Y-%m-%d %H:%M:%S} -> {b:%Y-%m-%d %H:%M:%S} ({y})")
    for o, y, n in plan[:8]:
        print(f"  {o}  ->  {y}/{n}")
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
        for o, y, n in plan:
            dst_dir = os.path.join(ROOT, "resources", y)
            os.makedirs(dst_dir, exist_ok=True)
            dst = os.path.join(dst_dir, n)
            if os.path.exists(dst):
                print(f"❌ 目标已存在，跳过：{dst}")
                return 1
            shutil.move(os.path.join(SRC, o), dst)
            w.writerow([o, f"{y}/{n}"])
    print(f"\n✅ 已处理 {len(plan)} 个文件，日志：{LOG}")
    left = [f for f in os.listdir(SRC) if f != ".DS_Store"]
    print(f"源目录剩余文件：{len(left)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
