/* ═══════════════════════════════════════════════
   Toast 轻提示（全局）
   用法：window.toast('消息', 'success'|'error'|'info', 毫秒)
   自动消费：页面上任何带 [data-toast] 的元素（后端 flash 渲染成隐藏节点即可）
   ═══════════════════════════════════════════════ */
(function () {
  'use strict';

  var ICONS = {
    success: '<svg viewBox="0 0 24 24"><path d="M20 6 9 17l-5-5"/></svg>',
    error: '<svg viewBox="0 0 24 24"><path d="M18 6 6 18M6 6l12 12"/></svg>',
    info: '<svg viewBox="0 0 24 24"><path d="M12 16v-5"/><path d="M12 8h.01"/></svg>'
  };
  var CLOSE = '<svg viewBox="0 0 24 24" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>';
  var DUR = { success: 3600, error: 6000, info: 4200 };
  var MAX = 3;

  var layer = null;
  function ensureLayer() {
    if (layer && document.body.contains(layer)) return layer;
    layer = document.createElement('div');
    layer.className = 'toast-layer';
    layer.setAttribute('role', 'status');
    layer.setAttribute('aria-live', 'polite');
    document.body.appendChild(layer);
    return layer;
  }

  function dismiss(el) {
    if (!el || el.dataset.closing === '1') return;
    el.dataset.closing = '1';
    el.classList.remove('is-in');
    el.classList.add('is-out');
    setTimeout(function () {
      if (el.parentNode) el.parentNode.removeChild(el);
    }, 220);
  }

  window.toast = function (msg, type, duration) {
    msg = String(msg == null ? '' : msg).trim();
    if (!msg) return null;
    type = ICONS[type] ? type : 'info';
    var host = ensureLayer();

    // 同屏最多 3 条，超出先顶掉最旧的
    var items = host.querySelectorAll('.toast');
    for (var i = 0; i <= items.length - MAX; i++) dismiss(items[i]);

    var el = document.createElement('div');
    el.className = 'toast toast--' + type;
    el.innerHTML =
      '<span class="toast-icon" aria-hidden="true">' + ICONS[type] + '</span>' +
      '<span class="toast-msg"></span>' +
      '<span class="toast-close" role="button" tabindex="0" aria-label="关闭">' + CLOSE + '</span>';
    el.querySelector('.toast-msg').textContent = msg;  // textContent 防注入
    host.appendChild(el);

    // 两帧后再加 is-in，保证过渡动画生效
    requestAnimationFrame(function () {
      requestAnimationFrame(function () { el.classList.add('is-in'); });
    });

    var timer = setTimeout(function () { dismiss(el); }, duration || DUR[type]);
    el.addEventListener('mouseenter', function () { clearTimeout(timer); });
    el.addEventListener('mouseleave', function () {
      timer = setTimeout(function () { dismiss(el); }, 1600);
    });
    el.querySelector('.toast-close').addEventListener('click', function () {
      clearTimeout(timer);
      dismiss(el);
    });
    el.querySelector('.toast-close').addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); dismiss(el); }
    });
    return el;
  };

  // 后端 flash → Toast：模板把消息渲染进 [data-toast] 隐藏节点，这里统一消费
  function consumeFlashNodes() {
    var nodes = document.querySelectorAll('[data-toast]');
    var delay = 0;
    Array.prototype.forEach.call(nodes, function (n) {
      var msg = n.getAttribute('data-toast');
      var type = n.getAttribute('data-toast-type') || 'info';
      setTimeout(function () { window.toast(msg, type); }, delay);
      delay += 120;
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', consumeFlashNodes);
  } else {
    consumeFlashNodes();
  }
})();
