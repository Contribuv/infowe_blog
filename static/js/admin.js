/**
 * infowe Admin Panel - 交互脚本（零框架依赖）
 * 主题：html[data-theme] 属性驱动（暗色默认，"light" 切亮色）
 * 抽屉：<992px 侧栏 offcanvas 替代方案（.admin-sidebar.open + .drawer-overlay.show）
 */
(function () {
  'use strict';

  /* ─── 主题 ─── */
  function isDark() {
    return document.documentElement.getAttribute('data-theme') !== 'light';
  }
  function applyTheme(dark) {
    var html = document.documentElement;
    if (dark) html.removeAttribute('data-theme');
    else html.setAttribute('data-theme', 'light');
    html.style.colorScheme = dark ? 'dark' : 'light';
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', dark ? '#0f1117' : '#f5f6fa');
  }

  /* 监听系统偏好变化（用户未手动切换时跟随） */
  (function watchSystemTheme() {
    try {
      var mql = window.matchMedia('(prefers-color-scheme: dark)');
      var onChange = function (e) {
        var saved;
        try { saved = localStorage.getItem('infowe-theme'); } catch (err) {}
        if (saved !== 'light' && saved !== 'dark') applyTheme(e.matches);
      };
      if (mql.addEventListener) mql.addEventListener('change', onChange);
      else if (mql.addListener) mql.addListener(onChange);
    } catch (e) { /* 忽略 */ }
  })();

  /* 手动切换：点击按钮翻转并持久化（顶栏 + 侧栏两个按钮） */
  (function bindThemeToggle() {
    function toggle() {
      applyTheme(!isDark());
      try {
        localStorage.setItem('infowe-theme', isDark() ? 'dark' : 'light');
      } catch (e) {}
    }
    ['admin-theme-toggle', 'sidebar-theme-toggle'].forEach(function (id) {
      var btn = document.getElementById(id);
      if (btn) btn.addEventListener('click', toggle);
    });
  })();

  /* ─── 移动端抽屉（<992px）─── */
  (function bindDrawer() {
    var sidebar = document.getElementById('adminSidebar');
    var overlay = document.getElementById('drawerOverlay');
    var burger = document.getElementById('adminBurger');
    var closeBtn = document.getElementById('drawerClose');
    if (!sidebar || !overlay) return;

    function isOpen() { return sidebar.classList.contains('open'); }
    function open() {
      sidebar.classList.add('open');
      overlay.classList.add('show');
      document.body.style.overflow = 'hidden';
      if (burger) burger.setAttribute('aria-expanded', 'true');
    }
    function close() {
      sidebar.classList.remove('open');
      overlay.classList.remove('show');
      document.body.style.overflow = '';
      if (burger) burger.setAttribute('aria-expanded', 'false');
    }

    if (burger) burger.addEventListener('click', function () { isOpen() ? close() : open(); });
    if (closeBtn) closeBtn.addEventListener('click', close);
    overlay.addEventListener('click', close);

    /* 导航链接点击后自动收起（按钮如主题切换不收起） */
    sidebar.querySelectorAll('a.admin-nav-item').forEach(function (el) {
      el.addEventListener('click', function () {
        if (isOpen()) close();
      });
    });

    /* Esc 关闭 */
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && isOpen()) close();
    });
  })();

  /* ─── Flash 提示：4 秒自动消失 + 手动关闭 ─── */
  document.querySelectorAll('.flash-msg').forEach(function (el) {
    var timer = setTimeout(function () {
      el.style.transition = 'opacity .3s, transform .3s';
      el.style.opacity = '0';
      el.style.transform = 'translateY(-8px)';
      setTimeout(function () { el.remove(); }, 300);
    }, 4000);
    var btn = el.querySelector('.flash-close');
    if (btn) btn.addEventListener('click', function () {
      clearTimeout(timer);
      el.remove();
    });
  });

  /* ─── 标题输入自动生成 Slug ─── */
  var titleInput = document.getElementById('title');
  var slugInput = document.querySelector('input[name="slug"]');
  if (titleInput && slugInput) {
    titleInput.addEventListener('input', function () {
      if (!slugInput.dataset.manual) {
        slugInput.value = titleInput.value
          .toLowerCase()
          .replace(/[^\w\s\u4e00-\u9fff-]/g, '')
          .replace(/\s+/g, '-')
          .slice(0, 60);
      }
    });
    slugInput.addEventListener('input', function () {
      slugInput.dataset.manual = '1';
    });
  }

  /* ─── 键盘快捷键：Ctrl+S 保存文章 ─── */
  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
      var form = document.getElementById('post-form');
      if (form) {
        e.preventDefault();
        form.submit();
      }
    }
  });
})();
