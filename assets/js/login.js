/* ===========================================================
   登录页逻辑
   密码不进代码：accounts.js 里只有 salt + 被 PBKDF2 派生密钥包裹的内容密钥。
   登录 = 用密码派生密钥 → 解包内容密钥 → 会话中只留内容密钥。
   =========================================================== */
(function () {
  'use strict';

  var SESSION = 'xtt.session.v1';
  var PERSIST = 'xtt.session.keep.v1';
  var FAILKEY = 'xtt.fail.v1';
  var A = window.ACCOUNTS;

  var form = document.getElementById('loginForm');
  var userEl = document.getElementById('user');
  var passEl = document.getElementById('pass');
  var rememberEl = document.getElementById('remember');
  var errBox = document.getElementById('loginErr');
  var btn = document.getElementById('submitBtn');
  var btnText = btn.querySelector('.btn-text');
  var card = document.querySelector('.login-card');

  var b64d = function (s) {
    var bin = atob(s), u = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
    return u;
  };
  var b64e = function (buf) {
    var b = new Uint8Array(buf), s = '';
    for (var i = 0; i < b.length; i++) s += String.fromCharCode(b[i]);
    return btoa(s);
  };

  function say(msg) {
    errBox.textContent = msg;
    errBox.classList.add('show');
    card.classList.remove('shake');
    void card.offsetWidth;
    card.classList.add('shake');
  }
  function hush() {
    errBox.classList.remove('show');
    errBox.textContent = '';
  }

  /* 失败节流：连续 5 次失败后冷却 60 秒（仅本地，防手误连点与简单爆破） */
  function fails() {
    try { return JSON.parse(localStorage.getItem(FAILKEY)) || { n: 0, t: 0 }; }
    catch (e) { return { n: 0, t: 0 }; }
  }
  function bumpFail() {
    var f = fails();
    f.n = (Date.now() - f.t < 10 * 60 * 1000) ? f.n + 1 : 1;
    f.t = Date.now();
    try { localStorage.setItem(FAILKEY, JSON.stringify(f)); } catch (e) {}
    return f;
  }
  function resetFail() {
    try { localStorage.removeItem(FAILKEY); } catch (e) {}
  }
  function cooling() {
    var f = fails();
    if (f.n >= 5 && Date.now() - f.t < 60 * 1000) {
      return Math.ceil((60 * 1000 - (Date.now() - f.t)) / 1000);
    }
    return 0;
  }

  /* 「记住 7 天」默认勾选；主动取消要二次确认，点头之后才真的取消。
     取消勾选只是改变下次的记住策略，不影响本次已建立的会话。 */
  var confirmEl = document.getElementById('rememberConfirm');
  if (rememberEl && confirmEl) {
    var keepBtn = document.getElementById('confirmKeep');
    var dropBtn = document.getElementById('confirmDrop');
    var lastFocus = null;

    function closeConfirm() {
      confirmEl.hidden = true;
      if (lastFocus && lastFocus.focus) lastFocus.focus();
      lastFocus = null;
    }
    function keepChecked() {
      rememberEl.checked = true;
      closeConfirm();
    }

    rememberEl.addEventListener('change', function () {
      if (rememberEl.checked) return;      // 勾选方向不拦
      rememberEl.checked = true;           // 先还原，等家人确认再真正取消
      lastFocus = document.activeElement;
      confirmEl.hidden = false;
      keepBtn.focus();
    });

    keepBtn.addEventListener('click', keepChecked);
    dropBtn.addEventListener('click', function () {
      rememberEl.checked = false;          // 程序赋值不触发 change，不会递归
      closeConfirm();
    });

    // 点遮罩 = 保持勾选，避免误触后把记住关掉
    confirmEl.addEventListener('click', function (ev) {
      if (ev.target.closest('.confirm-card')) return;
      keepChecked();
    });

    document.addEventListener('keydown', function (ev) {
      if (confirmEl.hidden) return;
      if (ev.key === 'Escape') { ev.preventDefault(); keepChecked(); return; }
      if (ev.key === 'Tab') {             // 焦点圈在弹窗里，别跑到背后的表单
        ev.preventDefault();
        (document.activeElement === keepBtn ? dropBtn : keepBtn).focus();
      }
    });
  }

  /* 回车提交 + 显示/隐藏密码 */
  var eye = document.getElementById('eye');
  if (eye) {
    eye.addEventListener('click', function () {
      var on = passEl.type === 'password';
      passEl.type = on ? 'text' : 'password';
      eye.classList.toggle('on', on);
      passEl.focus();
    });
  }

  async function derive(password, salt, iter) {
    var base = await crypto.subtle.importKey(
      'raw', new TextEncoder().encode(password), 'PBKDF2', false, ['deriveKey']);
    return crypto.subtle.deriveKey(
      { name: 'PBKDF2', salt: salt, iterations: iter, hash: 'SHA-256' },
      base, { name: 'AES-GCM', length: 256 }, false, ['decrypt']);
  }

  async function unwrap(acc, password) {
    var kek = await derive(password, b64d(acc.s), A.it);
    var raw = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: b64d(acc.i) }, kek, b64d(acc.k));
    return raw; // 32 字节内容密钥
  }

  function target() {
    var p = new URLSearchParams(location.search);
    var h = p.get('h');
    return 'index.html' + (h ? '#' + h : '');
  }

  /* 已登录则直接进站：先看本次会话，再看「记住 7 天」。
     只看 sessionStorage 会让勾了记住的用户在新标签页 / 重开浏览器访问 login.html
     时仍卡在登录页——而 auth.js 的入场守卫是两者都查的，两边规则必须一致。 */
  function valid(s) {
    return !!(s && s.u && s.k && s.e > Date.now());
  }

  (function already() {
    var s = null;
    try { s = JSON.parse(sessionStorage.getItem(SESSION) || 'null'); } catch (e) { s = null; }
    if (!valid(s)) {
      s = null;
      try { s = JSON.parse(localStorage.getItem(PERSIST) || 'null'); } catch (e) { s = null; }
      if (valid(s)) {
        // 记住态补写回本次会话，后续页面读到的是同一份
        try { sessionStorage.setItem(SESSION, JSON.stringify(s)); } catch (e) {}
      } else {
        s = null;
      }
    }
    if (s) location.replace(target());
  })();

  form.addEventListener('submit', async function (ev) {
    ev.preventDefault();
    hush();

    var wait = cooling();
    if (wait) { say('尝试次数过多，请 ' + wait + ' 秒后再试'); return; }

    var u = userEl.value.trim();
    var p = passEl.value;
    if (!u || !p) { say('请填写账号和密码'); return; }
    if (!window.crypto || !crypto.subtle) {
      say('当前环境不支持加密校验，请用 Chrome / Edge / Safari 打开，或改用 http 方式访问');
      return;
    }

    var acc = (A.users || []).filter(function (x) { return x.u === u; })[0];
    btn.disabled = true;
    card.classList.add('busy');
    btnText.textContent = '正在解锁…';

    try {
      var raw;
      if (!acc) {
        // 账号不存在也走一遍派生，避免被时间差识别出账号是否存在
        await derive(p, new Uint8Array(16), A.it).catch(function () {});
        throw new Error('bad');
      }
      raw = await unwrap(acc, p);

      var days = rememberEl && rememberEl.checked ? 7 : 0;
      var rec = { u: acc.u, k: b64e(raw), e: Date.now() + (days ? days * 864e5 : 12 * 36e5) };
      resetFail();
      try {
        sessionStorage.setItem(SESSION, JSON.stringify(rec));
        if (days) { localStorage.setItem(PERSIST, JSON.stringify(rec)); }
        else { localStorage.removeItem(PERSIST); }
      } catch (e) { /* 隐私模式：仍可继续，只是关页需重登 */ }

      btnText.textContent = '进入中…';
      card.classList.add('unlocked');
      setTimeout(function () { location.replace(target()); }, 420);
    } catch (e) {
      var f = bumpFail();
      btn.disabled = false;
      card.classList.remove('busy');
      btnText.textContent = '解 锁';
      say(f.n >= 5 ? '账号或密码不正确（已尝试 ' + f.n + ' 次，将短暂锁定）' : '账号或密码不正确');
      passEl.select();
    }
  });

  if (userEl.value) passEl.focus(); else userEl.focus();

  if (/[?&]bye=1/.test(location.search)) {
    var tip = document.getElementById('byeTip');
    if (tip) tip.hidden = false;
  }
})();
