/* tech 主题交互：主题切换、移动端抽屉菜单、回到顶部
版权 © 2023-2024 haozi
联系邮箱：site023@qq.com | 开源项目 商业请联系 */
(function () {
  'use strict';

  /* 品牌提示：与 default 主题（static/js/main.js）一致，控制台可见 */
  console.log('%c infowe.site %c 豪子 - 工作机会 VX：CQGGTF ',
    'background:linear-gradient(135deg,#00d4ff,#a855f7);color:#fff;padding:4px 8px;border-radius:4px;font-weight:bold;',
    'color:#00d4ff;');

  /* ── 身份状态兜底 ──
     页面 HTML 里的博主入口（抽屉「编辑本文」）、评论身份条、通知角标都是服务端
     渲染的，以下几种情况会拿到旧快照：
       1) bfcache 恢复（按后退/前进）；
       2) 后台标签页退出登录后切回前台；
       3) 浏览器直接命中了旧的 HTTP 缓存。
     统一做法：拿 /api/identity 和页面上的 data-admin 比对，不一致就重载一次。
     加 10 秒防抖，避免服务端与接口短暂不一致时反复刷新。 */
  var identityBody = document.body;
  var IDENTITY_RELOAD_KEY = 'cmt_identity_reload_at';

  function identityReloadAllowed() {
    var last = 0;
    try { last = Number(sessionStorage.getItem(IDENTITY_RELOAD_KEY) || 0); } catch (e) {}
    if (Date.now() - last < 10000) return false;
    try { sessionStorage.setItem(IDENTITY_RELOAD_KEY, String(Date.now())); } catch (e) {}
    return true;
  }

  function syncAdminIdentity() {
    if (!identityBody) return;
    if (document.visibilityState === 'hidden') return;
    var mine = identityBody.getAttribute('data-admin') === '1';
    fetch('/api/identity', { credentials: 'same-origin', cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || !!d.admin === mine) return;
        if (identityReloadAllowed()) window.location.reload();
      })
      .catch(function () {});
  }

  document.addEventListener('visibilitychange', syncAdminIdentity);
  window.addEventListener('focus', syncAdminIdentity);
  window.addEventListener('pageshow', function (e) {
    if (e.persisted) {
      if (identityReloadAllowed()) window.location.reload();
      return;
    }
    syncAdminIdentity();
  });

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
    var _cmtJump = document.getElementById('tech-comments-jump');
    var _cmtSection = document.getElementById('comments');
    var _scrollTick = false;
    var _lastY = window.scrollY || document.documentElement.scrollTop;
    var _dir = 'down';

    function syncFloating() {
      var y = window.scrollY || document.documentElement.scrollTop;
      var mobile = window.matchMedia('(max-width: 768px)').matches;
      // 移动端方向以手指为准（见下面的 touchmove），桌面端才用滚动增量
      if (!mobile) {
        var delta = y - _lastY;
        if (Math.abs(delta) >= 4) _dir = delta > 0 ? 'down' : 'up';
      }
      _lastY = y;
      var cmtReached = !!_cmtSection &&
        _cmtSection.getBoundingClientRect().top < window.innerHeight * 0.6;
      if (mobile && !(_cmtJump && _cmtSection)) {
        // 没有评论区可跳（首页、列表页等）：只保留回到顶部，按常规时机出现
        topBtn.classList.toggle('show', y > 320);
      } else if (mobile) {
        if (y < 160) {
          topBtn.classList.remove('show');
          if (_cmtJump) _cmtJump.classList.remove('show');
        } else if (cmtReached || _dir === 'up') {
          // 向上滑或已到评论区：显示回顶部
          topBtn.classList.add('show');
          if (_cmtJump) _cmtJump.classList.remove('show');
        } else {
          // 向下滑且评论还在下方：显示跳到评论
          topBtn.classList.remove('show');
          if (_cmtJump) _cmtJump.classList.add('show');
        }
      } else {
        // 桌面空间足够，评论到达前保持两个
        topBtn.classList.toggle('show', y > 320);
        if (_cmtJump) _cmtJump.classList.toggle('show', !cmtReached);
      }
      _scrollTick = false;
    }

    window.addEventListener('scroll', function () {
      if (_scrollTick) return;
      _scrollTick = true;
      requestAnimationFrame(syncFloating);
    }, { passive: true });

    /* 移动端用手指方向判断，避免懒加载图片撑高页面时 scrollY 跳动把方向判反 */
    var _touchStartY = 0;
    window.addEventListener('touchstart', function (e) {
      if (e.touches.length === 1) _touchStartY = e.touches[0].clientY;
    }, { passive: true });
    window.addEventListener('touchmove', function (e) {
      if (e.touches.length !== 1) return;
      var dy = e.touches[0].clientY - _touchStartY;
      if (Math.abs(dy) < 12) return;
      // 手指上移 = 页面往下走 = 显示跳到评论；手指下移 = 显示回到顶部
      _dir = dy < 0 ? 'down' : 'up';
      _touchStartY = e.touches[0].clientY;
      syncFloating();
    }, { passive: true });
    topBtn.addEventListener('click', function () {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
    window.dispatchEvent(new Event('scroll'));
  }
})();

