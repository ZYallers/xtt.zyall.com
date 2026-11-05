#!/usr/bin/env python3
"""统一重命名 resources/2018 下的媒体文件为 IMG_yyyymmdd_hhmmss / MOV_yyyymmdd_hhmmss"""
import os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "resources", "2018")
LOG = os.path.join(ROOT, ".workbuddy", "rename_log_2018.tsv")
DRY = "--apply" not in sys.argv

VIDEO_EXT = {".mp4", ".mov", ".avi", ".m4v", ".3gp", ".mkv", ".wmv", ".flv"}
PAT = re.compile(r"^([A-Za-z]+)_(\d{8})_?(\d{6})(.*)$")

def target(fn):
    stem, ext = os.path.splitext(fn)
    m = PAT.match(stem)
    if not m:
        return None
    d, t = m.group(2), m.group(3)
    prefix = "MOV" if ext.lower() in VIDEO_EXT else "IMG"
    return prefix, f"{prefix}_{d}_{t}", f"{prefix}_{d}_{t}{ext}", m.group(4)

files = sorted(f for f in os.listdir(DIR) if os.path.isfile(os.path.join(DIR, f)))

groups, skipped = {}, []
for f in files:
    r = target(f)
    if not r:
        skipped.append(f)
        continue
    groups.setdefault(r[2], []).append(f)

plan = []   # (old, new)
for newname, members in groups.items():
    if len(members) == 1:
        plan.append((members[0], newname))
        continue
    # 保留原名最“干净”的一个作为主名，其余追加 _1/_2...
    members.sort(key=lambda n: (n != newname, n))
    plan.append((members[0], newname))
    stem, ext = os.path.splitext(newname)
    for i, n in enumerate(members[1:], 1):
        plan.append((n, f"{stem}_{i}{ext}"))

print(f"文件总数 {len(files)}｜待改名 {sum(1 for o, n in plan if o != n)}｜未识别 {len(skipped)} {skipped}")
for o, n in plan:
    if o != n:
        print(f"  {o}  ->  {n}")

if DRY:
    print("\n[DRY-RUN] 未做任何修改。加 --apply 执行。")
    sys.exit(0)

# 两阶段重命名，避免新旧名互相占用
tmp = []
for o, n in plan:
    if o == n:
        continue
    tmpname = f".__rn__{abs(hash(o))}{os.path.splitext(o)[1]}"
    os.rename(os.path.join(DIR, o), os.path.join(DIR, tmpname))
    tmp.append((tmpname, n, o))

os.makedirs(os.path.dirname(LOG), exist_ok=True)
with open(LOG, "w", encoding="utf-8") as fh:
    fh.write("old\tnew\n")
    for tmpname, n, o in tmp:
        os.rename(os.path.join(DIR, tmpname), os.path.join(DIR, n))
        fh.write(f"{o}\t{n}\n")
print(f"\n✅ 完成 {len(tmp)} 个文件重命名，日志：{LOG}")
