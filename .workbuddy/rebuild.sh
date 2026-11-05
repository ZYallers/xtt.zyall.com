#!/usr/bin/env bash
# 一键重建相册站点：扫描 resources → 生成缺的缩略图 → 加密清单
#
#   .workbuddy/rebuild.sh              # 日常：只新增/删除了资源
#   .workbuddy/rebuild.sh --no-thumbs  # 跳过缩略图（只更新清单，很快）
#
# 新增或修改账号时用：
#   ACCOUNTS_JSON='[{"u":"账号","p":"密码"},…]' .workbuddy/rebuild.sh
#
# 注意：日常重建复用已有内容密钥，已登录的人不会掉线；
#      只有 ACCOUNTS_JSON 里带了新账号才会重写凭据（密钥仍复用）。
#
# 环境变量：NODE=... / PYTHON=... 可手动指定解释器路径
set -euo pipefail
cd "$(dirname "$0")/.."

# 交互式 shell 的 PATH 与非交互脚本不一定一致（例如 nvm、WorkBuddy 内置运行时），
# 所以这里自己找一遍，而不是假设 PATH 里有。
find_bin() {
  local name="$1"; shift
  local hit
  if hit=$(command -v "$name" 2>/dev/null); then
    printf '%s\n' "$hit"
    return 0
  fi
  local cand
  for cand in "$@"; do
    if [ -x "$cand" ]; then
      printf '%s\n' "$cand"
      return 0
    fi
  done
  return 1
}

PYTHON="${PYTHON:-$(find_bin python3 \
  /opt/homebrew/bin/python3 \
  /usr/local/bin/python3 \
  /usr/bin/python3 \
  "$HOME"/.workbuddy/binaries/python/versions/*/bin/python3 \
  "$HOME"/.pyenv/versions/*/bin/python3 || true)}"
NODE="${NODE:-$(find_bin node \
  /opt/homebrew/bin/node \
  /usr/local/bin/node \
  "$HOME"/.workbuddy/binaries/node/versions/*/bin/node \
  "$HOME"/.nvm/versions/node/*/bin/node \
  "$HOME"/.volta/bin/node || true)}"

if [ -z "$PYTHON" ]; then
  echo "❌ 找不到 python3。请安装（macOS: xcode-select --install）或指定 PYTHON=/path/to/python3"
  exit 1
fi
if [ -z "$NODE" ]; then
  cat <<'MSG'
❌ 找不到 node，加密清单这一步需要 Node.js。

任选一种：
  1) 装一个：      brew install node
  2) 已有但不在 PATH：NODE=/实际路径/node ./.workbuddy/rebuild.sh
  3) 或者在 WorkBuddy 里说一句「重建相册」，由内置运行时执行
MSG
  exit 1
fi

"$PYTHON" .workbuddy/build_gallery.py "$@"
echo

if [[ -n "${ACCOUNTS_JSON:-}" ]]; then
  printf '%s' "$ACCOUNTS_JSON" | "$NODE" .workbuddy/gen_auth.mjs
else
  "$NODE" .workbuddy/gen_auth.mjs < /dev/null
fi

echo
echo "✅ 重建完成。浏览器刷新即可（已登录状态保留）。"
