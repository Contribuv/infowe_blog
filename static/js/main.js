/**
 * infowe Blog - 性能优化版
 * 工作推介：VX：CQGGTF
 * 粒子背景 | 鼠标光晕 | 3D卡片 | 打字动画 | 主题切换 | 滚动动画
 */
(function () {
  'use strict';

  /* ============================================
     1. 粒子背景系统 (优化：减少粒子数，Canvas仅视口大小，合并光晕动画)
     ============================================ */
  const canvas = document.getElementById('particle-canvas');
  const cursorGlow = document.getElementById('cursor-glow');

  if (canvas) {
    const ctx = canvas.getContext('2d');
    let w, h, particles = [];
    const PARTICLE_COUNT = 35;  // 80 → 35
    const CONNECT_DIST = 80;    // 120 → 80
    const chars = '01{}[]()<>/\\|*#@$%&;:,.pydef class import return async await lambda'.split(' ');

    // 鼠标位置（合并到同一个动画循环）
    let mouseX = -500, mouseY = -500, glowX = -500, glowY = -500;
    let isDark = true;
    let lastStyleCheck = 0;

    function resize() {
      w = canvas.width = window.innerWidth;
      h = canvas.height = window.innerHeight;  // 仅视口大小，不再是scrollHeight
    }

    // 预分配粒子数组，避免GC
    class Particle {
      constructor() { this.reset(); }
      reset() {
        this.x = Math.random() * w;
        this.y = Math.random() * h;
        this.size = Math.random() * 10 + 6;    // 缩小字体
        this.speedY = Math.random() * 0.4 + 0.15;
        this.speedX = (Math.random() - 0.5) * 0.2;
        this.opacity = Math.random() * 0.25 + 0.04;
        this.char = chars[Math.floor(Math.random() * chars.length)];
        this.isSymbol = this.char.length === 1 && /[{}[\]()<>/\\|*#@$%&;:.,]/.test(this.char);
      }
      update() {
        this.y += this.speedY;
        this.x += this.speedX;
        if (this.y > h + 20) { this.y = -20; this.x = Math.random() * w; }
        if (this.x < -20) this.x = w + 20;
        if (this.x > w + 20) this.x = -20;
      }
      draw() {
        ctx.font = this.size + 'px monospace';
        ctx.fillStyle = this.isSymbol
          ? 'rgba(' + (isDark ? '0,212,255' : '8,145,178') + ',' + (this.opacity * 1.5).toFixed(3) + ')'
          : 'rgba(' + (isDark ? '168,85,247' : '124,58,237') + ',' + this.opacity.toFixed(3) + ')';
        ctx.fillText(this.char, this.x, this.y);
      }
    }

    function initParticles() {
      particles.length = 0;
      for (let i = 0; i < PARTICLE_COUNT; i++) {
        particles[i] = new Particle();
      }
    }

    function updateGlow() {
      // 光晕缓动
      glowX += (mouseX - glowX) * 0.06;
      glowY += (mouseY - glowY) * 0.06;
      if (cursorGlow) {
        cursorGlow.style.transform = 'translate(' + (glowX - 150) + 'px,' + (glowY - 150) + 'px)';
      }
    }

    var animFrameId;
    function animate() {
      ctx.clearRect(0, 0, w, h);

      // 更新+绘制粒子
      for (let i = 0; i < particles.length; i++) {
        particles[i].update();
        particles[i].draw();
      }

      // 连接线（空间哈希粗略优化：只检查距离接近的）
      for (let i = 0; i < particles.length; i++) {
        const pi = particles[i];
        for (let j = i + 1; j < particles.length; j++) {
          const pj = particles[j];
          const dx = pi.x - pj.x;
          const dy = pi.y - pj.y;
          // 快速矩形检查，避免 sqrt
          if (Math.abs(dx) > CONNECT_DIST || Math.abs(dy) > CONNECT_DIST) continue;
          const distSq = dx * dx + dy * dy;
          if (distSq < CONNECT_DIST * CONNECT_DIST) {
            const alpha = (0.05 * (1 - Math.sqrt(distSq) / CONNECT_DIST)).toFixed(3);
            ctx.strokeStyle = 'rgba(' + (isDark ? '0,212,255' : '8,145,178') + ',' + alpha + ')';
            ctx.lineWidth = 0.5;
            ctx.beginPath();
            ctx.moveTo(pi.x, pi.y);
            ctx.lineTo(pj.x, pj.y);
            ctx.stroke();
          }
        }
      }

      // 光晕（合并到同一帧循环）
      updateGlow();

      animFrameId = requestAnimationFrame(animate);
    }

    // 鼠标移动事件
    document.addEventListener('mousemove', function (e) {
      mouseX = e.clientX;
      mouseY = e.clientY;
      if (cursorGlow) cursorGlow.classList.add('visible');
    });
    document.addEventListener('mouseleave', function () {
      if (cursorGlow) cursorGlow.classList.remove('visible');
    });

    // 定期检查主题（降低频率）
    setInterval(function () {
      var theme = document.documentElement.getAttribute('data-theme');
      isDark = theme === 'dark' || !theme;
    }, 500);

    resize();
    initParticles();
    animate();

    // resize 防抖（只更新尺寸，不重建粒子）
    var resizeTimer;
    window.addEventListener('resize', function () {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(function () { resize(); }, 200);
    });

    // 页面不可见时暂停动画
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) {
        if (animFrameId) { cancelAnimationFrame(animFrameId); animFrameId = null; }
      } else {
        if (!animFrameId) animate();
      }
    });
  }

  /* ============================================
     2. 暗色/亮色模式切换
     ============================================ */
  const themeToggle = document.getElementById('theme-toggle');
  if (themeToggle) {
    const saved = localStorage.getItem('infowe-theme');
    // 初始主题由 head 内联脚本已按系统/存储设好；此处仅在无存储时确保按系统设定
    if (!saved) {
      const dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
    }
    // 系统主题变化时，若用户未手动选择则跟随
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const onSysTheme = (e) => {
      if (!localStorage.getItem('infowe-theme')) {
        document.documentElement.setAttribute('data-theme', e.matches ? 'dark' : 'light');
      }
    };
    if (mq.addEventListener) mq.addEventListener('change', onSysTheme);
    else if (mq.addListener) mq.addListener(onSysTheme);
    themeToggle.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme');
      const next = current === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('infowe-theme', next);
      // Re-trigger skill animation
      animateSkills();
    });
  }

  /* ============================================
     4. 合并滚动事件处理器（节流优化）
     ============================================ */
  const progressBar = document.getElementById('reading-progress');
  const navbar = document.getElementById('navbar');
  const backToTop = document.getElementById('back-to-top');
  var scrollTicking = false;

  window.addEventListener('scroll', function () {
    if (!scrollTicking) {
      requestAnimationFrame(function () {
        var scrollTop = window.scrollY;
        // 阅读进度条
        if (progressBar) {
          var docHeight = document.documentElement.scrollHeight - window.innerHeight;
          var progress = docHeight > 0 ? (scrollTop / docHeight) * 100 : 0;
          progressBar.style.width = Math.min(progress, 100) + '%';
        }
        // 导航栏阴影
        if (navbar) {
          navbar.classList.toggle('scrolled', scrollTop > 50);
        }
        // 回到顶部
        if (backToTop) {
          backToTop.classList.toggle('visible', scrollTop > 500);
        }
        scrollTicking = false;
      });
      scrollTicking = true;
    }
  }, { passive: true });

  /* ============================================
     6. 移动端菜单
     ============================================ */
  const menuBtn = document.getElementById('mobile-menu-btn');
  const navLinks = document.querySelector('.nav-links');
  if (menuBtn && navLinks) {
    menuBtn.addEventListener('click', () => {
      navLinks.classList.toggle('open');
    });
    document.addEventListener('click', (e) => {
      if (!menuBtn.contains(e.target) && !navLinks.contains(e.target)) {
        navLinks.classList.remove('open');
      }
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && navLinks.classList.contains('open')) {
        navLinks.classList.remove('open');
      }
    });
  }

  /* ============================================
     7. 3D 卡片倾斜（触屏设备跳过）
     ============================================ */
  if (!('ontouchstart' in window)) {
    document.querySelectorAll('.post-card').forEach(function (card) {
      card.addEventListener('mousemove', function (e) {
        var rect = card.getBoundingClientRect();
        var x = e.clientX - rect.left;
        var y = e.clientY - rect.top;
        var centerX = rect.width / 2;
        var centerY = rect.height / 2;
        var rotateX = ((y - centerY) / centerY) * -5;
        var rotateY = ((x - centerX) / centerX) * 5;
        card.style.transform = 'perspective(800px) rotateX(' + rotateX.toFixed(1) + 'deg) rotateY(' + rotateY.toFixed(1) + 'deg) translateY(-4px)';
      });
      card.addEventListener('mouseleave', function () {
        card.style.transform = 'perspective(800px) rotateX(0) rotateY(0) translateY(0)';
      });
    });
  }

  /* ============================================
     8. 滚动动画 (AOS - Animate on Scroll)
     ============================================ */
  const aosElements = document.querySelectorAll('[data-aos]');
  if (aosElements.length) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('aos-animate');
          // 延迟动画
          var delay = entry.target.getAttribute('data-aos-delay');
          if (delay) entry.target.style.animationDelay = delay + 'ms';
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.15, rootMargin: '0px 0px -40px 0px' });

    aosElements.forEach(el => observer.observe(el));
  }

  /* ============================================
     9. 打字机效果
     ============================================ */
  const typingEl = document.getElementById('typing-text');
  if (typingEl) {
    const phrases = [
      'print("Hello, World!")',
      'while alive: code()',
      'import creativity',
      'def build_dreams():',
      'lambda x: x * ∞',
      'await inspiration()',
      'git commit -m "🚀"',
      'try: explore()',
    ];
    let phraseIdx = 0;
    let charIdx = 0;
    let isDeleting = false;

    function type() {
      const current = phrases[phraseIdx];
      if (isDeleting) {
        typingEl.textContent = current.substring(0, charIdx - 1);
        charIdx--;
      } else {
        typingEl.textContent = current.substring(0, charIdx + 1);
        charIdx++;
      }

      // 后台标签页用一个长间隔兜底，避免集中抢夺 CPU
      if (document.hidden) { setTimeout(type, 2000); return; }

      let speed = isDeleting ? 40 : 80;

      if (!isDeleting && charIdx === current.length) {
        speed = 2000;
        isDeleting = true;
      } else if (isDeleting && charIdx === 0) {
        isDeleting = false;
        phraseIdx = (phraseIdx + 1) % phrases.length;
        speed = 400;
      }

      setTimeout(type, speed);
    }

    // 页面不可见时暂停打字动画
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden && typingEl && typingEl.textContent === '') type();
    });

    type();
  }

  /* ============================================
     10. 数字滚动动画
     ============================================ */
  function animateCounters() {
    var counterEls = document.querySelectorAll('.stat-number[data-target]');
    if (!counterEls.length) return;

    var counterObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        var el = entry.target;
        counterObserver.unobserve(el);
        var target = parseInt(el.getAttribute('data-target'));
        var duration = 1500;
        var start = performance.now();
        function update(now) {
          var progress = Math.min((now - start) / duration, 1);
          var eased = 1 - Math.pow(1 - progress, 3);
          el.textContent = Math.floor(eased * target);
          if (progress < 1) requestAnimationFrame(update);
          else el.textContent = target;
        }
        requestAnimationFrame(update);
      });
    }, { threshold: 0.3 });

    counterEls.forEach(function (el) { counterObserver.observe(el); });
  }
  animateCounters();

  /* ============================================
     11. 技能条动画
     ============================================ */
  function animateSkills() {
    document.querySelectorAll('.skill-fill').forEach(bar => {
      bar.classList.remove('animate');
      void bar.offsetWidth; // reflow
      bar.classList.add('animate');
    });
  }

  const skillsObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        animateSkills();
        skillsObserver.unobserve(entry.target);
      }
    });
  }, { threshold: 0.3 });

  const skillsCard = document.querySelector('.skills-card');
  if (skillsCard) skillsObserver.observe(skillsCard);

  /* ============================================
     12. 回到顶部按钮
     ============================================ */
  if (backToTop) {
    backToTop.addEventListener('click', function () {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

  /* ============================================
     13. 代码高亮
     ============================================ */
  if (typeof hljs !== 'undefined') {
    hljs.highlightAll();
  }

  /* ============================================
     14. 平滑滚动导航（点击导航链接）
     ============================================ */
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
      const target = document.querySelector(this.getAttribute('href'));
      if (target) {
        e.preventDefault();
        target.scrollIntoView({ behavior: 'smooth' });
      }
    });
  });

  /* ============================================
     14.5 时间线导航（年份高亮 + 滚动同步）
     ============================================ */
  const timelineNav = document.getElementById('timelineNav');
  if (timelineNav) {
    const yearLinks = Array.from(timelineNav.querySelectorAll('.timeline-link'));
    const yearSections = yearLinks
      .map(l => document.getElementById('year-' + l.dataset.year))
      .filter(Boolean);

    function setActiveYear(year) {
      yearLinks.forEach(l => l.classList.toggle('active', l.dataset.year === String(year)));
    }

    // 点击高亮（平滑滚动由 14 节统一处理）
    yearLinks.forEach(l => l.addEventListener('click', () => setActiveYear(l.dataset.year)));

    // 滚动同步高亮
    const navH = timelineNav.offsetHeight || 48;
    const spy = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) setActiveYear(entry.target.id.replace('year-', ''));
      });
    }, { rootMargin: '-' + (navH + 12) + 'px 0px -70% 0px', threshold: 0 });
    yearSections.forEach(s => spy.observe(s));

    // 初始高亮第一个年份
    if (yearLinks.length) setActiveYear(yearLinks[0].dataset.year);
  }

  /* ============================================
     15. 标签云项延迟索引
     ============================================ */
  document.querySelectorAll('.tag-cloud-item').forEach((item, i) => {
    item.style.setProperty('--i', i);
  });

  /* ============================================
     16. 代码块复制按钮
     ============================================ */
  const COPY_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
  const CHECK_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>';

  document.querySelectorAll('.post-content pre, .post-body pre').forEach((pre) => {
    if (pre.querySelector('.code-copy-btn')) return;
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'code-copy-btn';
    btn.setAttribute('aria-label', '复制代码');
    btn.innerHTML = COPY_ICON + '<span>复制</span>';
    pre.appendChild(btn);

    btn.addEventListener('click', async () => {
      const code = pre.querySelector('code');
      const text = code ? code.innerText : pre.innerText;
      let ok = false;
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(text);
          ok = true;
        }
      } catch (e) { /* 落到下方 execCommand 兜底 */ }
      if (!ok) {
        try {
          const ta = document.createElement('textarea');
          ta.value = text; ta.style.position = 'fixed'; ta.style.top = '-9999px'; ta.style.opacity = '0';
          document.body.appendChild(ta); ta.focus(); ta.select();
          ok = document.execCommand('copy');
          document.body.removeChild(ta);
        } catch (e) { ok = false; }
      }
      if (ok) {
        btn.classList.add('copied');
        btn.innerHTML = CHECK_ICON + '<span>已复制</span>';
      } else {
        btn.innerHTML = COPY_ICON + '<span>失败</span>';
      }
      setTimeout(() => {
        btn.classList.remove('copied');
        btn.innerHTML = COPY_ICON + '<span>复制</span>';
      }, 2000);
    });
  });

  console.log('%c infowe.site %c 豪子 - 工作机会 VX：CQGGTF ',
    'background:linear-gradient(135deg,#00d4ff,#a855f7);color:#fff;padding:4px 8px;border-radius:4px;font-weight:bold;',
    'color:#00d4ff;');

  /* ============================================
     17. 评论表单防重复提交
     ============================================ */
  var commentForm = document.querySelector('.comment-form');
  if (commentForm) {
    commentForm.addEventListener('submit', function () {
      var btn = commentForm.querySelector('.comment-submit-btn');
      if (btn) { btn.disabled = true; btn.textContent = '提交中...'; }
    });
  }
})();
