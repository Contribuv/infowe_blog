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
  var lastFocus = null;

  function openDrawer() {
    lastFocus = document.activeElement;
    overlay.classList.add('open');
    drawer.classList.add('open');
    drawer.setAttribute('aria-hidden', 'false');
    if (burger) burger.setAttribute('aria-expanded', 'true');
    document.body.style.overflow = 'hidden';
    if (closeBtn) {
      closeBtn.focus();
      // 兜底：个别浏览器在 display/visibility 刚切换的同一帧仍拒绝聚焦，
      // 下一帧再试一次（此时 .open 的 visibility 已确定生效）
      if (document.activeElement !== closeBtn) {
        requestAnimationFrame(function () {
          if (drawer.classList.contains('open')) closeBtn.focus();
        });
      }
    }
  }
  function closeDrawer() {
    if (!drawer.classList.contains('open')) return;
    overlay.classList.remove('open');
    drawer.classList.remove('open');
    drawer.setAttribute('aria-hidden', 'true');
    if (burger) burger.setAttribute('aria-expanded', 'false');
    document.body.style.overflow = '';
    // 键盘关闭后焦点回到触发按钮，避免焦点掉到 body
    if (lastFocus && typeof lastFocus.focus === 'function') lastFocus.focus();
    lastFocus = null;
  }

  if (burger && overlay && drawer) {
    burger.addEventListener('click', openDrawer);
    overlay.addEventListener('click', closeDrawer);
    if (closeBtn) closeBtn.addEventListener('click', closeDrawer);
    drawer.querySelectorAll('a').forEach(function (a) {
      a.addEventListener('click', closeDrawer);
    });
    document.addEventListener('keydown', function (e) {
      if (!drawer.classList.contains('open')) return;
      if (e.key === 'Escape') { closeDrawer(); return; }
      // 焦点圈定在抽屉内（简单的 Tab 首尾循环）
      if (e.key !== 'Tab') return;
      var items = drawer.querySelectorAll('a[href], button:not([disabled])');
      if (!items.length) return;
      var first = items[0], last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
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
    /* 移动端：评论表单进入视口时隐藏悬浮按钮，避免遮住「提交评论」（按钮靠右，恰在悬浮球右下位置） */
    var _cmtForm = document.getElementById('comment-form');
    if (_cmtForm && window.matchMedia('(max-width: 768px)').matches && 'IntersectionObserver' in window) {
      var _cmtIO = new IntersectionObserver(function (entries) {
        topBtn.classList.toggle('hide', entries[0].isIntersecting);
      }, { threshold: 0.02 });
      _cmtIO.observe(_cmtForm);
    }
  }
})();

