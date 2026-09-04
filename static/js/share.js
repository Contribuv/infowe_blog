/* ==============================================
   infowe Blog · 文章分享面板（共享，default / tech 主题通用）
   特性：
   - 不依赖 Web Share API，纯站内实现（PC/移动端行为一致）
   - 复制链接（clipboard + execCommand 兜底）
   - 微博 / QQ 空间：平台官方开放分享 URL（免 API Key，新窗口打开）
   - 微信：本地 qrcode-generator 生成二维码，扫码后在微信内转发
   触发元素：任意 [data-share-open]，data-title 可选（缺省用 document.title）
   ============================================== */
(function () {
  'use strict';

  var panel = null, mask = null, btnTitle = '', btnUrl = '', qrRendered = false;
  var lastFocused = null;

  var COPY_ICON =
    '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>' +
    '<path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>';
  var CLOSE_ICON =
    '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">' +
    '<path d="M18 6 6 18M6 6l12 12"/></svg>';

  /* ── 渠道品牌图标（形状复刻自 simple-icons，CC0 1.0；商标归属各品牌方） ── */
  var WECHAT_ICON =
    '<svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor" aria-hidden="true"><path d="M8.691 2.188C3.891 2.188 0 5.476 0 9.53c0 2.212 1.17 4.203 3.002 5.55a.59.59 0 0 1 .213.665l-.39 1.48c-.019.07-.048.141-.048.213 0 .163.13.295.29.295a.326.326 0 0 0 .167-.054l1.903-1.114a.864.864 0 0 1 .717-.098 10.16 10.16 0 0 0 2.837.403c.276 0 .543-.027.811-.05-.857-2.578.157-4.972 1.932-6.446 1.703-1.415 3.882-1.98 5.853-1.838-.576-3.583-4.196-6.348-8.596-6.348zM5.785 5.991c.642 0 1.162.529 1.162 1.18a1.17 1.17 0 0 1-1.162 1.178A1.17 1.17 0 0 1 4.623 7.17c0-.651.52-1.18 1.162-1.18zm5.813 0c.642 0 1.162.529 1.162 1.18a1.17 1.17 0 0 1-1.162 1.178 1.17 1.17 0 0 1-1.162-1.178c0-.651.52-1.18 1.162-1.18zm5.34 2.867c-1.797-.052-3.746.512-5.28 1.786-1.72 1.428-2.687 3.72-1.78 6.22.942 2.453 3.666 4.229 6.884 4.229.826 0 1.622-.12 2.361-.336a.722.722 0 0 1 .598.082l1.584.926a.272.272 0 0 0 .14.047c.134 0 .24-.111.24-.247 0-.06-.023-.12-.038-.177l-.327-1.233a.582.582 0 0 1-.023-.156.49.49 0 0 1 .201-.398C23.024 18.48 24 16.82 24 14.98c0-3.21-2.931-5.837-6.656-6.088V8.89c-.135-.01-.27-.027-.407-.03zm-2.53 3.274c.535 0 .969.44.969.982a.976.976 0 0 1-.969.983.976.976 0 0 1-.969-.983c0-.542.434-.982.97-.982zm4.844 0c.535 0 .969.44.969.982a.976.976 0 0 1-.969.983.976.976 0 0 1-.969-.983c0-.542.434-.982.969-.982z"/></svg>';
  var WEIBO_ICON =
    '<svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor" aria-hidden="true"><path d="M10.098 20.323c-3.977.391-7.414-1.406-7.672-4.02-.259-2.609 2.759-5.047 6.74-5.441 3.979-.394 7.413 1.404 7.671 4.018.259 2.6-2.759 5.049-6.737 5.439l-.002.004zM9.05 17.219c-.384.616-1.208.884-1.829.602-.612-.279-.793-.991-.406-1.593.379-.595 1.176-.861 1.793-.601.622.263.82.972.442 1.592zm1.27-1.627c-.141.237-.449.353-.689.253-.236-.09-.313-.361-.177-.586.138-.227.436-.346.672-.24.239.09.315.36.18.601l.014-.028zm.176-2.719c-1.893-.493-4.033.45-4.857 2.118-.836 1.704-.026 3.591 1.886 4.21 1.983.64 4.318-.341 5.132-2.179.8-1.793-.201-3.642-2.161-4.149zm7.563-1.224c-.346-.105-.57-.18-.405-.615.375-.977.42-1.804 0-2.404-.781-1.112-2.915-1.053-5.364-.03 0 0-.766.331-.571-.271.376-1.217.315-2.224-.27-2.809-1.338-1.337-4.869.045-7.888 3.08C1.309 10.87 0 13.273 0 15.348c0 3.981 5.099 6.395 10.086 6.395 6.536 0 10.888-3.801 10.888-6.82 0-1.822-1.547-2.854-2.915-3.284v.01zm1.908-5.092c-.766-.856-1.908-1.187-2.96-.962-.436.09-.706.511-.616.932.09.42.511.691.932.602.511-.105 1.067.044 1.442.465.376.421.466.977.316 1.473-.136.406.089.856.51.992.405.119.857-.105.992-.512.33-1.021.12-2.178-.646-3.035l.03.045zm2.418-2.195c-1.576-1.757-3.905-2.419-6.054-1.968-.496.104-.812.587-.706 1.081.104.496.586.813 1.082.707 1.532-.331 3.185.15 4.296 1.383 1.112 1.246 1.429 2.943.947 4.416-.165.48.106 1.007.586 1.157.479.165.991-.104 1.157-.586.675-2.088.241-4.478-1.338-6.235l.03.045z"/></svg>';
  var QZONE_ICON =
    '<svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor" aria-hidden="true"><path d="M21.395 15.035a40 40 0 0 0-.803-2.264l-1.079-2.695c.001-.032.014-.562.014-.836C19.526 4.632 17.351 0 12 0S4.474 4.632 4.474 9.241c0 .274.013.804.014.836l-1.08 2.695a39 39 0 0 0-.802 2.264c-1.021 3.283-.69 4.643-.438 4.673.54.065 2.103-2.472 2.103-2.472 0 1.469.756 3.387 2.394 4.771-.612.188-1.363.479-1.845.835-.434.32-.379.646-.301.778.343.578 5.883.369 7.482.189 1.6.18 7.14.389 7.483-.189.078-.132.132-.458-.301-.778-.483-.356-1.233-.646-1.846-.836 1.637-1.384 2.393-3.302 2.393-4.771 0 0 1.563 2.537 2.103 2.472.251-.03.581-1.39-.438-4.673"/></svg>';

  /* ── 弹层结构 ── */
  function build() {
    mask = document.createElement('div');
    mask.className = 'share-mask';

    panel = document.createElement('div');
    panel.className = 'share-panel';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-modal', 'true');
    panel.setAttribute('aria-label', '分享文章');

    panel.innerHTML =
      '<div class="share-panel-head">' +
      '  <div class="share-panel-title">分享文章</div>' +
      '  <button type="button" class="share-close" data-share-close aria-label="关闭">' + CLOSE_ICON + '</button>' +
      '</div>' +
      '<div class="share-views">' +
      '  <div class="share-view share-view-list">' +
      '    <div class="share-channels">' +
      '      <button type="button" class="share-item share-item-copy" data-share-copy>' +
      '        <span class="share-chip">' + COPY_ICON + '</span>' +
      '        <span class="share-label">复制链接</span>' +
      '      </button>' +
      '      <button type="button" class="share-item share-item-wechat" data-share-wechat>' +
      '        <span class="share-chip">' + WECHAT_ICON + '</span>' +
      '        <span class="share-label">微信</span>' +
      '      </button>' +
      '      <a class="share-item share-item-weibo" data-share-url target="_blank" rel="noopener">' +
      '        <span class="share-chip">' + WEIBO_ICON + '</span>' +
      '        <span class="share-label">微博</span>' +
      '      </a>' +
      '      <a class="share-item share-item-qzone" data-share-url target="_blank" rel="noopener">' +
      '        <span class="share-chip">' + QZONE_ICON + '</span>' +
      '        <span class="share-label">QQ 空间</span>' +
      '      </a>' +
      '    </div>' +
      '    <p class="share-tip">复制链接或分享到微博、QQ 空间；微信将生成二维码，扫码后转发</p>' +
      '  </div>' +
      '  <div class="share-view share-view-qr" hidden>' +
      '    <button type="button" class="share-back" data-share-back>' +
      '      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>返回' +
      '    </button>' +
      '    <div class="share-qr-box"><div class="share-qr" id="share-qr"></div></div>' +
      '    <p class="share-qr-tip">打开微信「扫一扫」，扫描上方二维码后在微信内转发分享</p>' +
      '  </div>' +
      '</div>';

    document.body.appendChild(mask);
    document.body.appendChild(panel);

    mask.addEventListener('click', close);
    panel.querySelectorAll('[data-share-close]').forEach(function (el) {
      el.addEventListener('click', close);
    });
  }

  /* ── 复制（clipboard 优先，旧环境 textarea 兜底） ── */
  function copyText(text, okFn, errFn) {
    if (navigator.clipboard && window.isSecureContext !== false) {
      navigator.clipboard.writeText(text).then(okFn, function () { legacyCopy(text, okFn, errFn); });
      return;
    }
    legacyCopy(text, okFn, errFn);
  }
  function legacyCopy(text, okFn, errFn) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.cssText = 'position:fixed;top:-9999px;left:-9999px;opacity:0;';
    document.body.appendChild(ta);
    ta.select();
    var ok = false;
    try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
    document.body.removeChild(ta);
    if (ok) okFn(); else if (errFn) errFn();
  }

  function setCopyDone(item) {
    var label = item.querySelector('.share-label');
    var chip = item.querySelector('.share-chip');
    if (!label) return;
    var old = label.textContent;
    label.textContent = '已复制';
    item.classList.add('is-copied');
    if (chip) chip.innerHTML =
      '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
    setTimeout(function () {
      label.textContent = old;
      item.classList.remove('is-copied');
      if (chip) chip.innerHTML = COPY_ICON;
    }, 2000);
  }

  function buildWeiboUrl(u, t) {
    return 'https://service.weibo.com/share/share.php?url=' + encodeURIComponent(u) + '&title=' + encodeURIComponent(t);
  }
  function buildQzoneUrl(u, t) {
    return 'https://sns.qzone.qq.com/cgi-bin/qzshare/cgi_qzshare_onekey?url=' + encodeURIComponent(u) + '&title=' + encodeURIComponent(t);
  }

  /* ── 渲染微信二维码（qrcode-generator 本地库） ── */
  function renderQr() {
    var box = document.getElementById('share-qr');
    if (!box) return;
    if (qrRendered) return;
    qrRendered = true;
    if (typeof window.qrcode !== 'function') {
      box.innerHTML = '<p class="share-qr-error">二维码组件未加载，请使用「复制链接」分享</p>';
      return;
    }
    try {
      var qr = window.qrcode(0, 'M');
      qr.addData(btnUrl);
      qr.make();
      box.innerHTML = qr.createSvgTag({ cellSize: 4, margin: 0, scalable: true });
    } catch (e) {
      box.innerHTML = '<p class="share-qr-error">二维码生成失败，请使用「复制链接」分享</p>';
    }
  }

  /* ── 打开 / 关闭 ── */
  function open(trigger) {
    btnTitle = (trigger && trigger.dataset && trigger.dataset.title) || document.title;
    btnUrl = window.location.href;

    if (!mask || !panel) build();
    qrRendered = false;
    var box = document.getElementById('share-qr');
    if (box) box.innerHTML = '';

    // 视图复位到渠道列表
    panel.querySelector('.share-view-list').hidden = false;
    var qv = panel.querySelector('.share-view-qr');
    qv.hidden = true;
    qv.style.display = '';
    // 复位复制按钮文案
    var copyItem = panel.querySelector('[data-share-copy]');
    copyItem.classList.remove('is-copied');
    copyItem.querySelector('.share-label').textContent = '复制链接';
    copyItem.querySelector('.share-chip').innerHTML = COPY_ICON;

    // 微博 / QQ 空间链接
    var urls = panel.querySelectorAll('[data-share-url]');
    if (urls[0]) urls[0].href = buildWeiboUrl(btnUrl, btnTitle);
    if (urls[1]) urls[1].href = buildQzoneUrl(btnUrl, btnTitle);

    lastFocused = document.activeElement;
    mask.classList.add('open');
    panel.classList.add('open');
    document.body.style.overflow = 'hidden';
    var closeBtn = panel.querySelector('[data-share-close]');
    if (closeBtn) closeBtn.focus();
  }

  function close() {
    if (!panel || !panel.classList.contains('open')) return;
    mask.classList.remove('open');
    panel.classList.remove('open');
    document.body.style.overflow = '';
    if (lastFocused && lastFocused.focus) lastFocused.focus();
  }

  /* ── 全局事件 ── */
  document.addEventListener('click', function (e) {
    var openBtn = e.target.closest('[data-share-open]');
    if (openBtn) {
      e.preventDefault();
      open(openBtn);
      return;
    }
    if (!panel || !panel.classList.contains('open')) return;

    var wechat = e.target.closest('[data-share-wechat]');
    if (wechat) {
      panel.querySelector('.share-view-list').hidden = true;
      panel.querySelector('.share-view-qr').hidden = false;
      renderQr();
      return;
    }
    var back = e.target.closest('[data-share-back]');
    if (back) {
      panel.querySelector('.share-view-qr').hidden = true;
      panel.querySelector('.share-view-list').hidden = false;
      return;
    }
    var copy = e.target.closest('[data-share-copy]');
    if (copy) {
      var text = btnTitle + '\n' + btnUrl;
      copyText(text, function () {
        setCopyDone(copy);
      }, function () {
        var label = copy.querySelector('.share-label');
        if (label) label.textContent = '复制失败';
        setTimeout(function () { if (label) label.textContent = '复制链接'; }, 1800);
      });
      return;
    }
    // 外链（微博/QQ）点击后关闭面板
    var ext = e.target.closest('[data-share-url]');
    if (ext) close();
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && panel && panel.classList.contains('open')) close();
  });
})();
