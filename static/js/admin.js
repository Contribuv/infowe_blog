/**
 * infowe Admin Panel - 交互脚本
 */
(function () {
  'use strict';

  /* ─── 监听系统偏好变化（用户未手动切换时跟随）─── */
  (function watchSystemTheme() {
    try {
      var mql = window.matchMedia('(prefers-color-scheme: dark)');
      var onChange = function (e) {
        var saved;
        try { saved = localStorage.getItem('infowe-theme'); } catch (err) {}
        if (saved !== 'light' && saved !== 'dark') {
          var next = e.matches ? 'dark' : 'light';
          document.documentElement.setAttribute('data-theme', next);
          var meta = document.querySelector('meta[name="theme-color"]');
          if (meta) meta.setAttribute('content', next === 'dark' ? '#0f1117' : '#f5f5f5');
        }
      };
      if (mql.addEventListener) { mql.addEventListener('change', onChange); }
      else if (mql.addListener) { mql.addListener(onChange); }
    } catch (e) { /* 忽略 */ }
  })();

  /* ─── 主题手动切换：点击按钮翻转并持久化（支持顶栏与侧边栏两个按钮）─── */
  (function bindThemeToggle() {
    function syncIcons() {
      var theme = document.documentElement.getAttribute('data-theme');
      var isLight = theme === 'light';
      document.querySelectorAll('.theme-icon-dark, .theme-icon-light').forEach(function (el) {
        if (!el) return;
        var isDark = el.classList.contains('theme-icon-dark');
        el.style.display = (isDark ? !isLight : isLight) ? 'inline-flex' : 'none';
      });
    }
    function toggle() {
      var html = document.documentElement;
      var next = html.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
      html.setAttribute('data-theme', next);
      try { localStorage.setItem('infowe-theme', next); } catch (e) {}
      var meta = document.querySelector('meta[name="theme-color"]');
      if (meta) meta.setAttribute('content', next === 'dark' ? '#0f1117' : '#f5f5f5');
      syncIcons();
    }
    ['admin-theme-toggle', 'sidebar-theme-toggle'].forEach(function (id) {
      var btn = document.getElementById(id);
      if (btn) btn.addEventListener('click', toggle);
    });
    syncIcons();
  })();

  /* ─── Flash 自动消失 ─── */
  document.querySelectorAll('.flash, .flash-msg').forEach(function (el) {
    setTimeout(function () {
      el.style.transition = 'opacity 0.3s, transform 0.3s';
      el.style.opacity = '0';
      el.style.transform = 'translateY(-8px)';
      setTimeout(function () { el.remove(); }, 300);
    }, 4000);
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

  /* ─── 键盘快捷键 ─── */
  document.addEventListener('keydown', function (e) {
    // Ctrl+S 保存文章
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
      var form = document.getElementById('post-form');
      if (form) {
        e.preventDefault();
        form.submit();
      }
    }
    // Esc 关闭抽屉
    if (e.key === 'Escape') {
      document.body.classList.remove('sidebar-open');
    }
  });

  /* ─── 移动端抽屉侧边栏 ─── */
  var toggle = document.getElementById('sidebarToggle');
  var overlay = document.getElementById('sidebarOverlay');
  var closeBtn = document.getElementById('sidebarClose');

  function openSidebar() { document.body.classList.add('sidebar-open'); }
  function closeSidebar() { document.body.classList.remove('sidebar-open'); }

  if (toggle) toggle.addEventListener('click', openSidebar);
  if (closeBtn) closeBtn.addEventListener('click', closeSidebar);
  if (overlay) overlay.addEventListener('click', closeSidebar);

  // 点击导航项后自动收起（移动端）
  document.querySelectorAll('.sidebar-nav .nav-item').forEach(function (el) {
    el.addEventListener('click', function () {
      if (window.matchMedia('(max-width: 768px)').matches) closeSidebar();
    });
  });
})();
