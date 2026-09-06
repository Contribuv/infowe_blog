/* ═══════════════════════════════════════════════
   评论交互（default / tech 两套主题共用）
   依赖：static/js/toast.js（window.toast）
   结构约定：一个 .cmt-thread = 一条根评论 + 它下面全部回复（.cmt-replies 内平铺）
   ── 回复 ──   表单统一挂到「所属楼层组的回复区末尾」，不再插到已有回复之前
   ── 折叠 ──   回复数 > COLLAPSE_AT 时默认只显示 SHOW_COUNT 条
   ── 提示 ──   提交态、字数、待审核提示均由本文件驱动
   ═══════════════════════════════════════════════ */
(function () {
  'use strict';

  var SHOW_COUNT = 2;    // 折叠态露出的回复条数
  var COLLAPSE_AT = 3;   // 回复数超过此值才折叠
  var MAX_LEN = 2000;

  /* ── 0. 头像兜底（须在表单检查之前：有头像即初始化） ──
     外部头像源（Cravatar/WeAvatar/QQ）失败或长时间挂起时，
     依次回退 备用源 → 本地默认头像，避免评论出头像空白。 */
  var AV_TIMEOUT = 3000;
  function initAvatar(img) {
    if (!img || img.dataset.avInit === '1') return;
    img.dataset.avInit = '1';
    var fallback = img.getAttribute('data-fallback') || '';
    var def = img.getAttribute('data-default') || '';
    img.addEventListener('error', function () {
      if (img.src === def) return;
      if (fallback && !img.dataset.fb) { img.dataset.fb = '1'; img.src = fallback; }
      else if (def) { img.src = def; }
    });
    // 挂起兜底：图片进入视口后仍未完成加载（被墙/超时）→ 切本地默认头像
    var hangCheck = function () {
      if (img.naturalWidth === 0 && !img.complete && def && img.src !== def) {
        img.src = def;
      }
    };
    if ('IntersectionObserver' in window) {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          if (en.isIntersecting) {
            io.unobserve(en.target);
            setTimeout(hangCheck, AV_TIMEOUT);
          }
        });
      }, { rootMargin: '300px' });
      io.observe(img);
    } else {
      setTimeout(hangCheck, AV_TIMEOUT);
    }
  }
  var avImgs = document.querySelectorAll('.cmt-avatar-img');
  Array.prototype.forEach.call(avImgs, initAvatar);

  var form = document.getElementById('comment-form');
  if (!form) return;

  var list = document.getElementById('cmt-list');
  var parentInput = document.getElementById('comment-parent-id');
  var hint = document.getElementById('comment-replying');
  var hintName = document.getElementById('comment-replying-name');
  var cancelBtn = document.getElementById('comment-cancel-reply');
  var anchor = document.getElementById('comment-form-anchor');
  var textarea = form.querySelector('textarea');
  var submitBtn = form.querySelector('.submit');
  var counter = form.querySelector('.count');
  var fields = document.getElementById('comment-fields');
  var remember = document.getElementById('comment-remember');
  var editBtn = document.getElementById('comment-remember-edit');

  /* ── 1. 回复：把表单挂到该评论所属楼层组的回复区末尾 ── */
  function repliesBoxOf(el) {
    var thread = el.closest('.cmt-thread');
    if (!thread) return null;
    var box = null;
    Array.prototype.forEach.call(thread.children, function (ch) {
      if (!box && ch.classList.contains('cmt-replies')) box = ch;
    });
    if (!box) {
      box = document.createElement('div');
      box.className = 'cmt-replies';
      thread.appendChild(box);
    }
    return box;
  }

  function resetReply() {
    if (parentInput) parentInput.value = '';
    if (hint) hint.hidden = true;
    form.classList.remove('is-inline');
    if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(form, anchor);
  }

  document.addEventListener('click', function (e) {
    var btn = e.target.closest ? e.target.closest('.cmt-reply') : null;
    if (!btn || !list || !list.contains(btn)) return;

    var item = btn.closest('.cmt-item');
    var box = repliesBoxOf(item);
    if (!box) return;

    if (parentInput) parentInput.value = btn.getAttribute('data-reply-to') || '';
    if (hintName) hintName.textContent = btn.getAttribute('data-reply-name') || '';
    if (hint) hint.hidden = false;
    form.classList.add('is-inline');
    box.appendChild(form);   // 追加到末尾，位于已有回复之后

    if (typeof window.toast === 'function') {
      // 不打断用户：仅静默定位，不弹提示
    }
    form.scrollIntoView({ behavior: 'smooth', block: 'center' });
    if (textarea) setTimeout(function () { textarea.focus({ preventScroll: true }); }, 260);
  });

  if (cancelBtn) {
    cancelBtn.addEventListener('click', function () {
      resetReply();
      form.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  }

  /* ── 2. 折叠 / 展开：回复过多的楼层组默认收起 ── */
  function setupFold(box) {
    if (box.dataset.foldInit === '1') return;
    box.dataset.foldInit = '1';

    var items = [];
    Array.prototype.forEach.call(box.children, function (ch) {
      // 只统计真正的评论条目，跳过表单、折叠按钮
      if (ch.classList.contains('cmt-item')) items.push(ch);
    });
    if (items.length <= COLLAPSE_AT) return;

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'cmt-fold';
    btn.setAttribute('aria-expanded', 'false');
    var rest = items.length - SHOW_COUNT;

    function render() {
      var open = btn.getAttribute('aria-expanded') === 'true';
      btn.innerHTML = '<svg viewBox="0 0 24 24"><path d="M6 9l6 6 6-6"/></svg>' +
        (open ? '收起回复' : '展开其余 ' + rest + ' 条回复');
      items.forEach(function (it, i) { it.hidden = !open && i >= SHOW_COUNT; });
    }

    btn.addEventListener('click', function () {
      var open = btn.getAttribute('aria-expanded') === 'true';
      btn.setAttribute('aria-expanded', open ? 'false' : 'true');
      render();
      if (open) {   // 收起后把视图拉回本楼层，避免页面突然变短
        var thread = box.closest('.cmt-thread');
        if (thread) thread.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });

    render();
    box.appendChild(btn);
  }

  function setupAllFolds() {
    if (!list) return;
    Array.prototype.forEach.call(list.querySelectorAll('.cmt-replies'), setupFold);
  }
  setupAllFolds();

  /* ── 3. 字数统计 ── */
  if (textarea && counter) {
    var sync = function () {
      var n = textarea.value.length;
      counter.textContent = n + ' / ' + MAX_LEN;
      counter.classList.toggle('is-over', n > MAX_LEN);
    };
    textarea.addEventListener('input', sync);
    sync();
  }

  /* ── 4. 提交防重复 ── */
  if (submitBtn) {
    form.addEventListener('submit', function () {
      if (form.dataset.submitting === '1') {
        if (window.toast) window.toast('正在提交，请稍候…', 'info', 2000);
        return false;
      }
      if (!textarea || !textarea.value.trim()) {
        if (window.toast) window.toast('请先填写评论内容', 'error');
        textarea && textarea.focus();
        return false;
      }
      if (textarea.value.length > MAX_LEN) {
        if (window.toast) window.toast('评论内容不能超过 ' + MAX_LEN + ' 字', 'error');
        textarea.focus();
        return false;
      }
      form.dataset.submitting = '1';
      submitBtn.disabled = true;
      submitBtn.textContent = '提交中…';
      // 兜底：10 秒后恢复，避免网络异常导致按钮永久卡死
      setTimeout(function () {
        form.dataset.submitting = '';
        submitBtn.disabled = false;
        submitBtn.textContent = '提交评论';
      }, 10000);
    });
  }

  /* ── 5. 记住信息：点「修改」展开昵称等字段 ── */
  if (editBtn && fields) {
    editBtn.addEventListener('click', function () {
      fields.hidden = false;
      if (remember) remember.hidden = true;
      var first = fields.querySelector('input');
      if (first) first.focus();
    });
  }

  /* ── 6. 待审核评论：轻提示引导（页面上已有提示条，这里补一句可关闭的说明） ── */
  var notice = document.getElementById('cmt-notice');
  if (notice && !notice.dataset.seen) {
    var close = notice.querySelector('[data-notice-close]');
    if (close) {
      close.addEventListener('click', function () {
        notice.hidden = true;
        try { sessionStorage.setItem('cmt_notice_closed', '1'); } catch (e) {}
      });
    }
    try {
      if (sessionStorage.getItem('cmt_notice_closed') === '1') notice.hidden = true;
    } catch (e) {}
  }
})();
