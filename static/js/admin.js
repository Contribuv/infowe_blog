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
  var THEME_LABEL = { auto: '跟随系统', light: '浅色主题', dark: '深色主题' };

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
    if (meta) meta.setAttribute('content', dark ? '#1a1d23' : '#f5f6fa');
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

  /* ─── 通用确认对话框：替代原生 confirm，风格与后台一致 ───
     用法：await window.adminConfirm('确定删除？', { title: '删除', okText: '删除' })
     返回 Promise<boolean>；danger: false 时确认按钮用主色（非破坏性操作）。 */
  var confirmDialog = null;

  function ensureConfirmDialog() {
    if (confirmDialog) return confirmDialog;
    var dialog = document.createElement('dialog');
    dialog.id = 'adminConfirmDialog';
    dialog.className = 'admin-detail-dialog admin-confirm-dialog';
    dialog.innerHTML =
      '<div class="admin-detail-head">' +
        '<strong id="adminConfirmTitle">确认操作</strong>' +
        '<button type="button" class="admin-detail-close" data-confirm-cancel aria-label="关闭">×</button>' +
      '</div>' +
      '<div class="admin-detail-body">' +
        '<p id="adminConfirmMessage" class="admin-confirm-message"></p>' +
        '<div class="admin-confirm-actions">' +
          '<button type="button" class="btn btn-secondary" data-confirm-cancel>取消</button>' +
          '<button type="button" class="btn btn-danger" data-confirm-ok>确定</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(dialog);
    confirmDialog = dialog;
    return dialog;
  }

  window.adminConfirm = function (message, options) {
    options = options || {};
    var dialog = ensureConfirmDialog();
    var title = dialog.querySelector('#adminConfirmTitle');
    var msg = dialog.querySelector('#adminConfirmMessage');
    var ok = dialog.querySelector('[data-confirm-ok]');
    var cancels = dialog.querySelectorAll('[data-confirm-cancel]');

    title.textContent = options.title || '确认操作';
    msg.textContent = message || '确定继续吗？';
    ok.textContent = options.okText || '确定';
    ok.className = 'btn ' + (options.danger === false ? 'btn-primary' : 'btn-danger');

    return new Promise(function (resolve) {
      function finish(result) {
        ok.removeEventListener('click', onOk);
        Array.prototype.forEach.call(cancels, function (b) { b.removeEventListener('click', onCancel); });
        dialog.removeEventListener('cancel', onCancel);
        dialog.removeEventListener('click', onBackdrop);
        if (dialog.open) dialog.close();
        resolve(result);
      }
      function onOk() { finish(true); }
      function onCancel(e) { if (e) e.preventDefault(); finish(false); }
      function onBackdrop(e) { if (e.target === dialog) finish(false); }

      ok.addEventListener('click', onOk);
      Array.prototype.forEach.call(cancels, function (b) { b.addEventListener('click', onCancel); });
      dialog.addEventListener('cancel', onCancel);
      dialog.addEventListener('click', onBackdrop);
      dialog.showModal();
    });
  };

  /* ─── 图片浮窗预览：后台点评论图不再开新窗口 ───
     多图（同一条评论）支持左右切换；Esc / 点遮罩 / × 关闭。 */
  var imgDialog = null;
  var imgGroup = [];
  var imgIndex = 0;

  function ensureImgDialog() {
    if (imgDialog) return imgDialog;
    var dialog = document.createElement('dialog');
    dialog.id = 'adminImgDialog';
    dialog.className = 'admin-detail-dialog admin-img-dialog';
    dialog.innerHTML =
      '<div class="admin-detail-head">' +
        '<strong id="adminImgCaption">图片预览</strong>' +
        '<button type="button" class="admin-detail-close" data-img-close aria-label="关闭">×</button>' +
      '</div>' +
      '<div class="admin-img-stage">' +
        '<img id="adminImgView" alt="">' +
        '<span class="admin-img-tip" id="adminImgTip">图片加载中…</span>' +
        '<button type="button" class="admin-img-nav" data-img-prev aria-label="上一张">‹</button>' +
        '<button type="button" class="admin-img-nav" data-img-next aria-label="下一张">›</button>' +
      '</div>' +
      '<div class="admin-img-foot" id="adminImgFoot"></div>';
    document.body.appendChild(dialog);
    imgDialog = dialog;

    dialog.addEventListener('click', function (e) {
      if (e.target === dialog) closeImg();
    });
    dialog.querySelector('[data-img-close]').addEventListener('click', closeImg);
    dialog.querySelector('[data-img-prev]').addEventListener('click', function () { stepImg(-1); });
    dialog.querySelector('[data-img-next]').addEventListener('click', function () { stepImg(1); });
    dialog.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowLeft') { e.preventDefault(); stepImg(-1); }
      if (e.key === 'ArrowRight') { e.preventDefault(); stepImg(1); }
    });
    return dialog;
  }

  function renderImg() {
    var item = imgGroup[imgIndex] || {};
    var view = imgDialog.querySelector('#adminImgView');
    var tip = imgDialog.querySelector('#adminImgTip');
    var foot = imgDialog.querySelector('#adminImgFoot');
    var multi = imgGroup.length > 1;

    imgDialog.querySelector('#adminImgCaption').textContent = item.alt || '图片预览';
    foot.textContent = multi ? (imgIndex + 1) + ' / ' + imgGroup.length : '';
    Array.prototype.forEach.call(imgDialog.querySelectorAll('.admin-img-nav'), function (b) {
      b.hidden = !multi;
    });

    view.classList.add('is-loading');
    tip.textContent = '图片加载中…';
    tip.hidden = false;
    view.onload = function () {
      view.classList.remove('is-loading');
      tip.hidden = true;
    };
    view.onerror = function () {
      view.classList.remove('is-loading');
      tip.textContent = '图片加载失败';
    };
    view.src = item.src || '';
    view.alt = item.alt || '';
  }

  function stepImg(delta) {
    if (imgGroup.length < 2) return;
    imgIndex = (imgIndex + delta + imgGroup.length) % imgGroup.length;
    renderImg();
  }

  function closeImg() {
    if (!imgDialog) return;
    if (imgDialog.open) imgDialog.close();
    var view = imgDialog.querySelector('#adminImgView');
    view.removeAttribute('src');
    view.classList.remove('is-loading');
  }

  window.adminImgPreview = function (group, index) {
    imgDialog = ensureImgDialog();
    imgGroup = group || [];
    imgIndex = Math.max(0, Math.min(index || 0, imgGroup.length - 1));
    renderImg();
    if (!imgDialog.open) imgDialog.showModal();
  };

  // 事件委托：评论区缩略图（<a href="/manage/preview/asset/...">）改为浮窗预览
  document.addEventListener('click', function (e) {
    var link = e.target && e.target.closest ? e.target.closest('.cmt-images a') : null;
    if (!link) return;
    e.preventDefault();
    var box = link.closest('.cmt-images');
    var links = box ? Array.prototype.slice.call(box.querySelectorAll('a')) : [link];
    var group = links.map(function (a) {
      var im = a.querySelector('img');
      return { src: a.getAttribute('href') || '', alt: im ? (im.getAttribute('alt') || '') : '' };
    });
    window.adminImgPreview(group, links.indexOf(link));
  });
})();
