/**
 * infowe Admin Panel - 交互脚本（零框架依赖）
 * 主题：三模式循环（auto 跟随系统 → light → dark），与前台共用 infowe-theme 键
 * 抽屉：<992px 侧栏 offcanvas 替代方案（.admin-sidebar.open + .drawer-overlay.show）
 */
(function () {
  'use strict';

  /* ─── 主题（三模式：auto / dark / light） ─── */
  var THEME_KEY = 'infowe-theme';
  var THEME_ORDER = ['auto', 'light', 'dark'];   // 与前台 main.js 循环顺序一致
  var THEME_LABEL = { auto: '跟随系统', light: '浅色', dark: '深色' };

  function savedMode() {
    var t;
    try { t = localStorage.getItem(THEME_KEY); } catch (e) {}
    return THEME_ORDER.indexOf(t) !== -1 ? t : 'auto';
  }
  function isAuto() {
    return (document.documentElement.getAttribute('data-theme-mode') || 'auto') === 'auto';
  }
  function applyMode(mode) {
    var dark = mode === 'dark' || (mode === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches);
    var html = document.documentElement;
    html.setAttribute('data-theme-mode', mode);
    html.setAttribute('data-theme', dark ? 'dark' : 'light');
    html.style.colorScheme = dark ? 'dark' : 'light';
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', dark ? '#0f1117' : '#f5f6fa');
    /* 同步按钮提示（顶栏图标按钮 + 侧栏文字） */
    var label = '当前：' + THEME_LABEL[mode] + '，点击切换主题';
    ['admin-theme-toggle', 'sidebar-theme-toggle'].forEach(function (id) {
      var btn = document.getElementById(id);
      if (btn) { btn.title = label; btn.setAttribute('aria-label', label); }
    });
    var navLabel = document.querySelector('#sidebar-theme-toggle .theme-label');
    if (navLabel) navLabel.textContent = THEME_LABEL[mode];
  }

  /* 监听系统偏好变化：仅 auto 模式实时跟随 */
  (function watchSystemTheme() {
    try {
      var mql = window.matchMedia('(prefers-color-scheme: dark)');
      var onChange = function () {
        if (isAuto()) applyMode('auto');
      };
      if (mql.addEventListener) mql.addEventListener('change', onChange);
      else if (mql.addListener) mql.addListener(onChange);
    } catch (e) { /* 忽略 */ }
  })();

  /* 点击循环三模式并持久化（顶栏 + 侧栏两个按钮；顺序与前台一致） */
  (function bindThemeToggle() {
    ['admin-theme-toggle', 'sidebar-theme-toggle'].forEach(function (id) {
      var btn = document.getElementById(id);
      if (btn) btn.addEventListener('click', function () {
        var mode = THEME_ORDER[(THEME_ORDER.indexOf(savedMode()) + 1) % THEME_ORDER.length];
        applyMode(mode);
        try { localStorage.setItem(THEME_KEY, mode); } catch (e) {}
      });
    });
    /* 启动时同步按钮提示（html 属性已由 head 内联脚本设置） */
    applyMode(savedMode());
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

  /* ─── 批量选择模式：默认隐藏选择列/工具条，按钮进入与退出（posts/comments/categories/projects/links/timeline 共用） ─── */
  (function bindBulkMode() {
    if (!document.querySelector('input.row-check')) return;
    var header = document.querySelector('.page-header');
    if (!header) return;

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn btn-sm bulk-toggle';

    function sync() {
      var on = document.body.classList.contains('bulk-on');
      btn.textContent = on ? '退出批量' : '批量操作';
      btn.setAttribute('aria-pressed', String(on));
      btn.classList.toggle('btn-primary', on);
    }
    function toggle() {
      document.body.classList.toggle('bulk-on');
      sync();
    }
    btn.addEventListener('click', toggle);
    /* Esc 退出批量模式（与抽屉一致的键盘习惯） */
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && document.body.classList.contains('bulk-on')) toggle();
    });

    /* 挂到页头 .page-actions 末尾（无则创建容器）：主按钮在前、批量操作在后，全站排序一致 */
    var actions = header.querySelector('.page-actions');
    if (!actions) {
      actions = document.createElement('div');
      actions.className = 'page-actions';
      header.appendChild(actions);
    }
    actions.appendChild(btn);
    sync();
  })();

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
