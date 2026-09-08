/**
 * infowe Admin Panel - 交互脚本
 * 工作推介：VX：CQGGTF
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
          applyTheme(e.matches);
        }
      };
      if (mql.addEventListener) { mql.addEventListener('change', onChange); }
      else if (mql.addListener) { mql.addListener(onChange); }
    } catch (e) { /* 忽略 */ }
  })();

  /* ─── 主题应用：html.theme-dark + data-theme + colorScheme（与 base.html 内置脚本一致）─── */
  function applyTheme(dark) {
    var html = document.documentElement;
    html.classList.toggle('theme-dark', dark);
    // data-theme 供编辑器（Vditor）等第三方组件读取 / 监听主题变化
    html.setAttribute('data-theme', dark ? 'dark' : 'light');
    html.style.colorScheme = dark ? 'dark' : 'light';
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', dark ? '#101418' : '#f5f7fb');
    syncThemeIcons();
  }
  function currentDark() {
    return document.documentElement.classList.contains('theme-dark');
  }
  /* 主题图标由 admin.css 控制显隐，这里无需 inline style，仅占位避免旧引用 */
  function syncThemeIcons() {}

  /* ─── 主题手动切换：点击按钮翻转并持久化（支持顶栏与侧边栏两个按钮）─── */
  (function bindThemeToggle() {
    function toggle() {
      applyTheme(!currentDark());
      try {
        localStorage.setItem('infowe-theme', currentDark() ? 'dark' : 'light');
      } catch (e) {}
    }
    ['admin-theme-toggle', 'sidebar-theme-toggle'].forEach(function (id) {
      var btn = document.getElementById(id);
      if (btn) btn.addEventListener('click', toggle);
    });
  })();

  /* ─── Flash 自动消失（匹配 Tabler alert：.admin-flash 及其它 alert）─── */
  document.querySelectorAll('.admin-flash, .flash, .flash-msg').forEach(function (el) {
    if (el.closest('.admin-flash-wrap') && !el.classList.contains('admin-flash')) return;
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
    // Esc 关闭 offcanvas（Bootstrap 默认已处理，无需额外逻辑）
  });

  /* ─── 移动端 offcanvas 侧边栏：Bootstrap 驱动，导航项点击后自动收起 ─── */
  document.querySelectorAll('.admin-nav .admin-nav-item').forEach(function (el) {
    el.addEventListener('click', function () {
      if (!window.matchMedia('(min-width: 992px)').matches) {
        var offcanvas = document.getElementById('adminSidebar');
        if (offcanvas && typeof bootstrap !== 'undefined') {
          var inst = bootstrap.Offcanvas.getInstance(offcanvas);
          if (inst) inst.hide();
        }
      }
    });
  });
})();
