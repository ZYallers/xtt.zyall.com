# xtt.zyall.com

时光小屋 · 成长相册

## 相册站点

- `index.html` 相册首页 · `login.html` 登录页
- `assets/` 样式与脚本（`auth.js` 入场守卫 / `login.js` 登录 / `app.js` 浏览逻辑）
- `gallery/data.enc.js` 加密后的清单 · `gallery/thumbs/` 缩略图
- `resources/` 原始图片与视频

## 新增 / 删除资源后怎么重建

把文件放进 `resources/<分组名>/` 里（**只识别这一层**：每个子目录就是首页上的一个分组），然后：

```bash
./.workbuddy/rebuild.sh
```

一条命令搞定：扫描资源 → 补生成缺的缩略图 → 重新加密清单。
**日常重建复用已有密钥，已登录的人刷新页面就能看到新内容，不会被踢下线。**

其它用法：

```bash
# 只改了文件名或删了文件，跳过缩略图（更快）
./.workbuddy/rebuild.sh --no-thumbs

# 新增/修改账号（密钥仍复用，其他人不受影响）
ACCOUNTS_JSON='[{"u":"账号","p":"密码"},{"u":"账号2","p":"密码2"}]' ./.workbuddy/rebuild.sh

# 轮换密钥：所有人强制重新登录（必须给出全部账号）
printf '[{"u":"账号","p":"密码"}]' | node .workbuddy/gen_auth.mjs --new-key
```

注意事项：

- 脚本会自己去找 `python3` 和 `node`（PATH、Homebrew、nvm、WorkBuddy 内置运行时都找一遍），不需要手动配 PATH；确实找不到时会提示怎么处理，也可以用 `NODE=/path/to/node ./.workbuddy/rebuild.sh` 指定。
- 文件必须放在 `resources/<相册名>/` 下。直接丢在 `resources/` 根目录、或再套一层子目录，都会被忽略（脚本会打印警告提示）。
- 缩略图按「路径的 md5」命名，文件改名等于新文件，会重新生成一张；旧缩略图不会被自动删除。
- 想手工分两步也行：`python3 .workbuddy/build_gallery.py`（只写 `.workbuddy/private/data.json`）→ `node .workbuddy/gen_auth.mjs`（加密成 `gallery/data.enc.js`）。

## 安全说明

- 账号密码不以明文保存：`assets/js/accounts.js` 只有 PBKDF2-SHA256（31 万次）派生密钥包裹的内容密钥。
- 清单用 AES-256-GCM 加密，没有密码拿不到文件列表。
- 明文清单在 `.workbuddy/private/data.json`，内容密钥在 `.workbuddy/private/content.key`（权限 600），**两者都不要上传到站点或公开仓库**（`.workbuddy/` 已被全局 `.gitignore` 忽略）。
- 静态托管的 `resources/` 与 `gallery/thumbs/` 若被知道确切文件名仍可直接访问；需要更强隔离请放到带鉴权的服务器后面。
