/* 代码字符粒子背景：登录页与前台首页 / 404 共用。
 *
 * 画面是缓慢漂浮的代码字符（{} [] () <> def class import ...），
 * 距离近的粒子之间会连线，另有一个跟随鼠标的柔光。
 * 画布固定铺满视口，绘制在内容下方，不拦截点击。
 *
 * 可通过 data-* 调整强度：
 *   data-count          桌面粒子数（默认 36）
 *   data-count-mobile   移动端粒子数（默认 16）
 *   data-connect        连线距离，0 表示不画连线（默认 80）
 *   data-opacity        透明度系数（默认 1）
 *   data-glow="0"       不显示鼠标光晕
 *
 * 系统开启「减少动态效果」时完全不启动；页面切到后台时暂停绘制。
 */
(function () {
  var canvas = document.getElementById('particle-canvas');
  if (!canvas) return;

  var mqlReduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)');
  if (mqlReduce && mqlReduce.matches) return;

  var ctx = canvas.getContext && canvas.getContext('2d');
  if (!ctx) return;

  function intAttr(name, fallback) {
    var value = parseInt(canvas.getAttribute(name), 10);
    return isNaN(value) ? fallback : value;
  }
  function floatAttr(name, fallback) {
    var value = parseFloat(canvas.getAttribute(name));
    return isNaN(value) ? fallback : value;
  }

  var isMobile = window.matchMedia('(max-width: 767.98px)').matches;
  var COUNT = isMobile ? intAttr('data-count-mobile', 16) : intAttr('data-count', 36);
  var CONNECT = intAttr('data-connect', 80);
  var ALPHA = floatAttr('data-opacity', 1);
  var cursorGlow = canvas.getAttribute('data-glow') === '0'
    ? null
    : document.getElementById('cursor-glow');

  var chars = '01{}[]()<>/\\|*#@$%&;:,.pydef class import return async await lambda'.split(' ');
  var w = 0;
  var h = 0;
  var particles = [];
  var mouseX = -500;
  var mouseY = -500;
  var glowX = -500;
  var glowY = -500;
  var running = false;
  var rafId = 0;

  function isDark() {
    return document.documentElement.getAttribute('data-theme') !== 'light';
  }

  function resize() {
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = window.innerWidth;
    h = window.innerHeight;
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function Particle() {
    this.reset();
  }
  Particle.prototype.reset = function () {
    this.x = Math.random() * w;
    this.y = Math.random() * h;
    this.size = Math.random() * 10 + 6;
    this.speedY = Math.random() * 0.4 + 0.15;
    this.speedX = (Math.random() - 0.5) * 0.2;
    this.opacity = (Math.random() * 0.25 + 0.04) * ALPHA;
    this.char = chars[Math.floor(Math.random() * chars.length)];
    this.isSymbol = this.char.length === 1 && /[{}[\]()<>/\\|*#@$%&;:.,]/.test(this.char);
  };
  Particle.prototype.update = function () {
    this.y += this.speedY;
    this.x += this.speedX;
    if (this.y > h + 20) {
      this.y = -20;
      this.x = Math.random() * w;
    }
    if (this.x < -20) this.x = w + 20;
    if (this.x > w + 20) this.x = -20;
  };
  Particle.prototype.draw = function () {
    var dark = isDark();
    ctx.font = this.size + 'px monospace';
    ctx.fillStyle = this.isSymbol
      ? 'rgba(' + (dark ? '0,212,255' : '8,145,178') + ',' + (this.opacity * 1.5).toFixed(3) + ')'
      : 'rgba(' + (dark ? '168,85,247' : '124,58,237') + ',' + this.opacity.toFixed(3) + ')';
    ctx.fillText(this.char, this.x, this.y);
  };

  function init() {
    particles = [];
    for (var i = 0; i < COUNT; i++) particles.push(new Particle());
  }

  function updateGlow() {
    if (!cursorGlow) return;
    glowX += (mouseX - glowX) * 0.06;
    glowY += (mouseY - glowY) * 0.06;
    cursorGlow.style.transform = 'translate(' + (glowX - 150) + 'px,' + (glowY - 150) + 'px)';
  }

  function animate() {
    if (!running) return;
    ctx.clearRect(0, 0, w, h);

    for (var i = 0; i < particles.length; i++) {
      particles[i].update();
      particles[i].draw();
    }

    if (CONNECT > 0) {
      var dark = isDark();
      for (var a = 0; a < particles.length; a++) {
        var pi = particles[a];
        for (var b = a + 1; b < particles.length; b++) {
          var pj = particles[b];
          var dx = pi.x - pj.x;
          var dy = pi.y - pj.y;
          if (Math.abs(dx) > CONNECT || Math.abs(dy) > CONNECT) continue;
          var dsq = dx * dx + dy * dy;
          if (dsq >= CONNECT * CONNECT) continue;
          var alpha = (0.05 * (1 - Math.sqrt(dsq) / CONNECT)).toFixed(3);
          ctx.strokeStyle = 'rgba(' + (dark ? '0,212,255' : '8,145,178') + ',' + alpha + ')';
          ctx.lineWidth = 0.5;
          ctx.beginPath();
          ctx.moveTo(pi.x, pi.y);
          ctx.lineTo(pj.x, pj.y);
          ctx.stroke();
        }
      }
    }

    updateGlow();
    rafId = requestAnimationFrame(animate);
  }

  function start() {
    if (running) return;
    running = true;
    rafId = requestAnimationFrame(animate);
  }

  function stop() {
    running = false;
    cancelAnimationFrame(rafId);
  }

  if (cursorGlow) {
    document.addEventListener('mousemove', function (e) {
      mouseX = e.clientX;
      mouseY = e.clientY;
      cursorGlow.classList.add('visible');
    });
    document.addEventListener('mouseleave', function () {
      cursorGlow.classList.remove('visible');
    });
  }

  document.addEventListener('visibilitychange', function () {
    if (document.hidden) stop();
    else start();
  });

  var resizeTimer = 0;
  window.addEventListener('resize', function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      resize();
      init();
    }, 200);
  });

  resize();
  init();
  start();
})();
