/* tech 主题交互：主题切换、移动端抽屉菜单、回到顶部 */
(function () {
  'use strict';

  /* 品牌提示：与 default 主题（static/js/main.js）一致，控制台可见 */
  console.log('%c infowe.site %c 豪子 - 工作机会 VX：CQGGTF ',
    'background:linear-gradient(135deg,#00d4ff,#a855f7);color:#fff;padding:4px 8px;border-radius:4px;font-weight:bold;',
    'color:#00d4ff;');

  /* ── 主题切换：三态循环（auto 跟随系统 → light → dark → auto） ── */
  var toggle = document.getElementById('theme-toggle');
  var rootEl = document.documentElement;
  var SYS_DARK = window.matchMedia('(prefers-color-scheme: dark)');

  function syncTechTheme() {
    var mode = rootEl.getAttribute('data-theme-mode') || 'auto';
    rootEl.setAttribute('data-theme', mode === 'auto' ? (SYS_DARK.matches ? 'dark' : 'light') : mode);
    if (toggle) {
      var modeName = mode === 'auto' ? '自动（跟随系统）' : (mode === 'dark' ? '深色' : '浅色');
      var label = '当前：' + modeName + '，点击切换主题';
      toggle.setAttribute('aria-label', label);
      toggle.title = label;
    }
  }
  if (toggle) {
    // 系统主题变化：仅 auto（跟随系统）态实时跟随
    if (SYS_DARK.addEventListener) SYS_DARK.addEventListener('change', syncTechTheme);
    else if (SYS_DARK.addListener) SYS_DARK.addListener(syncTechTheme);

    toggle.addEventListener('click', function () {
      var mode = rootEl.getAttribute('data-theme-mode') || 'auto';
      var next = mode === 'auto' ? 'light' : (mode === 'light' ? 'dark' : 'auto');
      rootEl.setAttribute('data-theme-mode', next);
      try { localStorage.setItem('infowe-theme', next); } catch (e) {}
      syncTechTheme();
    });
    // 启动时同步按钮提示文案（实际明暗已由 head 内联脚本设好）
    syncTechTheme();
  }

  /* ── 移动端抽屉菜单 ── */
  var burger = document.getElementById('tech-burger');
  var overlay = document.getElementById('tech-drawer-overlay');
  var drawer = document.getElementById('tech-drawer');
  var closeBtn = document.getElementById('tech-drawer-close');

  function openDrawer() {
    overlay.classList.add('open');
    drawer.classList.add('open');
    document.body.style.overflow = 'hidden';
  }
  function closeDrawer() {
    overlay.classList.remove('open');
    drawer.classList.remove('open');
    document.body.style.overflow = '';
  }

  if (burger && overlay && drawer) {
    burger.addEventListener('click', openDrawer);
    overlay.addEventListener('click', closeDrawer);
    if (closeBtn) closeBtn.addEventListener('click', closeDrawer);
    drawer.querySelectorAll('a').forEach(function (a) {
      a.addEventListener('click', closeDrawer);
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeDrawer();
    });
  }

  /* ── 回到顶部 ── */
  var topBtn = document.getElementById('tech-top');
  if (topBtn) {
    var _scrollTick = false;
    window.addEventListener('scroll', function () {
      if (_scrollTick) return;
      _scrollTick = true;
      requestAnimationFrame(function () {
        var y = window.scrollY || document.documentElement.scrollTop;
        topBtn.classList.toggle('show', y > 320);
        topBtn.classList.toggle('scrolled', y > 400);
        _scrollTick = false;
      });
    }, { passive: true });
    topBtn.addEventListener('click', function () {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }
})();

/* ── 首页终端格言：一言 API（5s 超时）+ 本地兜底，打字机输出，点击换一条 ── */
(function () {
  'use strict';
  var quoteText = document.getElementById('tech-quote-text');
  if (!quoteText) return; // 该区块仅首页渲染，其它页面直接跳过

  var srcEl = document.getElementById('tech-quote-src');
  var refreshBtn = document.getElementById('tech-quote-refresh');

  /* 本地兜底句子库：一言不可达 / 超时 / 返回异常时使用 */
  var FALLBACK = [
    { text: 'Talk is cheap. Show me the code.', src: 'Linus Torvalds' },
    { text: 'Stay hungry, stay foolish.', src: 'Steve Jobs' },
    { text: '学而不思则罔，思而不学则殆。', src: '《论语》' },
    { text: '君子藏器于身，待时而动。', src: '《周易》' },
    { text: '博学之，审问之，慎思之，明辨之，笃行之。', src: '《礼记·中庸》' },
    { text: '任何足够先进的技术都与魔法无异。', src: 'Arthur C. Clarke' },
    { text: '简单是可靠的先决条件。', src: 'Edsger W. Dijkstra' },
    { text: '把一件事做到极致，胜过平庸地做一万件事。', src: '' },
    { text: '代码如诗：先让它正确，再让它清晰，最后让它简洁。', src: '' },
    { text: '道阻且长，行则将至；行而不辍，未来可期。', src: '' },
    { text: '早优化是万恶之源：先量化，再优化，后庆祝。', src: '' },
    { text: '热爱可抵岁月漫长。', src: '' }
  ];

  var timers = [];
  var seq = 0;      // 取句序号：防止异步请求乱序覆盖
  var MAX_LEN = 120;

  function clearTimers() {
    timers.forEach(function (t) { clearTimeout(t); });
    timers = [];
  }

  /* 逐字打字输出，完成后延时淡出出处 */
  function typeQuote(text, src) {
    clearTimers();
    srcEl.textContent = '';
    quoteText.textContent = '';
    var chars = Array.from(String(text || '').slice(0, MAX_LEN));
    if (!chars.length) return;
    var i = 0;
    var step = chars.length > 60 ? 34 : 60; // 长句适当提速，避免等待过久
    timers.push(setInterval(function () {
      i += 1;
      quoteText.textContent = chars.slice(0, i).join('');
      if (i >= chars.length) {
        clearTimers();
        if (src) timers.push(setTimeout(function () { srcEl.textContent = src; }, 260));
      }
    }, step));
  }

  function renderLocal() {
    var item = FALLBACK[Math.floor(Math.random() * FALLBACK.length)];
    typeQuote(item.text, item.src);
  }

  function loadQuote() {
    var my = ++seq;
    quoteText.textContent = '';
    srcEl.textContent = '';
    var ctrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
    var guard = setTimeout(function () { if (ctrl) ctrl.abort(); }, 5000);
    fetch('https://v1.hitokoto.cn/?encode=json&lang=cn', { signal: ctrl && ctrl.signal })
      .then(function (res) {
        clearTimeout(guard);
        if (!res.ok) throw new Error('http ' + res.status);
        return res.json();
      })
      .then(function (d) {
        if (my !== seq) return; // 已有更新的请求，丢弃本次结果
        var text = d && d.hitokoto ? String(d.hitokoto) : '';
        if (!text) { renderLocal(); return; }
        var from = '';
        if (d.from_who && d.from) from = d.from_who + ' · ' + d.from;
        else if (d.from) from = d.from;
        typeQuote(text, from);
      })
      .catch(function () {
        clearTimeout(guard);
        if (my !== seq) return;
        renderLocal();
      });
  }

  if (refreshBtn) {
    refreshBtn.addEventListener('click', function () {
      refreshBtn.classList.add('spin');
      setTimeout(function () { refreshBtn.classList.remove('spin'); }, 300);
      loadQuote();
    });
  }

  if (quoteText) loadQuote();
})();

/* ── 全局搜索：导航放大镜按钮展开 / 收起下拉面板 ── */
(function () {
  'use strict';
  var openBtn = document.getElementById('tech-search-open');
  var layer = document.getElementById('tech-search-layer');
  var closeBtn = document.getElementById('tech-search-close');
  var input = document.getElementById('tech-search-input');
  if (!openBtn || !layer) return;

  function setOpen(open) {
    openBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
    layer.classList.toggle('open', open);
  }

  openBtn.addEventListener('click', function () {
    var isOpen = layer.classList.contains('open');
    setOpen(!isOpen);
    if (!isOpen && input) setTimeout(function () { input.focus(); }, 0);
  });
  if (closeBtn) closeBtn.addEventListener('click', function () {
    setOpen(false);
    if (openBtn) openBtn.focus();
  });
  // 面板内部点击不冒泡，避免误触发外部关闭
  layer.addEventListener('click', function (e) { e.stopPropagation(); });
  document.addEventListener('click', function (e) {
    if (layer.classList.contains('open') && !openBtn.contains(e.target)) setOpen(false);
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && layer.classList.contains('open')) setOpen(false);
  });
})();

/* ── 文章媒体灯箱：图片/视频点击浮窗，图片多图左右轮转（Esc 关闭，←/→ 切换） ── */
(function () {
  'use strict';
  var body = document.querySelector('.tech-post-body');
  if (!body) return;

  /* 汇总正文内图片与视频为轮转序列；排除 emoji 小图标（class 含 emoji 或宽 ≤ 24px） */
  function mediaList() {
    return Array.prototype.slice.call(body.querySelectorAll('img, video')).filter(function (el) {
      if (el.tagName !== 'IMG') return true;
      if (/emoji/i.test(el.className)) return false;
      var w = parseInt(el.getAttribute('width') || '', 10);
      if (w && w <= 24) return false;
      return true;
    });
  }

  var lb = null, stage = null, countEl = null;
  var items = [], cur = -1, lastFocus = null;

  function ensure() {
    if (lb) return;
    lb = document.createElement('div');
    lb.className = 'tech-lightbox';
    lb.setAttribute('role', 'dialog');
    lb.setAttribute('aria-modal', 'true');
    lb.setAttribute('aria-label', '媒体预览');

    stage = document.createElement('div');
    stage.className = 'tech-lightbox-stage';

    var close = document.createElement('button');
    close.type = 'button'; close.className = 'tech-lightbox-close';
    close.setAttribute('aria-label', '关闭');
    close.innerHTML = '&times;';

    var prev = document.createElement('button');
    prev.type = 'button'; prev.className = 'tech-lightbox-nav tech-lightbox-prev';
    prev.setAttribute('aria-label', '上一张');
    prev.textContent = '‹';

    var next = document.createElement('button');
    next.type = 'button'; next.className = 'tech-lightbox-nav tech-lightbox-next';
    next.setAttribute('aria-label', '下一张');
    next.textContent = '›';

    countEl = document.createElement('span');
    countEl.className = 'tech-lightbox-count';

    lb.appendChild(close);
    lb.appendChild(prev);
    lb.appendChild(stage);
    lb.appendChild(next);
    lb.appendChild(countEl);
    document.body.appendChild(lb);

    close.addEventListener('click', closeLb);
    prev.addEventListener('click', function () { show(cur - 1); });
    next.addEventListener('click', function () { show(cur + 1); });
    // 点击遮罩空白处关闭
    lb.addEventListener('click', function (e) { if (e.target === lb) closeLb(); });
  }

  function render() {
    if (!items.length) return;
    var el = items[cur];
    stage.textContent = '';

    var media;
    if (el.tagName === 'IMG') {
      media = document.createElement('img');
      media.className = 'tech-lightbox-media';
      media.src = el.currentSrc || el.src;
      media.alt = el.alt || '';
    } else {
      media = el.cloneNode(false); // 继承 src/poster 等属性
      media.className = 'tech-lightbox-media';
      media.controls = true;
      media.autoplay = true;
    }
    stage.appendChild(media);

    var multi = items.length > 1;
    countEl.textContent = multi ? (cur + 1) + ' / ' + items.length : '';
    countEl.style.visibility = multi ? '' : 'hidden';
    lb.querySelector('.tech-lightbox-prev').style.visibility = multi ? '' : 'hidden';
    lb.querySelector('.tech-lightbox-next').style.visibility = multi ? '' : 'hidden';
  }

  function show(i) {
    if (!items.length) return;
    cur = (i + items.length) % items.length;
    render();
  }

  function openLb(i, trigger) {
    items = mediaList();
    if (!items.length || !items[i]) return;
    cur = i;
    lastFocus = trigger;
    ensure();
    lb.classList.add('open');
    lb.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    render();
    lb.querySelector('.tech-lightbox-close').focus();
  }

  function closeLb() {
    if (!lb) return;
    lb.classList.remove('open');
    lb.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
    if (lastFocus) { lastFocus.focus(); lastFocus = null; }
  }

  // 点击正文图片 / 视频打开灯箱
  document.addEventListener('click', function (e) {
    if (!e.target.closest) return;
    var t = e.target.closest('img, video');
    if (!t || !body.contains(t)) return;
    e.preventDefault();
    var list = mediaList();
    var i = list.indexOf(t);
    if (i >= 0) openLb(i, t);
  });

  // 键盘：Esc 关闭，←/→ 切换
  document.addEventListener('keydown', function (e) {
    if (!lb || !lb.classList.contains('open')) return;
    if (e.key === 'Escape') closeLb();
    else if (e.key === 'ArrowLeft') show(cur - 1);
    else if (e.key === 'ArrowRight') show(cur + 1);
  });
})();

/* ── 文章目录：点击平滑滚动 + 滚动时高亮当前章节 ── */
(function () {
  var tocBody = document.querySelector('.tech-toc-body');
  var content = document.querySelector('.tech-post-body');
  if (!tocBody || !content) return;

  // 点击委托：拦截 #id 锚点，改用平滑滚动
  tocBody.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[href^="#"]');
    if (!a) return;
    var id = a.getAttribute('href').slice(1);
    var target = id && document.getElementById(id);
    if (!target) return;
    e.preventDefault();
    var headerOffset = 60; // 顶部导航高度预留
    var top = target.getBoundingClientRect().top + window.scrollY - headerOffset;
    window.scrollTo({ top: top, behavior: 'smooth' });
    history.replaceState(null, '', '#' + id);
  });

  // 当前章节高亮：基于 IntersectionObserver 监听 H2/H3
  var links = Array.prototype.slice.call(tocBody.querySelectorAll('a[href^="#"]'));
  if (!links.length) return;
  var map = {};
  links.forEach(function (a) {
    var id = a.getAttribute('href').slice(1);
    var h = id && document.getElementById(id);
    if (h) map[id] = a;
  });
  var headings = Object.keys(map).map(function (id) { return document.getElementById(id); }).filter(Boolean);
  if (!headings.length) return;

  function setActive(id) {
    links.forEach(function (a) { a.classList.remove('is-active'); });
    var a = map[id];
    if (a) a.classList.add('is-active');
  }

  var visible = {};
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (en) { visible[en.target.id] = en.isIntersecting; });
    // 取视口中第一个标题
    var first = null;
    headings.forEach(function (h) { if (first === null && visible[h.id]) first = h; });
    if (first) setActive(first.id);
  }, { rootMargin: '-72px 0px -65% 0px', threshold: 0 });

  headings.forEach(function (h) { io.observe(h); });
})();

