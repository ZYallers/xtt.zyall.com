#!/usr/bin/env python3
"""混合规则规范化（2022 及以后）：

1) 文件名是纯编号（01.mp4 / 2-1.mp4）且位于 YYYY-M月/YYYY-MM 子目录
   -> 前缀_yyyymm-dd   （yyyymm 取目录名，dd 取原文件名编号，不足两位补零）
2) 文件名不是纯编号（IMG_20221022_190400.jpg / MYXJ_20221126120816209_fast.jpg / WuTa_2022-01-05_10-20-30.jpg）
   -> 前缀_yyyymmdd_hhmmss ；时间戳重复时第二个起秒 +2，仍冲突继续 +2（自动进位）
3) 全部平铺到年份根目录，删除残留的空子目录

用法：python3 rename_hybrid.py <年份> [--apply]
"""
import os, re, sys, csv, shutil
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".tif", ".tiff"}
VID_EXT = {".mp4", ".mov", ".avi", ".m4v", ".3gp", ".mkv", ".wmv", ".flv", ".mpg", ".mpeg"}
MONTH_DIR = re.compile(r"^(\d{4})-(\d{1,2})月?$")
P_COMPACT = re.compile(r"^[A-Za-z]+_(\d{4})(\d{2})(\d{2})_?(\d{2})(\d{2})(\d{2})")
P_DASHED = re.compile(r"^[A-Za-z]+_(\d{4})-(\d{2})-(\d{2})[_-](\d{2})-(\d{2})-(\d{2})")


def seq_of(stem):
    m = re.search(r"(\d+)(?!.*\d)", stem)
    return int(m.group(1)) if m else None


def ts_of(stem):
    for pat in (P_DASHED, P_COMPACT):
        m = pat.match(stem)
        if not m:
            continue
        try:
            return datetime(*(int(x) for x in m.groups()))
        except ValueError:
            return None
    return None


def kind(ext):
    low = ext.lower()
    if low in IMG_EXT:
        return "IMG", low
    if low in VID_EXT:
        return "MOV", low
    return None, low


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

    month_dirs = sorted(d for d in os.listdir(base)
                        if os.path.isdir(os.path.join(base, d)) and MONTH_DIR.match(d))

    # 收集：rel, prefix, ext, 目录月份(可在根目录为 None), stem
    items, unknown = [], []
    for d in [None] + month_dirs:
        folder = base if d is None else os.path.join(base, d)
        ym = None
        if d:
            y, mo = MONTH_DIR.match(d).groups()
            ym = f"{y}{int(mo):02d}"
        for f in sorted(x for x in os.listdir(folder) if x != ".DS_Store"):
            if not os.path.isfile(os.path.join(folder, f)):
                continue
            stem, ext = os.path.splitext(f)
            prefix, lext = kind(ext)
            if not prefix:
                unknown.append(f"{d + '/' if d else ''}{f}")
                continue
            items.append({"rel": f"{d}/{f}" if d else f, "prefix": prefix, "ext": lext,
                          "ym": ym, "stem": stem, "dir": d})

    # 时间戳类：统一排重（+2s 顺延）
    ts_items = [it for it in items if not (it["ym"] and it["stem"].isdigit())]
    reserved = {ts_of(it["stem"]) for it in ts_items if ts_of(it["stem"])}
    used, plan, bumped = set(), [], []
    for it in ts_items:
        ts = ts_of(it["stem"])
        if ts is None:
            unknown.append(it["rel"] + "（无可用时间戳）")
            continue
        cand = ts
        while cand in used:
            cand += timedelta(seconds=2)
            while cand in reserved:
                cand += timedelta(seconds=2)
        if cand != ts:
            bumped.append((it["rel"], ts, cand))
        used.add(cand)
        plan.append((it["rel"], f"{it['prefix']}_{cand.strftime('%Y%m%d_%H%M%S')}{it['ext']}"))

    # 月份类：dd = 原编号
    for d in month_dirs:
        y, mo = MONTH_DIR.match(d).groups()
        ym = f"{y}{int(mo):02d}"
        group = [it for it in items if it["ym"] == ym and it["stem"].isdigit()]
        if not group:
            continue
        maxn = max(int(it["stem"]) for it in group)
        seen = {}
        for it in group:
            n = int(it["stem"])
            new = f"{it['prefix']}_{ym}-{n:02d}{it['ext']}"
            if new in seen:
                unknown.append(f"编号冲突 {it['rel']} <-> {seen[new]} => {new}")
            seen[new] = it["rel"]
            plan.append((it["rel"], new))

    # 全量目标名去重校验
    finals = [n for _, n in plan]
    if len(set(finals)) != len(finals):
        dup = sorted({n for n in finals if finals.count(n) > 1})
        unknown.append(f"目标名重复：{dup}")

    todo = [(s, n) for s, n in plan if os.path.basename(s) != n]
    n_img = sum(1 for _, n in plan if n.startswith("IMG_"))
    n_mov = sum(1 for _, n in plan if n.startswith("MOV_"))
    print(f"[{year}] 子目录 {len(month_dirs)}｜文件 {len(plan)}（图片 {n_img} / 视频 {n_mov}）｜需改名 {len(todo)}")
    print(f"未识别/冲突 {len(unknown)}")
    for u in unknown[:10]:
        print("  ⚠️", u)
    for s, n in todo[:10]:
        print(f"  {s}  ->  {n}")
    if len(todo) > 10:
        print(f"  ...（共 {len(todo)} 条）")
    for s, a, b in bumped:
        print(f"  时间戳顺延: {s}  {a:%H:%M:%S} -> {b:%H:%M:%S}")

    if not apply_mode:
        print("\n[DRY-RUN] 未修改。加 --apply 执行。")
        return 0
    if unknown:
        print("\n❌ 存在未识别/冲突项，已中止。")
        return 1

    os.makedirs(os.path.dirname(log), exist_ok=True)
    with open(log, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["old", "new"])
        for s, n in plan:
            if os.path.basename(s) == n and "/" not in s:
                continue
            shutil.move(os.path.join(base, s), os.path.join(base, n))
            w.writerow([s, n])
    print(f"\n✅ 完成 {len(todo)} 个文件重命名/移动 -> {base}")
    print(f"   回滚日志：{log}")

    removed = 0
    for d in month_dirs:
        p = os.path.join(base, d)
        junk = os.path.join(p, ".DS_Store")
        if os.path.exists(junk):
            os.remove(junk)
        try:
            os.rmdir(p)
            removed += 1
        except OSError as e:
            print(f"   ⚠️ 子目录未删除 {d}：{e}")
    print(f"✅ 已删除空子目录 {removed}/{len(month_dirs)} 个")
    return 0


if __name__ == "__main__":
    sys.exit(main())
