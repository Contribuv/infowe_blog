/* ═══════════════════════════════════════════════════════════
   拾光 Shiguang · 主题特效系统
   华为光尘粒子 / 液态玻璃高光 / 打字机 / 阅读进度 / 抽屉 / 灯箱 …
   ═══════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  /* ── 工具与降级检测 ── */
  var $  = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };
  var REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var IS_MOBILE = window.matchMedia('(max-width: 640px)').matches;
  var IS_TOUCH = ('ontouchstart' in window) || navigator.maxTouchPoints > 0;
  var THEME_KEY = 'shiguang-theme';

  function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    try { localStorage.setItem(THEME_KEY, theme); } catch (e) { /* 隐私模式忽略 */ }
  }

  /* ═══════════════════════════════════
     1. 明暗切换（localStorage 持久化）
     ═══════════════════════════════════ */
  var themeBtn = $('#sg-theme-toggle');
  if (themeBtn) {
    themeBtn.addEventListener('click', function () {
      var cur = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      setTheme(cur);
    });
  }
  // 跟随系统主题变化（用户未手动设置时才生效）
  try {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function (e) {
      if (localStorage.getItem(THEME_KEY)) return;
      document.documentElement.setAttribute('data-theme', e.matches ? 'dark' : 'light');
    });
  } catch (e) { /* 旧浏览器忽略 */ }

  /* ═══════════════════════════════════
     2. 华为光尘粒子系统（光点 + 连线 + 鼠标电离）
     ═══════════════════════════════════ */
  (function () {
    if (REDUCED || !$('#sg-particles')) return;

    var canvas = $('#sg-particles');
    var ctx = canvas.getContext('2d');
    var W = 0, H = 0, DPR = Math.min(window.devicePixelRatio || 1, 2);
    var particles = [];
    var mouse = { x: -9999, y: -9999 };
    var rafId = null;
    var running = true;

    /** 解析 CSS 变量里的 RGB 字符串：'154, 95, 51' -> [154,95,51] */
    function rgbVar(name) {
      var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
      var m = (v || '').match(/(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/);
      return m ? [parseInt(m[1], 10), parseInt(m[2], 10), parseInt(m[3], 10)] : [160, 95, 51];
    }

    function resize() {
      W = window.innerWidth;
      H = window.innerHeight;
      canvas.width = W * DPR;
      canvas.height = H * DPR;
      canvas.style.width = W + 'px';
      canvas.style.height = H + 'px';
      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
      build();
    }

    function build() {
      particles = [];
      var isSmall = W < 640;
      var count = isSmall
        ? Math.max(16, Math.round(W / 26))        // 移动端粒子减半
        : Math.max(34, Math.min(88, Math.round(W / 15)));
      for (var i = 0; i < count; i++) {
        particles.push({
          x: Math.random() * W,
          y: Math.random() * H,
          vx: (Math.random() - .5) * .7,
          vy: (Math.random() - .5) * .7,
          r: Math.random() * 1.8 + .7,
          a: Math.random() * .35 + .3,
          c: Math.random() < .5 ? 0 : 1   // 0=part-a 1=part-b
        });
      }
    }

    function tick() {
      if (!running) return;
      ctx.clearRect(0, 0, W, H);

      var colA = rgbVar('--part-a');
      var colB = rgbVar('--part-b');
      var LINK = W < 640 ? 0 : 108;   // 移动端不画连线
      var PUSH = 140;                 // 鼠标电离半径

      var i, j, p, q, dx, dy, d2, d, force;

      // 移动 + 边界回弹
      for (i = 0; i < particles.length; i++) {
        p = particles[i];
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < -8) p.x = W + 8; else if (p.x > W + 8) p.x = -8;
        if (p.y < -8) p.y = H + 8; else if (p.y > H + 8) p.y = -8;

        // 鼠标电离：把靠近鼠标的粒子推开
        dx = p.x - mouse.x;
        dy = p.y - mouse.y;
        d2 = dx * dx + dy * dy;
        if (d2 < PUSH * PUSH) {
          d = Math.sqrt(d2) || 1;
          force = (PUSH - d) / PUSH * 1.6;
          p.x += (dx / d) * force;
          p.y += (dy / d) * force;
        }

        var rgb = p.c === 0 ? colA : colB;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(' + rgb.join(', ') + ', ' + p.a + ')';
        ctx.fill();
      }

      // 粒子连线
      if (LINK > 0) {
        ctx.lineWidth = 1;
        for (i = 0; i < particles.length; i++) {
          p = particles[i];
          for (j = i + 1; j < particles.length; j++) {
            q = particles[j];
            dx = p.x - q.x;
            dy = p.y - q.y;
            d2 = dx * dx + dy * dy;
            if (d2 < LINK * LINK) {
              var opac = (1 - d2 / (LINK * LINK)) * .28;
              ctx.strokeStyle = 'rgba(' + colA.join(', ') + ', ' + opac + ')';
              ctx.beginPath();
              ctx.moveTo(p.x, p.y);
              ctx.lineTo(q.x, q.y);
              ctx.stroke();
            }
          }
        }
      }

      rafId = requestAnimationFrame(tick);
    }

    function setMouse(e) {
      mouse.x = e.clientX;
      mouse.y = e.clientY;
    }

    resize();
    if (window.matchMedia('(pointer: fine)').matches) {
      window.addEventListener('mousemove', setMouse, { passive: true });
    }
    window.addEventListener('resize', resize, { passive: true });
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) { running = false; cancelAnimationFrame(rafId); }
      else { running = true; rafId = requestAnimationFrame(tick); }
    });
    rafId = requestAnimationFrame(tick);
  })();

  /* ═══════════════════════════════════
     3. 氛围光斑 + 液态玻璃高光
     ═══════════════════════════════════ */
  (function () {
    // 全局氛围光斑（桌面端），缓动跟随鼠标
    var glow = $('#sg-glow');
    if (glow && !IS_TOUCH && !REDUCED) {
      var tx = -999, ty = -999, gx = -999, gy = -999, raf = null;
      window.addEventListener('mousemove', function (e) {
        tx = e.clientX; ty = e.clientY;
        if (!raf) raf = requestAnimationFrame(step);
      }, { passive: true });
      function step() {
        gx += (tx - gx) * .08;
        gy += (ty - gy) * .08;
        glow.style.transform = 'translate(' + (gx - 230) + 'px,' + (gy - 230) + 'px)';
        raf = Math.abs(tx - gx) > .5 || Math.abs(ty - gy) > .5 ? requestAnimationFrame(step) : null;
      }
    }

    // 液态玻璃高光：CSS 变量 --mx / --my 跟随（事件委托，性能好）
    var shineRoot = document.documentElement;
    document.addEventListener('mousemove', function (e) {
      var t = e.target.closest ? e.target.closest('.sg-hover-shine') : null;
      if (!t) return;
      var r = t.getBoundingClientRect();
      if (!r.width) return;
      t.style.setProperty('--mx', ((e.clientX - r.left) / r.width * 100) + '%');
      t.style.setProperty('--my', ((e.clientY - r.top) / r.height * 100) + '%');
    }, { passive: true });
  })();

  /* ═══════════════════════════════════
     4. 玻璃阅读进度条
     ═══════════════════════════════════ */
  (function () {
    var bar = $('#sg-reading span');
    if (!bar) return;
    var ticking = false;
    function update() {
      var doc = document.documentElement;
      var max = doc.scrollHeight - window.innerHeight;
      var p = max > 0 ? window.scrollY / max : 0;
      bar.style.transform = 'scaleX(' + Math.min(1, Math.max(0, p)) + ')';
      ticking = false;
    }
    window.addEventListener('scroll', function () {
      if (!ticking) { ticking = true; requestAnimationFrame(update); }
    }, { passive: true });
    update();
  })();

  /* ═══════════════════════════════════
     5. 导航滚动变色
     ═══════════════════════════════════ */
  (function () {
    var nav = $('#sg-nav');
    if (!nav) return;
    function onScroll() {
      nav.classList.toggle('sg-nav-scrolled', window.scrollY > 10);
    }
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  })();

  /* ═══════════════════════════════════
     6. 返回顶部
     ═══════════════════════════════════ */
  (function () {
    var btn = $('#sg-backtop');
    if (!btn) return;
    function onScroll() {
      btn.classList.toggle('show', window.scrollY > 420);
    }
    window.addEventListener('scroll', onScroll, { passive: true });
    btn.addEventListener('click', function () {
      window.scrollTo({ top: 0, behavior: REDUCED ? 'auto' : 'smooth' });
    });
    onScroll();
  })();

  /* ═══════════════════════════════════
     7. 玻璃抽屉（更多菜单）
     ═══════════════════════════════════ */
  (function () {
    var drawer = $('#sg-drawer');
    if (!drawer) return;
    var openers = ['#sg-more-btn', '#sg-tab-more'].map(function (s) { return $(s); }).filter(Boolean);
    var closer = $('#sg-drawer-close');

    function open() {
      drawer.classList.add('open');
      drawer.setAttribute('aria-hidden', 'false');
    }
    function close() {
      drawer.classList.remove('open');
      drawer.setAttribute('aria-hidden', 'true');
    }
    openers.forEach(function (el) { el.addEventListener('click', open); });
    if (closer) closer.addEventListener('click', close);
    drawer.addEventListener('click', function (e) {
      if (e.target === drawer) close();   // 点击遮罩关闭
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') close();
    });
  })();

  /* ═══════════════════════════════════
     8. 滚动入场动画（.sg-reveal → .sg-in）
     ═══════════════════════════════════ */
  (function () {
    var els = $$('.sg-reveal');
    var html = document.documentElement;
    if (!els.length) return;
    // 无 IO / 减少动效：直接显示（加 sg-no-anim，避开隐藏态）
    if (REDUCED || !('IntersectionObserver' in window)) {
      html.classList.add('sg-no-anim');
      return;
    }
    // JS 就绪，允许 CSS 初始隐藏；首屏元素立即点亮，避免刷新时刻的错位/闪烁
    html.classList.add('sg-js');
    function revealVisible() {
      $$('.sg-reveal:not(.sg-in)').forEach(function (el) {
        var r = el.getBoundingClientRect();
        if (r.top < window.innerHeight * .92) el.classList.add('sg-in');
      });
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) {
          en.target.classList.add('sg-in');
          io.unobserve(en.target);
        }
      });
    }, { threshold: .12, rootMargin: '0px 0px -6% 0px' });
    els.forEach(function (el) { io.observe(el); });
    // 首帧立即让首屏元素亮起
    requestAnimationFrame(revealVisible);
    // 兜底：load 后再扫一遍（处理加载慢、滚动恢复等时序）
    window.addEventListener('load', revealVisible);
  })();

  /* ═══════════════════════════════════
     9. 首页打字机（开朗大叔的碎碎念）
     ═══════════════════════════════════ */
  (function () {
    var typeEl = $('#sg-type');
    if (!typeEl || REDUCED) return;
    var SENTENCES = [
      '四十岁，一个人，也把日子过成了一本书',
      '一杯茶，一台电脑，一段不赶路的时光',
      '独居的夜里，键盘声比窗外更热闹',
      '写着写着，就老了；老着老着，就笑了',
      '独处不是孤独，是和世界和平相处'
    ];
    var text = SENTENCES[Math.floor(Math.random() * SENTENCES.length)];
    var i = 0;
    var speed = 95;
    function type() {
      if (i <= text.length) {
        typeEl.textContent = text.slice(0, i);
        i++;
        setTimeout(type, speed);
      }
    }
    // 等首屏入场动画完成再开始打字
    setTimeout(type, 500);
  })();

  /* ═══════════════════════════════════
     10. 统计数字滚动动画（.sg-stat-num[data-count]）
     ═══════════════════════════════════ */
  (function () {
    if (REDUCED || !('IntersectionObserver' in window)) return;
    var nums = $$('.sg-stat-num[data-count]');
    if (!nums.length) return;
    function countUp(el) {
      var target = parseInt(el.getAttribute('data-count'), 10) || 0;
      var suffix = el.getAttribute('data-suffix') || '';
      var dur = 1200;
      var start = null;
      function step(ts) {
        if (!start) start = ts;
        var p = Math.min(1, (ts - start) / dur);
        var ease = 1 - Math.pow(1 - p, 3);
        el.textContent = Math.round(target * ease) + suffix;
        if (p < 1) requestAnimationFrame(step);
      }
      requestAnimationFrame(step);
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) {
          countUp(en.target);
          io.unobserve(en.target);
        }
      });
    }, { threshold: .4 });
    nums.forEach(function (el) { io.observe(el); });
  })();

  /* ═══════════════════════════════════
     11. 文章目录：动态生成 + 滚动高亮（.sg-toc a[href^="#"]）
     ═══════════════════════════════════ */
  (function () {
    var tocNav = $('#sg-toc');
    // 容器为空但存在正文时，扫描 h2/h3 动态生成本页目录
    if (tocNav && !tocNav.children.length) {
      var heads = $$('.sg-paper .markdown-body h2, .sg-paper .markdown-body h3');
      if (heads.length) {
        var html = '';
        heads.forEach(function (h) {
          if (!h.id) return;
          var lvl = h.tagName === 'H2' ? 2 : 3;
          html += '<li><a class="lvl-' + lvl + '" href="#' + h.id + '">' + h.textContent + '</a></li>';
        });
        if (html) {
          tocNav.innerHTML = html;
        } else {
          // 文章没有带 id 的小标题时，收起目录卡，避免留白
          var emptyCard = tocNav.closest('.sg-rail-card');
          if (emptyCard) emptyCard.style.display = 'none';
        }
      }
    }

    var links = $$('.sg-toc a[href^="#"]');
    var targets = [];
    links.forEach(function (a) {
      var id = a.getAttribute('href').slice(1);
      var el = document.getElementById(id);
      if (el) targets.push({ link: a, el: el });
    });
    if (!targets.length) return;

    function highlight() {
      var pos = window.scrollY + window.innerHeight * .28;
      var cur = null;
      targets.forEach(function (t) {
        if (t.el.offsetTop <= pos) cur = t;
      });
      if (cur) {
        links.forEach(function (a) { a.classList.remove('is-active'); });
        cur.link.classList.add('is-active');
      }
    }
    var ticking = false;
    window.addEventListener('scroll', function () {
      if (!ticking) { ticking = true; requestAnimationFrame(function () { highlight(); ticking = false; }); }
    }, { passive: true });
    highlight();
  })();

  /* ═══════════════════════════════════
     12. 图片灯箱（惰性创建 DOM）
     ═══════════════════════════════════ */
  (function () {
    var lb = null;
    var imgs = [];
    var current = -1;

    function ensureLb() {
      if (lb) return;
      lb = document.createElement('div');
      lb.className = 'sg-lightbox';
      lb.style.position = 'fixed';
      lb.setAttribute('role', 'dialog');
      lb.innerHTML =
        '<img class="sg-lb-img" alt="">' +
        '<button class="sg-lb-btn sg-lb-prev" aria-label="上一张">‹</button>' +
        '<button class="sg-lb-btn sg-lb-next" aria-label="下一张">›</button>' +
        '<button class="sg-lb-close" aria-label="关闭">×</button>' +
        '<div class="sg-lb-count"></div>';
      document.body.appendChild(lb);

      function show(i) {
        if (i < 0 || i >= imgs.length) return;
        current = i;
        var img = lb.querySelector('.sg-lb-img');
        img.src = imgs[i].currentSrc || imgs[i].src;
        img.alt = imgs[i].alt || '';
        lb.querySelector('.sg-lb-count').textContent = (i + 1) + ' / ' + imgs.length;
      }
      lb.addEventListener('click', function (e) {
        if (e.target === lb) close();
      });
      lb.querySelector('.sg-lb-close').addEventListener('click', close);
      lb.querySelector('.sg-lb-prev').addEventListener('click', function () { show(current - 1); });
      lb.querySelector('.sg-lb-next').addEventListener('click', function () { show(current + 1); });

      // 键盘操作
      function onKey(e) {
        if (!lb.classList.contains('open')) return;
        if (e.key === 'Escape') close();
        else if (e.key === 'ArrowLeft') show(current - 1);
        else if (e.key === 'ArrowRight') show(current + 1);
      }
      document.addEventListener('keydown', onKey);

      // 触屏滑动切换
      var sx = 0;
      lb.addEventListener('touchstart', function (e) { sx = e.touches[0].clientX; }, { passive: true });
      lb.addEventListener('touchend', function (e) {
        var dx = e.changedTouches[0].clientX - sx;
        if (Math.abs(dx) > 48) show(dx < 0 ? current + 1 : current - 1);
      }, { passive: true });

      function close() {
        lb.classList.remove('open');
        lb.setAttribute('aria-hidden', 'true');
      }
    }

    function collect() {
      imgs = $$('.markdown-body img').filter(function (img) {
        return !img.closest('pre') && (img.currentSrc || img.src);
      });
    }

    document.addEventListener('click', function (e) {
      var img = e.target.closest ? e.target.closest('.markdown-body img') : null;
      if (!img || img.closest('pre')) return;
      ensureLb();
      collect();
      var idx = imgs.indexOf(img);
      if (idx < 0) return;
      current = idx;
      lb.querySelector('.sg-lb-img').src = img.currentSrc || img.src;
      lb.querySelector('.sg-lb-img').alt = img.alt || '';
      lb.querySelector('.sg-lb-count').textContent = (idx + 1) + ' / ' + imgs.length;
      lb.classList.add('open');
      lb.setAttribute('aria-hidden', 'false');
    });

    // 防止图片原生拖拽
    document.addEventListener('dragover', function (e) { e.preventDefault(); }, { passive: false });
  })();

  /* ═══════════════════════════════════
     13. 技能进度条动画（.sg-skill-fill[data-anim-skill]）
     ═══════════════════════════════════ */
  (function () {
    if (REDUCED || !('IntersectionObserver' in window)) return;
    var fills = $$('.sg-skill-fill[data-anim-skill]');
    if (!fills.length) return;
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) {
          var v = parseFloat(en.target.getAttribute('data-anim-skill'));
          en.target.style.width = (isNaN(v) ? 0 : v) + '%';
          io.unobserve(en.target);
        }
      });
    }, { threshold: .3 });
    fills.forEach(function (el) { io.observe(el); });
  })();

  /* ═══════════════════════════════════
     14. 媒体包裹（iframe/video 16:9 自适应）
     ═══════════════════════════════════ */
  (function () {
    $$('.markdown-body iframe, .markdown-body video').forEach(function (el) {
      if (!el.closest('.media-wrap')) {
        var wrap = document.createElement('div');
        wrap.className = 'media-wrap';
        el.parentNode.insertBefore(wrap, el);
        wrap.appendChild(el);
      }
    });
  })();

  /* ═══════════════════════════════════
     15. Hero 搜索清除按钮
     ═══════════════════════════════════ */
  (function () {
    var clearBtn = $('.sg-search-clear');
    var input = $('.sg-hero-search input');
    if (clearBtn && input) {
      clearBtn.addEventListener('click', function () {
        input.value = '';
        input.focus();
      });
    }
  })();

  /* ═══════════════════════════════════
     16. 文章浏览计数（停留满 5 秒上报一次）
     ═══════════════════════════════════ */
  (function () {
    var paper = $('[data-post-id]');
    if (!paper) return;
    var postId = paper.getAttribute('data-post-id');
    var key = 'post_viewed_' + postId;
    if (sessionStorage.getItem(key)) return;
    var acc = 0;
    var timer = setInterval(function () {
      if (document.hidden) return;
      acc += 1000;
      if (acc >= 5000) {
        clearInterval(timer);
        sessionStorage.setItem(key, '1');
        var url = '/post/' + postId + '/view';
        try { fetch(url, { method: 'POST', keepalive: true }); }
        catch (e) { if (navigator.sendBeacon) navigator.sendBeacon(url); }
      }
    }, 1000);
  })();

  /* ═══════════════════════════════════
     17. 状态页轮询 /api/status（每 60 秒）
     ═══════════════════════════════════ */
  (function () {
    if (!$('[data-svc-name]') && !$('[data-expiry-key]')) return;
    var pad = function (n) { return n < 10 ? '0' + n : '' + n; };
    function fmtTime(ts) {
      if (!ts) return '待探测';
      var diff = (Date.now() - ts * 1000) / 1000;
      if (diff < 60) return '刚刚';
      if (diff < 3600) return Math.floor(diff / 60) + ' 分钟前';
      if (diff < 86400) return Math.floor(diff / 3600) + ' 小时前';
      var d = new Date(ts * 1000);
      return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
        ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
    }
    function render(expiry, services, generatedAt) {
      $$('.sg-svc-row[data-svc-name]').forEach(function (row) {
        var name = row.getAttribute('data-svc-name');
        var svc = null;
        for (var i = 0; i < services.length; i++) {
          if (services[i].name === name) { svc = services[i]; break; }
        }
        if (!svc) return;
        var dot = row.querySelector('.sg-svc-dot');
        if (dot) {
          dot.classList.remove('st-ok', 'st-warn', 'st-down', 'st-none');
          dot.classList.add(svc.ok === true ? 'st-ok' : (svc.ok === false ? 'st-down' : 'st-none'));
        }
        var lat = row.querySelector('[data-field="latency"]');
        if (lat) lat.textContent = (svc.latency_ms != null) ? (svc.latency_ms + ' ms') : '—';
        var cert = row.querySelector('[data-field="cert"]');
        if (cert) cert.textContent = (svc.cert_days != null && svc.cert_days >= 0) ? (svc.cert_days + ' 天') : '—';
        var upt = row.querySelector('[data-field="uptime"]');
        if (upt) upt.textContent = (svc.uptime != null) ? (svc.uptime + '%') : '—';
      });

      var online = 0;
      services.forEach(function (s) { if (s.ok === true) online++; });
      var countEl = $('#svc-count');
      if (countEl && services.length) countEl.textContent = online + '/' + services.length + ' 在线';

      if (expiry) {
        $$('[data-expiry-key]').forEach(function (row) {
          var info = expiry[row.getAttribute('data-expiry-key')];
          if (!info) return;
          var st = info.status || 'none';
          ['ok', 'warn', 'expired', 'down', 'none'].forEach(function (c) { row.classList.remove('st-' + c); });
          row.classList.add('st-' + st);
          var dot = row.querySelector('.sg-svc-dot');
          if (dot) {
            ['ok', 'warn', 'expired', 'down', 'none'].forEach(function (c) { dot.classList.remove('st-' + c); });
            dot.classList.add('st-' + st);
          }
          var dateEl = row.querySelector('[data-expiry-field="date"]');
          if (dateEl) dateEl.textContent = info.expiry || '—';
          var badgeEl = row.querySelector('[data-expiry-field="badge"]');
          if (badgeEl) {
            badgeEl.classList.remove('st-ok', 'st-warn', 'st-expired', 'st-down', 'st-none');
            badgeEl.classList.add('st-' + st);
            badgeEl.textContent = st === 'ok' ? '正常'
              : (st === 'warn' ? '即将到期' : (st === 'expired' ? '已到期' : '未配置'));
          }
        });
      }

      var hint = $('#status-hint');
      if (hint && generatedAt) {
        hint.textContent = '数据每 5 分钟自动探测 · 最近更新 ' + fmtTime(generatedAt) + ' · 页面每 60 秒自动刷新';
      }
    }
    function poll() {
      fetch('/api/status', { cache: 'no-store' })
        .then(function (r) { return r.json(); })
        .then(function (data) { render(data.expiry || {}, data.services || [], data.generated_at); })
        .catch(function () { /* 静默失败，等下一轮 */ });
    }
    setTimeout(poll, 1000);
    setInterval(poll, 60000);
  })();
})();