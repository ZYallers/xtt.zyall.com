#!/usr/bin/env bash
# 生成站点图标：favicon.svg / favicon.ico / apple-touch-icon.png（写入仓库根目录）
# 依赖：Chrome（用 --screenshot 渲染 SVG，透明背景）与 python3（打包 ICO）
# 说明：icon16.svg 是 16px 专用的简化版（细线在小尺寸会糊），32/48/64 用 icon.svg
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
[ -x "$CHROME" ] || { echo "找不到 Chrome：$CHROME" >&2; exit 1; }

OUT="$(mktemp -d)"
shoot() {  # $1=svg 路径 $2=边长 $3=输出文件
  "$CHROME" --headless --no-sandbox --disable-gpu --hide-scrollbars \
    --default-background-color=00000000 --window-size="$2,$2" \
    --screenshot="$OUT/$3" "file://$1" >/dev/null 2>&1
}

shoot "$HERE/icon16.svg"    16  s16.png
shoot "$HERE/icon.svg"      32  s32.png
shoot "$HERE/icon.svg"      48  s48.png
shoot "$HERE/icon.svg"      64  s64.png
shoot "$HERE/icon-touch.svg" 180 touch.png

cp "$HERE/icon.svg" "$ROOT/favicon.svg"
cp "$OUT/touch.png" "$ROOT/apple-touch-icon.png"
python3 "$HERE/build_ico.py" "$ROOT/favicon.ico" \
  "$OUT/s16.png" "$OUT/s32.png" "$OUT/s48.png" "$OUT/s64.png"

ls -l "$ROOT/favicon.svg" "$ROOT/favicon.ico" "$ROOT/apple-touch-icon.png"
