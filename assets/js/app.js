/* ===========================================================
   时光小屋 · 成长相册
   纯前端：时间线 + 分组筛选 + 分页 + 灯箱
   =========================================================== */
(async function () {
  'use strict';

  /* 相册清单在磁盘上是加密的：密钥只能由登录密码解开 */
  let DATA;
  try {
    DATA = await window.VAULT.open();
  } catch (err) {
    try { window.VAULT && window.VAULT.clear(); } catch (e) {}
    location.replace('login.html?e=1');
    return;
  }
  const ITEMS = DATA.items.map((it, i) => ({ ...it, id: i }));
  const PER_PAGE = 30;
  const UNDATED = 'none';
  /* 原图/视频托管在七牛云 Kodo（CDN 加速域名），缩略图仍走本站；
     中文目录名等需按段编码，否则 CDN 404 */
  const RES_BASE = 'https://oss.zyall.com/';
  const resURL = (p) => RES_BASE + p.split('/').map(encodeURIComponent).join('/');
  /* 仅用于静态截图/降级：?reveal=all 直接显示全部卡片，不做入场动画 */
  const FORCE_REVEAL = /[?&]reveal=all/.test(location.search) || !('IntersectionObserver' in window);
  /* 年份目录本身就是时间线，不再重复出现在分组里 */
  const THEME_ALBUMS = (DATA.albums || []).filter((a) => !/^\d{4}$/.test(a.k));

  const $ = (sel, root = document) => root.querySelector(sel);
  const el = (tag, cls, html) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html != null) n.innerHTML = html;
    return n;
  };
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  /* 缩略图缺失时的暖色占位（内联 SVG，零请求） */
  const PLACEHOLDER = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400">' +
    '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">' +
    '<stop offset="0" stop-color="#f4e6d1"/><stop offset="1" stop-color="#e2c8a4"/>' +
    '</linearGradient></defs><rect width="400" height="400" fill="url(#g)"/></svg>');

  const state = {
    year: 'all',
    album: 'all',
    type: 'all',
    q: '',
    desc: true,          // 默认从晚到早
    page: 1,
  };

  /* ---------------- 日期辅助 ---------------- */
  const pad = (n) => (n < 10 ? '0' + n : '' + n);

  function dParts(d) {                       // "2018-01-18 21:15:18"
    if (!d) return null;
    return { y: +d.slice(0, 4), m: +d.slice(5, 7), d: +d.slice(8, 10), t: d.slice(11, 19) };
  }
  function monthKey(it) {
    const p = dParts(it.d);
    return p ? `${p.y}-${pad(p.m)}` : 'none';
  }
  function monthLabel(key) {
    if (key === 'none') return { year: '未标注时间', month: '按分组排列' };
    const [y, m] = key.split('-');
    return { year: `${y} 年`, month: `${+m} 月` };
  }
  function itemDateText(it) {
    const p = dParts(it.d);
    if (!p) return '未标注日期';
    return `${p.y}.${pad(p.m)}.${pad(p.d)} ${p.t.slice(0, 5)}`;
  }

  /* ---------------- 筛选 ---------------- */
  function matches(it, skip) {
    if (skip !== 'year' && state.year !== 'all') {
      if (state.year === UNDATED ? !!it.d : it.y !== +state.year) return false;
    }
    if (skip !== 'album' && state.album !== 'all' && it.a !== state.album) return false;
    if (skip !== 'type' && state.type !== 'all' && it.t !== state.type) return false;
    if (state.q) {
      const q = state.q.toLowerCase();
      const hay = (it.n + ' ' + it.a + ' ' + it.d).toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  }

  function currentList() {
    const list = ITEMS.filter((it) => matches(it));
    if (!state.desc) return list;          // ITEMS 本身按时间升序
    /* 从晚到早：倒转有日期的部分，未标注日期的始终留在最后 */
    const dated = [];
    const undated = [];
    list.forEach((it) => (it.d ? dated : undated).push(it));
    dated.reverse();
    return dated.concat(undated);
  }

  /* ---------------- 顶部统计 ---------------- */
  function renderStats() {
    $('#statAll').textContent = ITEMS.length.toLocaleString();
    $('#statImg').textContent = ITEMS.filter((i) => i.t === 'i').length.toLocaleString();
    $('#statVid').textContent = ITEMS.filter((i) => i.t === 'v').length.toLocaleString();
    $('#statAlbum').textContent = DATA.albums.length;
    $('#genTime').textContent = DATA.generated || '—';
  }

  /* ---------------- 胶片拼贴：桌面 / 移动端均 5 张，静态展示不轮换 ----------------
     移动端屏窄：间距按视口比例收窄，5 张同样叠放开（旋转角度与桌面一致） */
  const mqMobile = window.matchMedia('(max-width: 900px)');
  const clParams = () => ({
    slots: 5,
    gap: mqMobile.matches ? Math.round(window.innerWidth * 0.13) : 112,
    rots: [-11, -5, 0, 6, 12],
  });

  function renderCollage() {
    const box = $('#heroCollage');
    if (!box) return;
    const { slots: CL_SLOTS, gap: CL_GAP, rots: CL_ROTS } = clParams();
    box.innerHTML = '';
    const pool = ITEMS.filter((i) => i.th && i.t === 'i');
    if (pool.length <= CL_SLOTS) return;
    const shown = new Set();
    const take = () => {
      const avail = pool.filter((p) => !shown.has(p));
      const it = avail[Math.floor(Math.random() * avail.length)];
      shown.add(it);
      return it;
    };

    for (let i = 0; i < CL_SLOTS; i++) {
      const it = take();
      const p = el('div', 'polaroid');
      p.innerHTML = `<div class="polaroid-card"><img src="${it.th}" alt="" loading="lazy"></div>`;
      /* 点击拼贴卡片 = 打开灯箱看原图，左右翻页按时间序走全部照片 */
      p.firstChild.style.cursor = 'pointer';
      p.firstChild.addEventListener('click', () => openLightbox(it.id, pool));
      p.style.setProperty('--rot', CL_ROTS[i] + 'deg');
      p.style.setProperty('--z', String(10 - Math.abs(i - (CL_SLOTS - 1) / 2)));
      p.style.marginLeft = ((i - (CL_SLOTS - 1) / 2) * CL_GAP) + 'px';
      /* 负延迟只错开摆动相位，不产生等待 */
      p.firstChild.style.animationDelay = (-i * 1.3) + 's';
      box.appendChild(p);
    }
  }
  /* 桌面 ↔ 移动端断点切换时重建拼贴（间距随视口宽度重算） */
  mqMobile.addEventListener('change', renderCollage);

  /* ---------------- 微尘 ---------------- */
  function renderDust() {
    const box = $('#dust');
    if (!box || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    for (let i = 0; i < 24; i++) {
      const d = el('div', 'mote');
      const s = 2 + Math.random() * 5;
      d.style.width = d.style.height = s + 'px';
      d.style.left = (Math.random() * 100) + '%';
      d.style.top = (60 + Math.random() * 50) + '%';
      d.style.setProperty('--dx', (Math.random() * 120 - 60) + 'px');
      d.style.animationDuration = (16 + Math.random() * 22) + 's';
      d.style.animationDelay = (-Math.random() * 30) + 's';
      d.style.opacity = 0;
      box.appendChild(d);
    }
  }

  /* ---------------- 筛选 chip ---------------- */
  function renderChips() {
    /* 年份 */
    const ybox = $('#yearChips');
    ybox.innerHTML = '';

    const mkYear = (key, label) => {
      const cnt = key === 'all'
        ? ITEMS.filter((it) => matches(it, 'year')).length
        : (key === UNDATED
          ? ITEMS.filter((it) => !it.d && matches(it, 'year')).length
          : ITEMS.filter((it) => it.y === key && matches(it, 'year')).length);
      const b = el('button', 'chip' + (state.year === key ? ' on' : ''),
        `${label}<em>${cnt}</em>`);
      b.onclick = () => { state.year = key; state.page = 1; sync({ chips: true }); };
      return b;
    };

    ybox.appendChild(mkYear('all', '全部'));
    /* 年份从晚到早，和默认排序一致；「未标注」永远压在最后 */
    [...DATA.years].sort((a, b) => b - a).forEach((y) => ybox.appendChild(mkYear(y, String(y))));
    const undated = ITEMS.filter((i) => !i.d).length;
    if (undated) ybox.appendChild(mkYear(UNDATED, '未标注'));

    /* 相册 */
    const abox = $('#albumChips');
    abox.innerHTML = '';
    const mkAlbum = (key, label, cnt) => {
      const b = el('button', 'chip small' + (state.album === key ? ' on' : ''), `${label}<em>${cnt}</em>`);
      b.onclick = () => { state.album = key; state.page = 1; sync({ chips: true }); };
      return b;
    };
    abox.appendChild(mkAlbum('all', '全部分组', ITEMS.filter((it) => matches(it, 'album')).length));
    THEME_ALBUMS.forEach((a) => {
      const cnt = ITEMS.filter((it) => it.a === a.k && matches(it, 'album')).length;
      abox.appendChild(mkAlbum(a.k, a.k, cnt));
    });
  }

  /* ---------------- 网格 ---------------- */
  const cardObserver = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (e.isIntersecting) {
        e.target.classList.add('in');
        cardObserver.unobserve(e.target);
      }
    });
  }, { rootMargin: '120px 0px 200px', threshold: 0.01 });

  function cardNode(it) {
    const c = el('article', 'card' + (it.t === 'v' ? ' is-video' : ''));
    c.dataset.id = it.id;
    c.tabIndex = 0;
    c.setAttribute('role', 'button');
    c.setAttribute('aria-label', `${it.a} ${itemDateText(it)}`);

    /* 视频也有预生成的封面缩略图；只有点开灯箱才去 CDN 拉原视频 */
    const src = it.th || (it.t === 'i' ? resURL(it.p) : null);
    if (src) {
      const img = el('img', 'thumb');
      img.loading = 'lazy';
      img.decoding = 'async';
      img.alt = it.n;
      img.src = src;
      img.onerror = () => {
        /* 只有图片才有原图可回退；视频封面挂了就停在占位图，别去拉原视频 */
        if (!img.dataset.fb && it.t === 'i' && it.th) { img.dataset.fb = '1'; img.src = resURL(it.p); }
        else img.src = PLACEHOLDER;
      };
      c.appendChild(img);
    } else {
      const ph = el('img', 'thumb');
      ph.alt = '';
      ph.src = PLACEHOLDER;
      c.appendChild(ph);
    }
    if (it.t === 'v') {
      c.appendChild(el('div', 'play-badge'));
      /* 没有封面的视频多半是坏文件，直接标注，不再去 CDN 试帧 */
      if (!it.th) {
        c.classList.add('media-bad');
        c.appendChild(el('span', 'bad-mark', '格式异常'));
      }
    }

    const meta = el('div', 'card-meta');
    meta.innerHTML = `<span class="cm-date">${itemDateText(it)}</span><span class="cm-tag">${esc(it.a)}</span>`;
    c.appendChild(meta);

    c.addEventListener('click', () => openLightbox(it.id));
    c.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openLightbox(it.id); }
    });
    return c;
  }

  /* 折叠状态下那条摘要：当前时间线 / 分组 / 类型 / 搜索 / 总数 */
  function summaryText(n) {
    const parts = [state.year === 'all' ? '全部时间'
      : state.year === UNDATED ? '未标注时间' : `${state.year} 年`];
    if (state.album !== 'all') parts.push(state.album);
    if (state.type !== 'all') parts.push(state.type === 'i' ? '照片' : '视频');
    if (state.q) parts.push(`搜「${state.q}」`);
    parts.push(`${n.toLocaleString()} 项`);
    return parts.join(' · ');
  }

  function renderGrid() {
    const list = currentList();
    const totalPages = Math.max(1, Math.ceil(list.length / PER_PAGE));
    if (state.page > totalPages) state.page = totalPages;
    const start = (state.page - 1) * PER_PAGE;
    const slice = list.slice(start, start + PER_PAGE);

    const grid = $('#grid');
    grid.innerHTML = '';
    $('#empty').hidden = list.length > 0;

    let lastKey = null;
    const frag = document.createDocumentFragment();
    slice.forEach((it) => {
      const key = monthKey(it);
      if (key !== lastKey) {
        const lb = monthLabel(key);
        const row = el('div', 'month-row');
        row.innerHTML = `<span class="mr-year">${lb.year}</span>
          <span class="mr-month">${lb.month}</span>
          <span class="mr-line"></span>
          <span class="mr-count">${list.filter((x) => monthKey(x) === key).length} 项</span>`;
        frag.appendChild(row);
        lastKey = key;
      }
      frag.appendChild(cardNode(it));
    });
    grid.appendChild(frag);

    /* 渐次入场 */
    const cards = grid.querySelectorAll('.card');
    cards.forEach((c, i) => {
      c.style.transitionDelay = Math.min(i, 12) * 28 + 'ms';
      if (FORCE_REVEAL) { c.classList.add('in'); c.style.transitionDelay = '0ms'; }
      else cardObserver.observe(c);
    });

    $('#resultCount').innerHTML = `共 <b>${list.length}</b> 项${state.q ? ' · 含搜索' : ''}`;
    $('#filterSummary').textContent = summaryText(list.length);
    renderPager(list.length, totalPages);
    renderChips();
  }

  function renderPager(total, totalPages) {
    const pager = $('#pager');
    pager.innerHTML = '';
    if (total === 0) return;

    const mkBtn = (label, page, opts = {}) => {
      const b = el('button', 'pg' + (opts.on ? ' on' : ''), label);
      b.disabled = !!opts.disabled;
      if (opts.on) b.setAttribute('aria-current', 'page');
      if (!opts.disabled && !opts.on) b.onclick = () => goPage(page);
      return b;
    };

    pager.appendChild(mkBtn('‹ 上一页', state.page - 1, { disabled: state.page === 1 }));

    const pages = [];
    const push = (p) => pages.push(p);
    if (totalPages <= 7) { for (let i = 1; i <= totalPages; i++) push(i); }
    else {
      push(1);
      if (state.page > 3) push('…');
      for (let i = Math.max(2, state.page - 1); i <= Math.min(totalPages - 1, state.page + 1); i++) push(i);
      if (state.page < totalPages - 2) push('…');
      push(totalPages);
    }
    pages.forEach((p) => {
      if (p === '…') pager.appendChild(el('span', 'pg-gap', '…'));
      else pager.appendChild(mkBtn(String(p), p, { on: p === state.page }));
    });

    pager.appendChild(mkBtn('下一页 ›', state.page + 1, { disabled: state.page === totalPages }));

    const info = el('div', 'pg-info',
      `第 <b>${state.page}</b> / ${totalPages} 页 · 每页 ${PER_PAGE} 项 · 共 <b>${total}</b> 项`);
    pager.appendChild(info);
  }

  function goPage(p) {
    state.page = p;
    renderGrid();
    const top = $('#browser').getBoundingClientRect().top + window.scrollY - 130;
    window.scrollTo({ top, behavior: 'smooth' });
  }

  /* ---------------- 灯箱 ---------------- */
  const lb = $('#lightbox');
  const lbFig = $('#lbFigure');
  const lbCap = $('#lbCap');
  let lbList = [];
  let lbIndex = 0;

  function openLightbox(id, list) {
    /* list 可选：拼贴等场景传入自定义播放列表（如全部照片按时间序） */
    lbList = list || currentList();
    lbIndex = lbList.findIndex((x) => x.id === id);
    if (lbIndex < 0) { lbList = currentList(); lbIndex = lbList.findIndex((x) => x.id === id); }
    if (lbIndex < 0) lbIndex = 0;
    showLightbox();
  }

  /* ---------------- 灯箱图片缩放：滚轮（桌面）/ 双指捏合（移动）/ 拖拽平移 ---------------- */
  const ZOOM_MAX = 8;
  let zImg = null, zScale = 1, zTx = 0, zTy = 0;

  function zClampPan() {
    /* 放大后允许平移的范围 = 溢出尺寸的一半，保证图不会拖出屏幕 */
    const r = zImg.getBoundingClientRect();
    const limX = Math.max(0, (r.width - r.width / zScale) / 2);
    const limY = Math.max(0, (r.height - r.height / zScale) / 2);
    zTx = Math.min(limX, Math.max(-limX, zTx));
    zTy = Math.min(limY, Math.max(-limY, zTy));
  }
  function zApply() {
    zImg.style.transform = `translate(${zTx}px, ${zTy}px) scale(${zScale})`;
    zImg.classList.toggle('zmed', zScale > 1);
  }
  function zReset(smooth) {
    zScale = 1; zTx = 0; zTy = 0;
    if (!zImg) return;
    if (smooth) {
      zImg.style.transition = 'transform .3s var(--ease)';
      zApply();
      setTimeout(() => { if (zImg) zImg.style.transition = ''; }, 320);
    } else zApply();
  }
  function zoomBind(img) {
    zImg = img;
    img.draggable = false;
    zReset(false);
  }

  /* 桌面：滚轮以鼠标位置为锚点缩放 */
  lb.addEventListener('wheel', (e) => {
    if (lb.hidden || !zImg || !zImg.isConnected) return;
    e.preventDefault();
    const ns = Math.min(ZOOM_MAX, Math.max(1, zScale * (e.deltaY < 0 ? 1.18 : 1 / 1.18)));
    if (ns === zScale) return;
    const r = zImg.getBoundingClientRect();
    const cx = e.clientX - (r.left + r.width / 2);
    const cy = e.clientY - (r.top + r.height / 2);
    const k = ns / zScale;
    zTx = cx - k * (cx - zTx);
    zTy = cy - k * (cy - zTy);
    zScale = ns;
    if (zScale === 1) { zTx = 0; zTy = 0; } else zClampPan();
    zApply();
  }, { passive: false });

  /* 移动：双指捏合缩放（锚点跟随双指中心），单指放大后平移 */
  let pinch = null, pan = null, drag = null;
  lb.addEventListener('touchstart', (e) => {
    if (lb.hidden) return;
    if (e.touches.length === 2 && zImg && zImg.isConnected) {
      const [a, b] = e.touches;
      const r = zImg.getBoundingClientRect();
      pinch = {
        d: Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY) || 1,
        s: zScale, tx: zTx, ty: zTy,
        mx: (a.clientX + b.clientX) / 2, my: (a.clientY + b.clientY) / 2,
        cx: r.left + r.width / 2, cy: r.top + r.height / 2
      };
      pan = null;
    } else if (e.touches.length === 1 && zScale > 1 && zImg) {
      pan = { x: e.touches[0].clientX, y: e.touches[0].clientY, tx: zTx, ty: zTy };
    }
  }, { passive: true });

  lb.addEventListener('touchmove', (e) => {
    if (pinch && e.touches.length === 2 && zImg) {
      e.preventDefault();
      const [a, b] = e.touches;
      const d = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY) || 1;
      const ns = Math.min(ZOOM_MAX, Math.max(1, pinch.s * (d / pinch.d)));
      zScale = ns;
      if (ns === 1) { zTx = 0; zTy = 0; }
      else {
        const mx = (a.clientX + b.clientX) / 2, my = (a.clientY + b.clientY) / 2;
        const p0x = (pinch.mx - pinch.cx) / pinch.s;   /* 起始锚点的图像局部坐标 */
        const p0y = (pinch.my - pinch.cy) / pinch.s;
        zTx = mx - pinch.cx + pinch.tx - ns * p0x;
        zTy = my - pinch.cy + pinch.ty - ns * p0y;
        zClampPan();
      }
      zApply();
    } else if (pan && e.touches.length === 1 && zScale > 1 && zImg) {
      e.preventDefault();
      zTx = pan.tx + (e.touches[0].clientX - pan.x);
      zTy = pan.ty + (e.touches[0].clientY - pan.y);
      zClampPan();
      zApply();
    }
  }, { passive: false });

  /* 手指抬起：清掉捏合/平移状态，剩下的单指可无缝转平移 */
  let lastPinchEnd = 0;
  lb.addEventListener('touchend', (e) => {
    if (pinch && e.touches.length < 2) {
      pinch = null;
      lastPinchEnd = Date.now();
      if (e.touches.length === 1 && zScale > 1 && zImg) {
        pan = { x: e.touches[0].clientX, y: e.touches[0].clientY, tx: zTx, ty: zTy };
      }
    }
    if (!e.touches.length) pan = null;
  }, { passive: true });

  /* 桌面：放大后按住拖拽平移 */
  lb.addEventListener('mousedown', (e) => {
    if (lb.hidden || zScale <= 1 || !zImg || !zImg.isConnected || e.button !== 0) return;
    drag = { x: e.clientX, y: e.clientY, tx: zTx, ty: zTy };
    zImg.classList.add('zgrab');
    e.preventDefault();
  });
  window.addEventListener('mousemove', (e) => {
    if (!drag || !zImg) return;
    zTx = drag.tx + (e.clientX - drag.x);
    zTy = drag.ty + (e.clientY - drag.y);
    zClampPan();
    zApply();
  });
  window.addEventListener('mouseup', () => {
    if (!drag) return;
    drag = null;
    if (zImg) zImg.classList.remove('zgrab');
  });

  /* 双击：放大到 2.5x / 复位 */
  lbFig.addEventListener('dblclick', (e) => {
    if (!zImg || !zImg.isConnected) return;
    e.preventDefault();
    if (zScale > 1) { zReset(true); return; }
    const ns = 2.5;
    const r = zImg.getBoundingClientRect();
    const cx = e.clientX - (r.left + r.width / 2);
    const cy = e.clientY - (r.top + r.height / 2);
    const k = ns / zScale;
    zTx = cx - k * (cx - zTx);
    zTy = cy - k * (cy - zTy);
    zScale = ns;
    zClampPan();
    zApply();
  });

  function showLightbox() {
    const it = lbList[lbIndex];
    if (!it) return;
    lb.hidden = false;
    document.body.style.overflow = 'hidden';
    lbFig.innerHTML = '';

    if (it.t === 'v') {
      zImg = null;
      const v = document.createElement('video');
      v.src = resURL(it.p);
      v.controls = true; v.autoplay = true; v.playsInline = true;
      v.preload = 'metadata';
      v.addEventListener('error', () => {
        const c = v.error && v.error.code;
        const netFail = c === 1 || c === 2;   /* ABORTED / NETWORK */
        lbFig.innerHTML = netFail
          ? `<div class="lb-broken">
              <b>这个视频没加载出来</b>
              <span>网络或 CDN 稍不稳定，关掉再点一次试试。</span>
            </div>`
          : `<div class="lb-broken">
              <b>这个文件暂时放不出来</b>
              <span>扩展名是 <code>${esc(it.p.split('.').pop())}</code>，实际是视频格式，<br>重命名成 <code>.mp4</code> 就能正常播放。</span>
            </div>`;
      }, { once: true });
      lbFig.appendChild(v);
    } else {
      const img = document.createElement('img');
      img.src = resURL(it.p);
      img.alt = it.n;
      img.decoding = 'async';
      /* 扩展名异常的原图可能无法解码，退回缩略图 */
      img.onerror = () => { if (it.th) img.src = it.th; };
      lbFig.appendChild(img);
      zoomBind(img);
    }

    const p = dParts(it.d);
    const dateTxt = p ? `${p.y} 年 ${p.m} 月 ${p.d} 日 · ${p.t}` : '未标注日期';
    const note = it.w ? ' · 扩展名与实际格式不符' : '';
    const fname = it.p.split('/').pop();
    lbCap.innerHTML = `<div class="cap-main">${esc(it.a)}</div>
      <button class="cap-name" type="button" title="点击复制文件名">${esc(fname)}</button>
      <div class="cap-sub">${dateTxt}${note}<span class="cap-count">${lbIndex + 1} / ${lbList.length}</span></div>`;

    /* 点文件名 = 复制（含扩展名），按钮短暂显示结果 */
    const nameBtn = lbCap.querySelector('.cap-name');
    nameBtn.addEventListener('click', async () => {
      const ok = await copyText(fname);
      nameBtn.classList.add(ok ? 'copied' : 'fail');
      nameBtn.textContent = ok ? '已复制 ✓' : '复制失败';
      setTimeout(() => {
        nameBtn.textContent = fname;
        nameBtn.classList.remove('copied', 'fail');
      }, 1200);
    });
  }

  /* 剪贴板：先在用户手势内同步走 execCommand（最稳），
     失败再试 Clipboard API（需 https 安全上下文） */
  function copyText(text) {
    try {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.cssText = 'position:fixed;top:-999px;opacity:0';
      document.body.appendChild(ta);
      ta.focus();
      ta.setSelectionRange(0, text.length);
      const ok = document.execCommand('copy');
      ta.remove();
      if (ok) return Promise.resolve(true);
    } catch (e) { /* 继续走现代 API */ }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).then(() => true).catch(() => false);
    }
    return Promise.resolve(false);
  }

  function closeLightbox() {
    lb.hidden = true;
    lbFig.innerHTML = '';
    zImg = null; pinch = null; pan = null; drag = null;
    document.body.style.overflow = '';
  }

  function stepLightbox(delta) {
    if (!lbList.length) return;
    lbIndex = (lbIndex + delta + lbList.length) % lbList.length;
    showLightbox();
  }

  $('#lbClose').onclick = closeLightbox;
  lb.querySelector('.lb-backdrop').onclick = closeLightbox;
  $('#lbPrev').onclick = () => stepLightbox(-1);
  $('#lbNext').onclick = () => stepLightbox(1);

  document.addEventListener('keydown', (e) => {
    if (lb.hidden) return;
    if (e.key === 'Escape') closeLightbox();
    else if (e.key === 'ArrowLeft') stepLightbox(-1);
    else if (e.key === 'ArrowRight') stepLightbox(1);
  });

  /* 触屏左右滑动翻页（放大查看时不翻页，让位给拖拽平移） */
  let tStartX = 0;
  lb.addEventListener('touchstart', (e) => {
    if (e.touches.length === 1) tStartX = e.touches[0].clientX;
  }, { passive: true });
  lb.addEventListener('touchend', (e) => {
    if (pinch || zScale > 1 || e.touches.length) return;
    if (Date.now() - lastPinchEnd < 350) return;   /* 捏合刚结束不当作滑动 */
    const dx = e.changedTouches[0].clientX - tStartX;
    if (Math.abs(dx) > 60) stepLightbox(dx > 0 ? -1 : 1);
  }, { passive: true });

  /* ---------------- 交互绑定 ---------------- */
  $('#typeSeg').addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    state.type = b.dataset.type;
    state.page = 1;
    [...$('#typeSeg').children].forEach((x) => x.classList.toggle('on', x === b));
    sync({ chips: true });
  });

  let qTimer = null;
  $('#search').addEventListener('input', (e) => {
    clearTimeout(qTimer);
    qTimer = setTimeout(() => {
      state.q = e.target.value.trim();
      state.page = 1;
      sync({ chips: true });
    }, 260);
  });

  /* ---------------- 排序 ---------------- */
  function setSortUI() {
    $('#sortBtn').classList.toggle('desc', state.desc);
    $('#sortBtn').setAttribute('aria-label', state.desc ? '当前从晚到早，点击切换' : '当前从早到晚，点击切换');
    $('#sortTxt').textContent = state.desc ? '从晚到早' : '从早到晚';
  }

  $('#sortBtn').addEventListener('click', () => {
    state.desc = !state.desc;
    state.page = 1;
    setSortUI();
    sync();
  });

  /* ---------------- 过滤栏折叠（置顶固定后可用） ---------------- */
  const toTop = $('#toTop');
  toTop.onclick = () => window.scrollTo({ top: 0, behavior: 'smooth' });

  const filters = $('#filters');
  const filterToggle = $('#filterToggle');
  const COLLAPSE_KEY = 'xtt.filters.collapsed';
  let collapsed = false;
  try { collapsed = localStorage.getItem(COLLAPSE_KEY) === '1'; } catch (e) {}

  function isFolded() {
    /* 开关常驻，收起状态在任何滚动位置都生效 */
    return collapsed;
  }

  function applyCollapse() {
    const folded = isFolded();
    filters.classList.toggle('collapsed', folded);
    filterToggle.setAttribute('aria-expanded', String(!folded));
    filterToggle.querySelector('.ft-txt').textContent = folded ? '展开筛选' : '收起筛选';
    filterToggle.setAttribute('aria-label', folded ? '展开筛选条件' : '收起筛选条件');
  }

  filterToggle.addEventListener('click', () => {
    collapsed = !collapsed;
    try { localStorage.setItem(COLLAPSE_KEY, collapsed ? '1' : '0'); } catch (e) {}
    acc = 0;                 // 清掉方向累积，避免点开后又立刻被残留的滚动趋势收起
    applyCollapse();
  });

  let prevStuck = null;
  let prevTopBtn = null;
  const userbar = $('#userbar');
  /* 滚动方向驱动筛选栏：吸顶后向下滚自动收起、向上滚自动展开。
     累计滚动超过阈值才切换，避免惯性微滚来回抖动 */
  let lastY = window.scrollY;
  let acc = 0;
  const DIR_T = 24;
  function onScroll() {
    const y = window.scrollY;
    const stuck = y > 320;
    if (stuck !== prevStuck) {
      prevStuck = stuck;
      filters.classList.toggle('stuck', stuck);
      if (userbar) userbar.classList.toggle('hide', stuck);   // 别压住右上角的折叠按钮
      applyCollapse();
    }
    /* 自动收起只发生在吸顶状态；向上滚（含回到顶部脱离吸顶）必定展开。
       自动变化不写 localStorage：刷新后回到用户手动选择的状态 */
    const dy = y - lastY;
    lastY = y;
    if (dy !== 0) acc = Math.max(-DIR_T, Math.min(DIR_T, acc + dy));
    if (acc >= DIR_T && stuck && !collapsed) {
      collapsed = true;
      applyCollapse();
    } else if ((acc <= -DIR_T || !stuck) && collapsed) {
      collapsed = false;
      applyCollapse();
    }
    const showTop = y > 900;
    if (showTop !== prevTopBtn) {
      prevTopBtn = showTop;
      toTop.classList.toggle('show', showTop);
    }
  }
  window.addEventListener('scroll', onScroll, { passive: true });

  /* ---------------- 统一刷新 ---------------- */
  function sync() {
    renderGrid();
    writeHash();
  }

  /* ---------------- URL 状态 ---------------- */
  function writeHash() {
    const p = new URLSearchParams();
    if (state.year !== 'all') p.set('y', state.year);
    if (state.album !== 'all') p.set('a', state.album);
    if (state.type !== 'all') p.set('t', state.type);
    if (state.q) p.set('q', state.q);
    if (!state.desc) p.set('d', '0');      // 默认从晚到早，只有顺序反过来时才记
    if (state.page > 1) p.set('p', state.page);
    const s = p.toString();
    history.replaceState(null, '', s ? '#' + s : location.pathname + location.search);
  }

  function readHash() {
    /* 先回到默认，这样地址栏 hash 变化时能正确地把删掉的条件也一并重置 */
    state.year = 'all';
    state.album = 'all';
    state.type = 'all';
    state.q = '';
    state.desc = true;
    state.page = 1;
    $('#search').value = '';
    [...$('#typeSeg').children].forEach((x) => x.classList.toggle('on', x.dataset.type === 'all'));

    const raw = location.hash.replace(/^#/, '');
    if (!raw) return;
    const p = new URLSearchParams(raw);
    if (p.has('y')) state.year = p.get('y') === UNDATED ? UNDATED : (+p.get('y') || 'all');
    if (p.has('a')) state.album = p.get('a');
    if (p.has('t')) state.type = p.get('t');
    if (p.has('q')) { state.q = p.get('q'); $('#search').value = state.q; }
    if (p.has('d')) state.desc = p.get('d') !== '0';   // 兼容旧链接 d=1
    if (p.has('p')) state.page = Math.max(1, +p.get('p') || 1);
    if (state.type !== 'all') {
      [...$('#typeSeg').children].forEach((x) => x.classList.toggle('on', x.dataset.type === state.type));
    }
  }

  window.addEventListener('hashchange', () => {
    readHash();
    setSortUI();
    renderGrid();
  });

  /* ---------------- 启动 ---------------- */
  renderStats();
  renderDust();
  renderCollage();
  readHash();
  setSortUI();
  applyCollapse();     // 先按记忆恢复收起状态，避免闪一下
  renderGrid();
  onScroll();          // 从带 hash 的链接进来时可能已经在页面中部

})();
