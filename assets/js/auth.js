/* ===========================================================
   入场守卫 + 内容解密
   - 没有有效会话时立刻跳转 login.html（页面在渲染前即隐藏，不会闪出内容）
   - 会话里只存「已被密码解开的内容密钥」，不含密码本身
   =========================================================== */
(function () {
  'use strict';

  /* 标记 JS 可用：加载层只在有 JS 时显示（无 JS 时把 noscript 提示露出来） */
  document.documentElement.classList.add('js');

  var SESSION = 'xtt.session.v1';       // 本次会话（关掉浏览器即失效）
  var PERSIST = 'xtt.session.keep.v1';  // 勾选“记住 7 天”

  function b64d(s) {
    var bin = atob(s), u = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
    return u;
  }

  function parse(raw) {
    if (!raw) return null;
    try {
      var s = JSON.parse(raw);
      if (!s || !s.u || !s.k || !s.e) return null;
      if (s.e < Date.now()) return null;
      b64d(s.k);            // 校验 base64 合法性
      return s;
    } catch (e) { return null; }
  }

  function readSession() {
    var s = parse(sessionStorage.getItem(SESSION));
    if (s) return s;
    s = parse(localStorage.getItem(PERSIST));
    if (s) {
      try { sessionStorage.setItem(SESSION, JSON.stringify(s)); } catch (e) { /* 隐私模式 */ }
      return s;
    }
    return null;
  }

  function lock() {
    document.documentElement.classList.add('auth-pending');
    var hash = location.hash ? '&h=' + encodeURIComponent(location.hash.slice(1)) : '';
    location.replace('login.html?from=guard' + hash);
  }

  var s = readSession();
  if (!s) { lock(); return; }

  window.AUTH = { user: s.u, exp: s.e, keyBytes: b64d(s.k) };

  /* 解密相册清单（v2 清单是 gzip 后再加密的，需先解压） */
  window.VAULT = {
    async open() {
      if (!window.GALLERY_ENC) throw new Error('envelope-missing');
      if (!window.AUTH) throw new Error('no-session');
      var key = await crypto.subtle.importKey(
        'raw', window.AUTH.keyBytes, { name: 'AES-GCM' }, false, ['decrypt']);
      var buf = new Uint8Array(await crypto.subtle.decrypt(
        { name: 'AES-GCM', iv: b64d(window.GALLERY_ENC.i) }, key, b64d(window.GALLERY_ENC.d)));
      if (window.GALLERY_ENC.v >= 2) {
        /* 页面 loader 已按能力选了文件：走到这里说明 DecompressionStream 一定存在 */
        var text = await new Response(
          new Blob([buf]).stream().pipeThrough(new DecompressionStream('gzip'))).text();
        return JSON.parse(text);
      }
      return JSON.parse(new TextDecoder().decode(buf));
    },
    clear() {
      try { sessionStorage.removeItem(SESSION); } catch (e) {}
      try { localStorage.removeItem(PERSIST); } catch (e) {}
    }
  };

  document.documentElement.classList.remove('auth-pending');

  document.addEventListener('DOMContentLoaded', function () {
    var bar = document.getElementById('userbar');
    var out = document.getElementById('logoutBtn');
    if (bar) {
      var name = bar.querySelector('.ub-name');
      if (name) name.textContent = s.u;
      bar.hidden = false;
    }
    if (out) {
      out.addEventListener('click', function () {
        window.VAULT.clear();
        location.replace('login.html?bye=1');
      });
    }
  });
})();
