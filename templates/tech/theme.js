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
    window.addEventListener('scroll', function () {
      topBtn.classList.toggle('show', window.scrollY > 400);
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