/* ── 首页终端格言：本地句子库（FALLBACK 数组），刷新按钮换下一句 ── */
(function () {
  'use strict';
  var quoteText = document.getElementById('tech-quote-text');
  if (!quoteText) return; // 该区块仅首页渲染，其它页面直接跳过

  var srcEl = document.getElementById('tech-quote-src');
  var refreshBtn = document.getElementById('tech-quote-refresh');

  /* 本地句子库：加载/刷新时先用它，保证弱网与一键旁路下首屏即时出句 */
  var FALLBACK = [
    { text: '学而不思则罔，思而不学则殆。', src: '《论语》' },
    { text: '君子藏器于身，待时而动。', src: '《周易》' },
    { text: '博学之，审问之，慎思之，明辨之，笃行之。', src: '《礼记·中庸》' },
    { text: '把一件事做到极致，胜过平庸地做一万件事。', src: '' },
    { text: '代码如诗：先让它正确，再让它清晰，最后让它简洁。', src: '' },
    { text: '道阻且长，行则将至；行而不辍，未来可期。', src: '' },
    { text: '早优化是万恶之源：先量化，再优化，后庆祝。', src: '' },
    { text: '热爱可抵岁月漫长。', src: '' },
    { text: '流量是入口，房源是底牌；先收住线索，再谈转化。', src: '' },
    { text: '渠道多不是本事，把一条货带出本地成交才是。', src: '' },
    { text: '算法会变，人性不会；做内容先懂人，再猜机器。', src: '' },
    { text: '四十未娶不是异类，是还没遇到值得将就的反面。', src: '' },
    { text: '一个人把日子过明白，比凑合两个人更有分量。', src: '' },
    { text: '自己造轮子不丢人，丢人的是不知道轮子怎么转。', src: '' },
    { text: '开源的意义：省了别人的时间，也逼自己把活做干净。', src: '' },
    { text: '好东西不靠调参堆出来，靠把每条链路都接住。', src: '' },
    { text: '把踩过的坑写下来，下一次就能少走一点弯路。', src: '' },
    { text: '一篇文章只讲清一个问题，读者才记得住。', src: '' },
    { text: '先让它跑起来，再让它跑得优雅。', src: '' },
    { text: '代码会过时，排查问题的方法不会。', src: '' },
    { text: '能稳定复现的问题，才值得写进文章。', src: '' },
    { text: '博客不是作品集，是一份长期维护的公开笔记。', src: '' },
    { text: '先写清楚，再写漂亮。', src: '' },
    { text: '好的文档，是写给三个月后的自己看的。', src: '' },
    { text: '把复杂留给实现，把简单留给读者。', src: '' },
    { text: '线上没有小事，日志里藏着答案。', src: '' },
    { text: '更新日志不是流水账，是项目留下的脚印。', src: '' },
    { text: '比起追新，更重要的是把旧问题讲明白。', src: '' },
    { text: '写作和调试一样，都是不断缩小问题范围。', src: '' },
    { text: '先记录，再整理；先完成，再完美。', src: '' },
    { text: '一个能长期更新的博客，比一次爆款更有价值。', src: '' },
    { text: '把经验写成步骤，下次就不用重新踩坑。', src: '' },
    { text: '文章是代码之外的另一份调试记录。', src: '' },
    { text: '能被搜索到、能被复用的内容，才值得写下来。', src: '' },
    { text: '别急着加功能，先把现有链路跑顺。', src: '' },
    { text: '博客最怕的不是没人看，是连自己都不回看。', src: '' }
  ];

  // 后台「首页一言」有自定义内容时优先使用；留空继续用上面的内置列表
  var quoteData = document.getElementById('tech-quotes-data');
  if (quoteData) {
    try {
      var customQuotes = JSON.parse(quoteData.textContent || '[]');
      if (Array.isArray(customQuotes)) {
        var validQuotes = customQuotes.filter(function (item) {
          return item && typeof item.text === 'string' && item.text.trim();
        }).map(function (item) {
          return { text: item.text.trim(), src: typeof item.src === 'string' ? item.src.trim() : '' };
        });
        if (validQuotes.length) FALLBACK = validQuotes;
      }
    } catch (e) {}
  }

  var timers = [];
  var MAX_LEN = 120;
  var lastIndex = -1;

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
    var index = 0;
    if (FALLBACK.length > 1) {
      do {
        index = Math.floor(Math.random() * FALLBACK.length);
      } while (index === lastIndex);
    }
    lastIndex = index;
    var item = FALLBACK[index];
    typeQuote(item.text, item.src);
  }

  if (refreshBtn) {
    refreshBtn.addEventListener('click', function () {
      refreshBtn.classList.add('spin');
      setTimeout(function () { refreshBtn.classList.remove('spin'); }, 300);
      renderLocal();
    });
  }

  renderLocal();
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

/* ── 文章目录：点击平滑滚动 + 滚动时高亮当前章节 ── */
(function () {
  var tocBody = document.querySelector('.tech-toc-body');
  var content = document.querySelector('.tech-post-body');
  if (!tocBody || !content) return;

  // 点击委托：拦截 #id 锚点，改用平滑滚动 + 点完即关（移动端抽屉式 TOC 必关；桌面端连续浏览也建议收起避免遮挡正文）
  tocBody.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[href^="#"]');
    if (!a) return;
    var id = a.getAttribute('href').slice(1);
    var target = id && document.getElementById(id);
    if (!target) return;
    e.preventDefault();
    // 让外层 <details> 收起：统一行为，桌面/移动都关
    var details = tocBody.closest('details');
    if (details) details.open = false;
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
    if (!a) return;
    a.classList.add('is-active');
    // 长目录（20+ 条）在 60vh 容器里滚动，当前项可能不在视野内：
    // 只调整容器 scrollTop，不能用 scrollIntoView（会带动整页跳动）
    var box = a.closest('.tech-toc-body');
    if (!box || box.scrollHeight <= box.clientHeight + 1) return;
    var ar = a.getBoundingClientRect();
    var br = box.getBoundingClientRect();
    if (ar.top < br.top + 8) box.scrollTop += ar.top - br.top - 8;
    else if (ar.bottom > br.bottom - 8) box.scrollTop += ar.bottom - br.bottom + 8;
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

  // 项目页「反馈」按钮：监听由 base.html 末尾的内联脚本绑定（避开 theme.js IIFE 抛错时的副作用）
})();

/* ── 阅读进度条：页面存在 #readingProgress 时启用（文章页与项目页共用同一份逻辑） ──
   锚点由 data-reading-target 指定（默认文章正文 .tech-post-body）；正文顶部与视口顶部
   对齐时为 0%，正文底部到达视口底部时为 100%。滚动用 rAF 节流，与回到顶部按钮同款。 */
(function () {
  'use strict';
  var bar = document.getElementById('readingProgress');
  if (!bar) return;
  var target = document.querySelector(bar.getAttribute('data-reading-target') || '.tech-post-body');
  if (!target) return;
  var ticking = false;
  function update() {
    ticking = false;
    var rect = target.getBoundingClientRect();
    var total = rect.height - window.innerHeight;
    var scrolled = Math.max(0, -rect.top);
    var pct = total > 0 ? Math.min(100, Math.max(0, (scrolled / total) * 100)) : 0;
    bar.style.width = pct + '%';
  }
  function onScroll() {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(update);
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', update);
  update();
})();


/* ── 友链页「本站信息」点击复制 ──
   点击按钮复制 data-copy 内容（站点地址 / 头像 / 现成 HTML 代码），
   成功后按钮文字短暂切换为「已复制 ✓」。
   https（含 localhost）走 Clipboard API，普通 http 降级 execCommand。 */
(function () {
  'use strict';
  var btns = document.querySelectorAll('.tech-copy[data-copy]');
  if (!btns.length) return;

  function fallbackCopy(text, ok) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); ok(); } catch (e) { /* 剪贴板不可用时静默 */ }
    document.body.removeChild(ta);
  }

  Array.prototype.forEach.call(btns, function (btn) {
    btn.addEventListener('click', function () {
      var text = btn.getAttribute('data-copy');
      var ok = function () {
        if (btn.dataset.label === undefined) btn.dataset.label = btn.textContent;
        btn.textContent = '已复制 ✓';
        btn.classList.add('copied');
        setTimeout(function () {
          btn.textContent = btn.dataset.label;
          btn.classList.remove('copied');
        }, 1500);
      };
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(ok, function () { fallbackCopy(text, ok); });
      } else {
        fallbackCopy(text, ok);
      }
    });
  });
})();