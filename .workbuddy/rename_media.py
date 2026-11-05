#!/usr/bin/env python3
"""媒体文件命名统一：图片 IMG_yyyymmdd_hhmmss，视频 MOV_yyyymmdd_hhmmss

时间戳完全重复时：第一个保留原时间戳，后续每个在上一个基础上 +2 秒；
若 +2 秒后仍与已有时间戳冲突，则继续 +2 秒，直到唯一（自动处理进位）。

用法:
    python3 rename_media.py 2019          # dry-run
    python3 rename_media.py 2019 --apply  # 执行
"""
import os, re, sys, csv
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGDIR = os.path.join(ROOT, ".workbuddy")
VIDEO_EXT = {".mp4", ".mov", ".avi", ".m4v", ".3gp", ".mkv", ".wmv", ".flv", ".mpg", ".mpeg"}

P_COMPACT = re.compile(r"^([A-Za-z]+)_(\d{4})(\d{2})(\d{2})_?(\d{2})(\d{2})(\d{2})(.*)$")
P_DASHED = re.compile(r"^([A-Za-z]+)_(\d{4})-(\d{2})-(\d{2})[_-](\d{2})-(\d{2})-(\d{2})(.*)$")
# Screenshot_20200413-233224__01
P_SCREENSHOT = re.compile(r"^([A-Za-z]+)_(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})(.*)$")


def parse(stem):
    for pat in (P_DASHED, P_SCREENSHOT, P_COMPACT):
        m = pat.match(stem)
        if not m:
            continue
        g = m.groups()
        try:
            dt = datetime(int(g[1]), int(g[2]), int(g[3]), int(g[4]), int(g[5]), int(g[6]))
        except ValueError:
            return None
        return dt, m.group(8)
    return None


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    name = sys.argv[1].rstrip("/")
    apply_mode = "--apply" in sys.argv
    d = os.path.join(ROOT, "resources", name)
    files = sorted(f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f)))

    records, bad = [], []
    for f in files:
        stem, ext = os.path.splitext(f)
        r = parse(stem)
        if not r:
            bad.append(f)
            continue
        dt, tail = r
        prefix = "MOV" if ext.lower() in VIDEO_EXT else "IMG"
        records.append({"old": f, "dt": dt, "tail": tail, "ext": ext.lower(), "prefix": prefix})

    # 所有原始时间戳均需保留，任何 +2s 结果不得占用它们
    reserved = {r["dt"] for r in records}

    groups = {}
    for r in records:
        groups.setdefault((r["prefix"], r["dt"]), []).append(r)

    plan, bumped = [], []
    used = set()
    for (prefix, dt) in sorted(groups, key=lambda k: (k[1], k[0])):
        # 主名优先给“最干净”的文件（原名恰好就是标准名），其次按文件名排序
        members = sorted(groups[(prefix, dt)], key=lambda r: (
            r["old"] != f"{prefix}_{dt.strftime('%Y%m%d_%H%M%S')}{r['ext']}", r["old"]))
        cur = dt
        first = True
        for r in members:
            if first:
                cur = dt
                first = False
            else:
                cur = cur + timedelta(seconds=2)
                while cur in reserved or cur in used:
                    cur = cur + timedelta(seconds=2)
                bumped.append((r["old"], cur))
            newname = f"{prefix}_{cur.strftime('%Y%m%d_%H%M%S')}{r['ext']}"
            used.add(cur)
            plan.append((r["old"], newname))

    changed = [(o, n) for o, n in plan if o != n]
    print(f"[{name}] 文件 {len(files)}｜待改名 {len(changed)}｜未识别 {len(bad)} {bad}")
    for o, n in changed:
        print(f"  {o}  ->  {n}")
    if bumped:
        print(f"\n时间戳冲突 {len(bumped)} 个，已 +2s 顺延：")
        for o, dt in bumped:
            print(f"  {o}  =>  {dt.strftime('%Y-%m-%d %H:%M:%S')}")

    if not apply_mode:
        print("\n[DRY-RUN] 未修改。加 --apply 执行。")
        return 0

    log = os.path.join(LOGDIR, f"rename_log_{name}.tsv")
    os.makedirs(LOGDIR, exist_ok=True)
    tmp = []
    for o, n in changed:
        t = f".__rn__{abs(hash(o))}{os.path.splitext(o)[1]}"
        os.rename(os.path.join(d, o), os.path.join(d, t))
        tmp.append((t, n, o))
    with open(log, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["old", "new"])
        for t, n, o in tmp:
            os.rename(os.path.join(d, t), os.path.join(d, n))
            w.writerow([o, n])
    print(f"\n✅ 完成 {len(tmp)} 个重命名，日志：{log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