/* ── 首页终端格言：本地句子库（FALLBACK 数组），逐字输出 ── */
(function () {
  'use strict';
  var quoteText = document.getElementById('tech-quote-text');
  if (!quoteText) return; // 该区块仅首页渲染，其它页面直接跳过

  var srcEl = document.getElementById('tech-quote-src');

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

  var rafId = 0;
  var tailTimer = 0;
  var MAX_LEN = 300; // 仅防极端长文；展示上最多两行，超出由 CSS 省略
  var lastIndex = -1;

  function clearTimers() {
    if (rafId) { cancelAnimationFrame(rafId); rafId = 0; }
    if (tailTimer) { clearTimeout(tailTimer); tailTimer = 0; }
  }

  /* 逐字打字输出：rAF + 时间轴驱动，而非 setInterval 定时器。
     setInterval 精度差且会漂移（后台标签页被节流、嵌套定时器有最小延迟
     钳制），字符出现忽快忽慢，观感就是"帧数低/卡顿"。rAF 随屏幕刷新率
     （60/120Hz）回调，按已过时间换算应显示字数，出字节奏精确平滑。 */
  function typeQuote(text, src) {
    clearTimers();
    srcEl.textContent = '';
    quoteText.textContent = '';
    var chars = Array.from(String(text || '').slice(0, MAX_LEN));
    if (!chars.length) return;
    var cps = chars.length > 60 ? 29 : 17; // 字符/秒（对应原 34ms、60ms 每字）
    var startedAt = 0;
    var shown = 0;
    function tick(now) {
      if (!startedAt) startedAt = now;
      var target = Math.min(chars.length, Math.floor((now - startedAt) / 1000 * cps));
      if (target > shown) {
        shown = target;
        quoteText.textContent = chars.slice(0, shown).join('');
      }
      if (shown >= chars.length) {
        if (src) tailTimer = setTimeout(function () { srcEl.textContent = src; }, 260);
        return;
      }
      rafId = requestAnimationFrame(tick);
    }
    rafId = requestAnimationFrame(tick);
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

  /* 首页一言只负责展示：刷新按钮和打字光标已移除，避免破坏居中与重复站标光标 */
  renderLocal();
})();

/* ── 代码块语法高亮：文章正文与项目 README 共用 ──
   highlight.min.js 以 defer 加载，模板内联脚本执行时可能还没就绪；
   这里统一等 DOMContentLoaded 后再高亮。
   注意：不认识的块一律按纯文本处理，绝不交给自动识别——
   目录树、ASCII 流程图会被猜成 C#/Bash，反而制造出错误颜色。 */
var TECH_LANG_ALIAS = { dockerignore: 'dockerfile' };

function techHighlightCode(root) {
  if (!root) return;
  var hljs = window.hljs;
  if (!hljs || typeof hljs.highlightElement !== 'function') return;
  var blocks = root.querySelectorAll('pre code');
  for (var i = 0; i < blocks.length; i++) {
    var block = blocks[i];
    if (block.dataset && block.dataset.highlighted === 'yes') continue;
    var match = (block.className || '').match(/\blanguage-([\w+#.-]+)/);
    var lang = match ? match[1].toLowerCase() : '';
    if (TECH_LANG_ALIAS[lang]) lang = TECH_LANG_ALIAS[lang];
    var known = false;
    if (lang) {
      try { known = !!hljs.getLanguage(lang); } catch (e) { known = false; }
    }
    if (!known) {
      // 未标注语言 / hljs 不认识（text、txt 也走这里）：统一换成 plaintext
      if (match) block.classList.remove('language-' + match[1]);
      block.classList.add('language-plaintext');
    } else if (lang !== match[1].toLowerCase()) {
      // 别名替换（dockerignore），让 highlightElement 拿到真正的语言名
      block.classList.remove('language-' + match[1]);
      block.classList.add('language-' + lang);
    }
    try { hljs.highlightElement(block); } catch (e) {}
  }
}
window.techHighlightCode = techHighlightCode;

/* 页面加载后自动处理文章/项目正文，模板无需重复绑定 */
(function () {
  function run() {
    techHighlightCode(document.querySelector('.tech-post-body'));
    techHighlightCode(document.querySelector('.tech-proj-readme-body'));
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', run);
  } else {
    run();
  }
})();

/* ── 全局搜索：屏幕居中浮窗（遮罩点击 / Esc / 焦点与滚动锁定） ── */
(function () {
  'use strict';
  var openBtn = document.getElementById('tech-search-open');
  var layer = document.getElementById('tech-search-layer');
  var closeBtn = document.getElementById('tech-search-close');
  var input = document.getElementById('tech-search-input');
  if (!openBtn || !layer) return;

  var prevOverflow = '';

  function isOpen() { return layer.classList.contains('open'); }

  function setOpen(open) {
    if (open === isOpen()) return;
    if (open) {
      // 抽屉与搜索遮罩不同时出现，先关抽屉，避免两个 body 滚动锁互相覆盖
      var drawerOverlay = document.getElementById('tech-drawer-overlay');
      if (drawerOverlay && drawerOverlay.classList.contains('open')) drawerOverlay.click();
      prevOverflow = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
      layer.classList.add('open');
      layer.setAttribute('aria-hidden', 'false');
      openBtn.setAttribute('aria-expanded', 'true');
      if (input) {
        setTimeout(function () { if (isOpen()) { input.focus(); input.select(); } }, 0);
        requestAnimationFrame(function () {
          if (isOpen() && document.activeElement !== input) input.focus();
        });
      }
    } else {
      layer.classList.remove('open');
      layer.setAttribute('aria-hidden', 'true');
      openBtn.setAttribute('aria-expanded', 'false');
      document.body.style.overflow = prevOverflow;
      openBtn.focus();
    }
  }

  openBtn.addEventListener('click', function () { setOpen(!isOpen()); });
  if (closeBtn) closeBtn.addEventListener('click', function () { setOpen(false); });
  // 点对话框之外的遮罩区域关闭
  layer.addEventListener('click', function (e) { if (e.target === layer) setOpen(false); });
  document.addEventListener('click', function (e) {
    if (isOpen() && !openBtn.contains(e.target) && !layer.contains(e.target)) setOpen(false);
  });
  document.addEventListener('keydown', function (e) {
    if (!isOpen()) return;
    if (e.key === 'Escape') { e.preventDefault(); setOpen(false); return; }
    if (e.key !== 'Tab') return;
    // 焦点锁在浮窗内，避免 Tab 跑到被遮罩挡住的页面元素
    var f = layer.querySelectorAll('input, button, [href], [tabindex]:not([tabindex="-1"])');
    if (!f.length) return;
    var first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });
})();

/* ── 文章目录：点击平滑滚动 + 滚动时高亮当前章节 ── */
(function () {
  var tocBody = document.querySelector('.tech-toc-body');
  // 文章页正文是 .tech-post-body，项目页是 .tech-proj-readme-body；
  // 之前只认前者，项目页整个 TOC 逻辑直接 return，点击退回浏览器默认锚点，
  // 而 README 图片懒加载会让页面高度从 1800 瞬间涨到 1 万，锚点就被顶到页面底部。
  var content = document.querySelector('.tech-post-body, .tech-proj-readme-body');
  if (!tocBody || !content) return;

  function settleScroll(target) {
    // README 图片是懒加载的，点击后图片开始下载会把页面高度撑大，
    // 目标位置一直在变。这里连续几帧跟着目标走，直到它稳定（或 3 秒）。
    var root = document.documentElement;
    var prevBehavior = root.style.scrollBehavior;
    root.style.scrollBehavior = 'auto';
    var cancelled = false;
    var stop = function () { cancelled = true; };
    window.addEventListener('wheel', stop, { once: true, passive: true });
    window.addEventListener('touchstart', stop, { once: true, passive: true });
    var tries = 0, lastTop = null, stable = 0;
    var tick = function () {
      if (cancelled) {
        root.style.scrollBehavior = prevBehavior;
        return;
      }
      var top = Math.max(0, target.getBoundingClientRect().top + window.scrollY - 60);
      window.scrollTo(0, top);
      // scrollTo 会被页面最大滚动距离截断（懒加载图片撑高前，目标 docTop
      // 几乎总在 maxScroll 之后）。未真正到达目标时不能计入"稳定"，
      // 否则前几帧就停在旧页面底部，图片加载完也不再追，表现为"点目录到底部"。
      var reached = Math.abs(window.scrollY - top) < 2;
      if (reached && lastTop !== null && Math.abs(top - lastTop) < 2) stable++;
      else stable = 0;
      lastTop = top;
      tries++;
      if (stable < 3 && tries < 180) {
        requestAnimationFrame(tick);
      } else {
        root.style.scrollBehavior = prevBehavior;
      }
    };
    requestAnimationFrame(tick);
  }

  // 手写目录（文章 Markdown 里的「## 目录」）链接与渲染器生成的标题 id
  // 常常对不上：如「#14-★-实战逆向…」vs 实际 id「14-实战逆向-…」（★ 被
  // 去掉、分词连字符不同）。直接 id 找不到时，把两边归一化（去掉符号、
  // 小写）后在正文标题里兜底匹配，避免锚点悬空导致原生跳转乱滑。
  function findTarget(id) {
    var el = document.getElementById(id);
    if (el) return el;
    var norm = id.toLowerCase().replace(/[^0-9a-z\u4e00-\u9fff]+/g, '');
    if (!norm) return null;
    var hs = content.querySelectorAll('h1, h2, h3, h4');
    for (var i = 0; i < hs.length; i++) {
      var hid = hs[i].id || '';
      if (hid.toLowerCase().replace(/[^0-9a-z\u4e00-\u9fff]+/g, '') === norm) return hs[i];
    }
    return null;
  }

  // 点击委托：拦截 #id 锚点，改用逐帧对齐（点完即关；桌面/移动都收起 TOC）。
  // 除侧边栏 TOC 外，正文里 Markdown 目录（「## 目录」渲染的 <ol>）的锚点
  // 也要拦截：原生锚点跳转只在点击瞬间对齐一次，随后懒加载图片把页面
  // 撑高，目标被顶下去，最终停在页面底部。
  function onAnchorClick(e) {
    var a = e.target.closest && e.target.closest('a[href^="#"]');
    if (!a) return;
    var id = a.getAttribute('href').slice(1);
    var target = id && findTarget(id);
    if (!target) return;
    e.preventDefault();
    var details = a.closest('details');
    // 移动端目录是底部抽屉（details.open 必须常开，靠面板类名控制显隐），
    // 这里若把 open 置 false，抽屉内容会直接消失；桌面/平板仍保持点完即收起
    if (details && !window.matchMedia('(max-width: 767px)').matches) details.open = false;
    // 先把待加载的图改成 eager，让页面高度尽快稳定
    Array.prototype.forEach.call(content.querySelectorAll('img'), function (img) {
      if (!img.complete) img.loading = 'eager';
    });
    settleScroll(target);
    history.replaceState(null, '', '#' + id);
  }
  tocBody.addEventListener('click', onAnchorClick);
  // 正文容器：目录通常在正文头部，一个委托即可覆盖所有文内锚点
  content.addEventListener('click', onAnchorClick);

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
    links.forEach(function (a) {
      a.classList.remove('is-active');
      a.removeAttribute('aria-current');
    });
    var a = map[id];
    if (!a) return;
    a.classList.add('is-active');
    // 读屏用户也需要知道当前章节；location 比 true 更贴合目录的语义
    a.setAttribute('aria-current', 'location');
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

/* ── 移动端目录浮窗（< 768px）：悬浮入口 + 底部抽屉 ──
   结构由 JS 注入：入口按钮、遮罩、抽屉头部（把手 / 标题 / 节数 / 关闭）。
   桌面与平板（768~1399px）保持原有内联折叠，≥1400px 固定侧栏不变；
   只有 html.toc-sheet-ready 存在时 CSS 才接管移动端布局，JS 失效也不丢功能。 */
(function () {
  'use strict';
  var aside = document.querySelector('.tech-toc-sidebar');
  var details = aside && aside.querySelector('details.tech-toc');
  var body = aside && aside.querySelector('.tech-toc-body');
  if (!aside || !details || !body) return;
  var links = body.querySelectorAll('a[href^="#"]');
  if (!links.length) return;

  /* 窄屏（768~1399）折叠摘要右侧的「共 N 节」：
     摘要本身是 details/summary，节数无法用 CSS 统计，这里注入一次。
     ≥1400 与 <768 都由 CSS 隐藏，不影响固定侧栏和抽屉头部。 */
  var summary = details.querySelector('.tech-toc-summary');
  if (summary && !summary.querySelector('.tech-toc-count')) {
    var count = document.createElement('span');
    count.className = 'tech-toc-count';
    count.textContent = '共 ' + links.length + ' 节';
    summary.appendChild(count);
  }

  var root = document.documentElement;
  var mq = window.matchMedia('(max-width: 767px)');
  var isOpen = false;
  var lastFocus = null;

  /* 抽屉头部：把手 + 标题 + 节数 + 关闭 */
  var head = document.createElement('div');
  head.className = 'tech-toc-sheet-head';
  head.innerHTML =
    '<span class="tech-toc-grip" aria-hidden="true"></span>' +
    '<div class="tech-toc-sheet-bar">' +
      '<span class="tech-toc-sheet-title">目录</span>' +
      '<span class="tech-toc-sheet-count">共 ' + links.length + ' 节</span>' +
      '<button type="button" class="tech-toc-close" aria-label="关闭目录">' +
        '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>' +
      '</button>' +
    '</div>';
  aside.insertBefore(head, aside.firstChild);
  aside.id = 'tech-toc-sheet';
  var closeBtn = head.querySelector('.tech-toc-close');

  /* 入口条：插在 aside 之前（标题卡内、正文之前），不占屏幕角落，
     与评论区浮窗按钮互不影响 */
  var trigger = document.createElement('button');
  trigger.type = 'button';
  trigger.className = 'tech-toc-trigger';
  trigger.setAttribute('aria-label', '打开文章目录');
  trigger.setAttribute('aria-controls', 'tech-toc-sheet');
  trigger.setAttribute('aria-expanded', 'false');
  trigger.innerHTML =
    '<svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 7h16M4 12h10M4 17h16"/></svg>' +
    '<span class="tech-toc-trigger-label">目录</span>' +
    '<span class="tech-toc-trigger-count">共 ' + links.length + ' 节</span>' +
    '<svg class="tech-toc-trigger-chevron" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>';
  aside.parentNode.insertBefore(trigger, aside);

  var scrim = document.createElement('div');
  scrim.className = 'tech-toc-scrim';
  document.body.appendChild(scrim);

  /* 打开时把当前章节滚进可视区；只动抽屉容器，不带动整页 */
  function revealActive() {
    var a = body.querySelector('a.is-active');
    if (!a || body.scrollHeight <= body.clientHeight + 1) return;
    var ar = a.getBoundingClientRect();
    var br = body.getBoundingClientRect();
    if (ar.top < br.top + 8) body.scrollTop += ar.top - br.top - 8;
    else if (ar.bottom > br.bottom - 8) body.scrollTop += ar.bottom - br.bottom + 8;
  }

  function openSheet() {
    if (!mq.matches) return;
    details.open = true;   // 抽屉内容不依赖原生折叠
    isOpen = true;
    lastFocus = document.activeElement;
    aside.classList.add('is-open');
    scrim.classList.add('is-open');
    root.classList.add('toc-sheet-open');
    trigger.setAttribute('aria-expanded', 'true');
    aside.setAttribute('role', 'dialog');
    aside.setAttribute('aria-modal', 'true');
    revealActive();
    try { closeBtn.focus({ preventScroll: true }); } catch (err) { closeBtn.focus(); }
  }

  function closeSheet() {
    if (!isOpen) return;
    isOpen = false;
    aside.classList.remove('is-open');
    scrim.classList.remove('is-open');
    root.classList.remove('toc-sheet-open');
    trigger.setAttribute('aria-expanded', 'false');
    aside.removeAttribute('role');
    aside.removeAttribute('aria-modal');
    // 焦点还给打开前的元素；若当时焦点落在 body（程序化点击等），
    // 退回入口条，避免焦点跑到文档根后键盘用户丢失位置
    var back = (lastFocus && lastFocus.focus && lastFocus !== document.body) ? lastFocus : trigger;
    try { back.focus({ preventScroll: true }); } catch (err) {}
  }

  trigger.addEventListener('click', openSheet);
  scrim.addEventListener('click', closeSheet);
  closeBtn.addEventListener('click', closeSheet);

  /* 抽屉里点章节：滚动交给页面原有锚点逻辑（theme.js 上方），这里只负责收起 */
  body.addEventListener('click', function (e) {
    if (e.target.closest && e.target.closest('a[href^="#"]')) closeSheet();
  });

  document.addEventListener('keydown', function (e) {
    if (!isOpen) return;
    if (e.key === 'Escape') {
      e.preventDefault();
      closeSheet();
      return;
    }
    /* 焦点锁在抽屉内，避免 Tab 跑到被遮罩挡住的页面元素 */
    if (e.key !== 'Tab') return;
    var f = aside.querySelectorAll('a[href], button, [tabindex]:not([tabindex="-1"])');
    if (!f.length) return;
    var first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });

  function sync() {
    if (mq.matches) {
      root.classList.add('toc-sheet-ready');
      details.open = true;   // 抽屉内容不依赖原生折叠
    } else {
      closeSheet();
      root.classList.remove('toc-sheet-ready');
      /* 768~1399 回到「内联折叠」的默认收起；≥1400 由页面内联脚本强制展开 */
      if (!window.matchMedia('(min-width: 1400px)').matches) details.open = false;
    }
  }
  sync();
  mq.addEventListener('change', sync);
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


/* ── 侧栏 sticky 自适应 ──
   侧栏比视口高时（例如开启「最新评论」并设了较多条数），
   若仍以 top:72px 吸附，侧栏下半部分会被永远挡在视口外，页面也「滚不下去」。
   这里量出侧栏高度写到 .tech-home-grid 的 --sidebar-h，
   CSS 用 top: min(72px, 100vh - var(--sidebar-h) - 16px)：
   放得下就正常吸顶；放不下就把吸附点变成负值，
   让侧栏先跟着页面滚到露出底部，再在那里固定。
   刻意不给侧栏加 max-height + overflow-y（那会变成独立滚动容器、吞掉滚轮）。 */
(function () {
  'use strict';
  var bar = document.querySelector('.tech-sidebar');
  if (!bar) return;
  var host = bar.closest('.tech-home-grid') || bar.parentElement;
  if (!host) return;
  var last = 0;
  function sync() {
    var h = Math.round(bar.getBoundingClientRect().height);
    if (h && h !== last) {
      last = h;
      host.style.setProperty('--sidebar-h', h + 'px');
    }
  }
  sync();
  window.addEventListener('resize', sync, { passive: true });
  // 图片加载、字体切换都会改变高度，用 ResizeObserver 兜住
  if (window.ResizeObserver) {
    new ResizeObserver(sync).observe(bar);
  } else {
    window.addEventListener('load', sync);
  }
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
