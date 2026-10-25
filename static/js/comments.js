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
  var emailInput = document.getElementById('comment-email');
  var emailSuggest = document.getElementById('cmt-email-suggest');
  var qqAv = document.getElementById('cmt-qq-av');

  /* ── 0.5 表单定位：仅当表单显示不全（底部/顶部被视口截断）时才滚动；
     完全可见（如文章内容较短、页面本身能装下表单）则不滚动，避免多余跳动 ── */
  function scrollFormIntoView() {
    var rect = form.getBoundingClientRect();
    var vh = window.innerHeight || document.documentElement.clientHeight;
    if (rect.bottom > vh) {
      form.scrollIntoView({ behavior: 'smooth', block: 'end' });
    } else if (rect.top < 0) {
      form.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }

  /* 滚动定位时给表单留出上下边距，避免贴住视口边缘 */
  form.style.scrollMarginTop = '50px';
  form.style.scrollMarginBottom = '50px';

  /* 点「写评论」展开 <details> 后：表单被截断才滚动到可见 */
  var cmtBox = form.querySelector('.cmt-box');
  if (cmtBox) {
    cmtBox.addEventListener('toggle', function () {
      if (cmtBox.open) scrollFormIntoView();
    });
  }

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
    var boxEl = form.querySelector('.cmt-box');
    if (boxEl && !boxEl.open) boxEl.open = true;   // 折叠态下点「回复」自动展开表单
    box.appendChild(form);   // 追加到末尾，位于已有回复之后

    if (typeof window.toast === 'function') {
      // 不打断用户：仅静默定位，不弹提示
    }
    scrollFormIntoView();
    if (textarea) setTimeout(function () { textarea.focus({ preventScroll: true }); }, 260);
  });

  if (cancelBtn) {
    cancelBtn.addEventListener('click', function () {
      resetReply();
      scrollFormIntoView();
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

  /* ── 2.5 锚点定位：#comment-N 指向被折叠的回复时，先展开所在折叠区再滚动过去 ──
     折叠是用 hidden 实现的，隐藏元素没有布局盒子，浏览器直接跳转只能停在错误位置
     （后台评论管理点击 /projects/1#comment-68 定位不到就是此因）。这里保留折叠，
     仅在带锚点访问时自动展开命中的那一组，并短暂高亮目标。 */
  function revealHashTarget() {
    var hash = location.hash || '';
    if (hash.indexOf('#comment-') !== 0) return;
    var el = document.getElementById(hash.slice(1));
    if (!el) return;
    // 逐层向上展开包含它的折叠区（当前结构只有一层，写法兼容未来嵌套）
    var box = el.closest ? el.closest('.cmt-replies') : null;
    while (box) {
      var foldBtn = box.querySelector('.cmt-fold');
      if (foldBtn && foldBtn.getAttribute('aria-expanded') !== 'true') foldBtn.click();
      box = box.parentElement && box.parentElement.closest
        ? box.parentElement.closest('.cmt-replies') : null;
    }
    var scroll = function () {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      el.classList.add('cmt-anchor-flash');
      setTimeout(function () { el.classList.remove('cmt-anchor-flash'); }, 1600);
    };
    if (typeof requestAnimationFrame === 'function') requestAnimationFrame(scroll);
    else setTimeout(scroll, 30);
  }
  revealHashTarget();
  window.addEventListener('hashchange', revealHashTarget);

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
      // 邮箱若仍是纯数字 QQ 号，提交前自动补全 @qq.com（后端另有格式校验）
      if (emailInput && QQ_RE.test(emailInput.value.trim())) {
        emailInput.value = emailInput.value.trim() + '@qq.com';
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

  /* ── 7. 邮箱字段：纯数字 QQ 号 → 下拉补全 @qq.com + 预览 QQ 头像 ── */
  var QQ_RE = /^\d{5,12}$/;
  if (emailInput && emailSuggest) {
    var hideSuggest = function () { emailSuggest.hidden = true; };

    // 头像预览：前台代理不联网，首次未命中会 404，后端异步预热后重试即可命中
    var qqAvTries = 0;
    var showQqAv = function (qq) {
      if (!qqAv) return;
      qqAvTries = 0;
      qqAv.hidden = false;
      qqAv.src = '/avatar/q' + qq + '/100.png';
    };

    var syncEmail = function () {
      var v = emailInput.value.trim();
      if (QQ_RE.test(v)) {
        emailSuggest.textContent = '补全为 ' + v + '@qq.com';
        emailSuggest.hidden = false;
        showQqAv(v);
      } else {
        hideSuggest();
        if (qqAv) { qqAvTries = 0; qqAv.hidden = true; qqAv.removeAttribute('src'); }
      }
    };

    emailInput.addEventListener('input', syncEmail);
    emailInput.addEventListener('blur', function () { setTimeout(hideSuggest, 150); });
    if (qqAv) qqAv.addEventListener('error', function () {
      qqAv.hidden = true;
      var v = emailInput.value.trim();
      // 预热未完成：最多重试 2 次（1.5s / 3s），仍失败则保持隐藏
      if (QQ_RE.test(v) && qqAvTries < 2) {
        qqAvTries++;
        setTimeout(function () {
          if (QQ_RE.test(emailInput.value.trim())) {
            qqAv.hidden = false;
            qqAv.src = '/avatar/q' + emailInput.value.trim() + '/100.png?r=' + qqAvTries;
          }
        }, 1500 * qqAvTries);
      }
    });
    // mousedown 先于 blur：preventDefault 防止点选时下拉被 blur 抢先关闭
    emailSuggest.addEventListener('mousedown', function (e) {
      e.preventDefault();
      var v = emailInput.value.trim();
      if (QQ_RE.test(v)) emailInput.value = v + '@qq.com';
      hideSuggest();
      if (qqAv) qqAv.hidden = true;
      emailInput.focus();
    });
    syncEmail();   // 回填记住的邮箱时同步一次（纯数字则直接显示补全项）
  }

  /* ── 8. 表情选择：精选 Unicode emoji，插入到正文光标处 ── */
  var EMOJI_GROUPS = [
    { name: '笑脸', list: ['😀', '😄', '😁', '😂', '🤣', '😊', '😍', '🥰', '😘', '😉', '😎', '🤔', '😅', '😏', '🙄', '😜', '🤗', '🤭', '🥺', '😢', '😭', '😡', '😱', '😴', '🤤', '🙃', '😌', '😇'] },
    { name: '手势', list: ['👍', '👎', '👏', '🙏', '🤝', '💪', '✌️', '🤞', '👌', '🫡', '👋', '🤟'] },
    { name: '心与星', list: ['❤️', '💔', '💕', '💖', '💘', '✨', '🌟', '⭐', '💯'] },
    { name: '庆祝与符号', list: ['🎉', '🎊', '🎁', '🎂', '🔥', '✅', '❌', '⚠️', '👀', '💡', '🚀', '☕'] }
  ];
  var emojiWrap = document.getElementById('cmt-emoji');
  var emojiBtn = document.getElementById('cmt-emoji-btn');
  var emojiPanel = document.getElementById('cmt-emoji-panel');
  if (emojiBtn && emojiPanel && textarea) {
    var frag = document.createDocumentFragment();
    EMOJI_GROUPS.forEach(function (g) {
      var box = document.createElement('div');
      box.className = 'cmt-emoji-group';
      var title = document.createElement('div');
      title.className = 'cmt-emoji-title';
      title.textContent = g.name;
      box.appendChild(title);
      var grid = document.createElement('div');
      grid.className = 'cmt-emoji-grid';
      g.list.forEach(function (ch) {
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'cmt-emoji-item';
        b.textContent = ch;
        grid.appendChild(b);
      });
      box.appendChild(grid);
      frag.appendChild(box);
    });
    emojiPanel.appendChild(frag);

    var closeEmoji = function () {
      emojiPanel.hidden = true;
      emojiBtn.setAttribute('aria-expanded', 'false');
    };
    emojiBtn.addEventListener('click', function () {
      var willOpen = emojiPanel.hidden;
      emojiPanel.hidden = !willOpen;
      emojiBtn.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
    });
    emojiPanel.addEventListener('click', function (e) {
      var b = e.target.closest ? e.target.closest('.cmt-emoji-item') : null;
      if (!b) return;
      var ch = b.textContent;
      var s = textarea.selectionStart;
      var en = textarea.selectionEnd;
      if (typeof s === 'number' && typeof en === 'number') {
        var v = textarea.value;
        textarea.value = v.slice(0, s) + ch + v.slice(en);
        var pos = s + ch.length;
        textarea.setSelectionRange(pos, pos);
      } else {
        textarea.value += ch;
      }
      textarea.focus();
      textarea.dispatchEvent(new Event('input'));   // 同步字数统计
      closeEmoji();   // 选毕即收起
    });
    document.addEventListener('click', function (e) {
      if (emojiWrap && !emojiWrap.contains(e.target)) closeEmoji();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeEmoji();
    });
  }

  /* ── 9. 图片上传：选本地图 → POST 上传 → 以缩略图卡片展示（正文保持纯文字） ──
     上传成功后不往输入框塞 ![](url)，而是把 URL 记入隐藏域 images、在下方显示缩略图；
     用户可继续打字，也能单独删除某张图。提交时由后端合并进评论并做站内白名单校验。 */
  var imgup = document.getElementById('cmt-imgup');
  var imgupBtn = document.getElementById('cmt-imgup-btn');
  var imgupInput = document.getElementById('cmt-imgup-input');
  var imgupList = document.getElementById('cmt-imgup-list');
  var imagesInput = document.getElementById('comment-images');
  if (imgup && imgupBtn && imgupInput && imgupList && imagesInput) {
    var IMG_MAX = 5 * 1024 * 1024;
    var IMG_COUNT = 6;   // 与后端 Comments::MAX_IMAGES 保持一致
    var pendingImages = [];

    // 只接受本站评论上传目录的 URL 才拿来当缩略图，避免异常响应被注入
    var isLocalUpload = function (u) {
      return typeof u === 'string' &&
        /^\/uploads\/comment\/\d{4}\/\d{2}\/[A-Za-z0-9_.\-]+$/.test(u) &&
        u.indexOf('..') === -1;
    };

    var syncImagesInput = function () { imagesInput.value = pendingImages.join('\n'); };

    var renderImages = function () {
      imgupList.innerHTML = '';
      imgupList.hidden = pendingImages.length === 0;
      pendingImages.forEach(function (url, idx) {
        var chip = document.createElement('div');
        chip.className = 'cmt-imgup-item';

        var img = document.createElement('img');
        img.alt = '';
        img.loading = 'lazy';
        img.src = url;
        chip.appendChild(img);

        var del = document.createElement('button');
        del.type = 'button';
        del.className = 'cmt-imgup-remove';
        del.setAttribute('aria-label', '删除这张图片');
        del.textContent = '×';
        del.addEventListener('click', function () {
          pendingImages.splice(idx, 1);
          syncImagesInput();
          renderImages();
        });
        chip.appendChild(del);

        imgupList.appendChild(chip);
      });
    };

    var setImgBusy = function (busy) {
      imgupBtn.disabled = busy;
      imgupBtn.classList.toggle('is-loading', busy);
      imgupBtn.setAttribute('aria-expanded', busy ? 'true' : 'false');
    };

    imgupBtn.addEventListener('click', function () {
      if (imgupBtn.disabled) return;
      if (pendingImages.length >= IMG_COUNT) {
        if (window.toast) window.toast('最多添加 ' + IMG_COUNT + ' 张图片', 'error');
        return;
      }
      imgupInput.value = '';
      imgupInput.click();
    });

    imgupInput.addEventListener('change', function () {
      var f = imgupInput.files && imgupInput.files[0];
      if (!f) return;
      if (!/^image\/(png|jpeg|gif|webp)$/.test(f.type)) {
        if (window.toast) window.toast('仅支持 png / jpg / gif / webp 图片', 'error');
        return;
      }
      if (f.size > IMG_MAX) {
        if (window.toast) window.toast('图片不能超过 5MB', 'error');
        return;
      }
      var fd = new FormData();
      fd.append('image', f);
      setImgBusy(true);
      fetch('/comment/upload', { method: 'POST', body: fd, credentials: 'same-origin' })
        .then(function (r) { return r.json().catch(function () { return { error: '上传失败，请稍后再试' }; }); })
        .then(function (data) {
          if (data && isLocalUpload(data.url)) {
            pendingImages.push(data.url);
            syncImagesInput();
            renderImages();
            if (window.toast) window.toast('图片已添加', 'success');
          } else if (window.toast) {
            window.toast((data && data.error) || '上传失败', 'error');
          }
        })
        .catch(function () {
          if (window.toast) window.toast('网络异常，上传失败', 'error');
        })
        .then(function () { setImgBusy(false); });
    });
  }

  /* ── 10. 网址字段：缺协议时下拉补全 http:// / https://，失焦默认补 https:// ──
     type=text 不会触发原生 url 校验，故 www.demo.com 也能顺利提交。 */
  var webInput = document.getElementById('comment-website');
  var webSuggest = document.getElementById('cmt-website-suggest');
  if (webInput && webSuggest) {
    var hasScheme = function (v) { return /^[a-zA-Z][a-zA-Z0-9+.\-]*:\/\//.test(v); };
    var hideWebSuggest = function () { webSuggest.hidden = true; };

    var renderWebSuggest = function () {
      var v = webInput.value.trim();
      if (v === '' || hasScheme(v)) { hideWebSuggest(); return; }
      webSuggest.innerHTML = '';
      ['https://', 'http://'].forEach(function (scheme) {
        var item = document.createElement('div');
        item.className = 'cmt-suggest-item';
        item.setAttribute('data-scheme', scheme);
        item.textContent = '补全为 ' + scheme + v;
        webSuggest.appendChild(item);
      });
      webSuggest.hidden = false;
    };

    webInput.addEventListener('input', renderWebSuggest);
    webInput.addEventListener('focus', renderWebSuggest);
    webInput.addEventListener('blur', function () {
      setTimeout(hideWebSuggest, 150);
      // 兜底：失焦仍未写协议则默认补 https://，保证能提交
      var v = webInput.value.trim();
      if (v !== '' && !hasScheme(v)) webInput.value = 'https://' + v;
    });
    // mousedown 先于 blur：preventDefault 阻止失焦，保证能点到选项
    webSuggest.addEventListener('mousedown', function (e) {
      var item = e.target.closest ? e.target.closest('.cmt-suggest-item') : null;
      if (!item) return;
      e.preventDefault();
      var v = webInput.value.trim();
      if (!hasScheme(v)) webInput.value = item.getAttribute('data-scheme') + v;
      hideWebSuggest();
      webInput.focus();
    });
  }

  /* ── 11. 敏感词过滤：命中即就地替换为等长星号（词库由后端注入） ──
     词库挂在表单 data-sensitive-words（JSON）。前端实时拦截只是体验优化、天然可绕过，
     后端提交时另有兜底过滤（Sensitive::filter），两者共用同一份词库。 */
  if (textarea && form) {
    var rawWords = form.getAttribute('data-sensitive-words') || '';
    var wordRe = null;
    if (rawWords) {
      try {
        var words = JSON.parse(rawWords);
        if (Object.prototype.toString.call(words) === '[object Array]' && words.length) {
          words.sort(function (a, b) { return b.length - a.length; });   // 长词优先，保证最长匹配
          var alts = [];
          for (var wi = 0; wi < words.length; wi++) {
            var w = String(words[wi]);
            if (w) alts.push(w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
          }
          if (alts.length) wordRe = new RegExp('(' + alts.join('|') + ')', 'g');
        }
      } catch (e) { wordRe = null; }
    }

    if (wordRe) {
      var stars = function (n) {
        var s = '';
        for (var i = 0; i < n; i++) s += '*';
        return s;
      };
      var applyWordFilter = function () {
        var v = textarea.value;
        if (!v) return;
        var nv = v.replace(wordRe, function (m) { return stars(m.length); });
        if (nv !== v) {
          var ss = textarea.selectionStart;
          var se = textarea.selectionEnd;
          textarea.value = nv;   // 等长替换：长度不变，光标位置无需调整
          if (typeof ss === 'number') {
            try { textarea.setSelectionRange(ss, se); } catch (e) {}
          }
        }
      };
      // 中文输入法组字期间不改 value，否则会打断候选词；组字结束再过滤
      var composing = false;
      textarea.addEventListener('compositionstart', function () { composing = true; });
      textarea.addEventListener('compositionend', function () { composing = false; applyWordFilter(); });
      textarea.addEventListener('input', function () { if (!composing) applyWordFilter(); });
    }
  }

  /* ── 评论图片灯箱 ──
     正文里的 .cmt-img 默认是缩略小图（CSS 限宽高），点击后在本层浮窗里显示原图，
     点空白处 / 关闭按钮 / 按 Esc 关闭；触摸屏支持双指捏合缩放、单指拖动、双击放大还原。
     用事件委托绑定在 document 上，动态插入的评论也生效。 */
  (function () {
    var box = null, pic = null;
    var MIN_S = 1, MAX_S = 5, DBL_ZOOM = 2.5;
    var scale = 1, tx = 0, ty = 0;      // 变换：先平移再缩放，作用于居中显示的图片
    var pinch = null, drag = null;      // 手势起始状态
    var lastTap = 0, lastTapX = 0, lastTapY = 0;

    function apply() {
      pic.style.transform = (tx || ty || scale !== 1)
        ? 'translate(' + tx + 'px,' + ty + 'px) scale(' + scale + ')'
        : '';
    }
    // 拖动范围限制：不超过放大后图片相对视口的溢出量，避免图片被拖出屏幕找不回
    function clamp() {
      var w = pic.offsetWidth, h = pic.offsetHeight;
      var maxX = Math.max(0, (w * scale - w) / 2);
      var maxY = Math.max(0, (h * scale - h) / 2);
      if (tx > maxX) tx = maxX; else if (tx < -maxX) tx = -maxX;
      if (ty > maxY) ty = maxY; else if (ty < -maxY) ty = -maxY;
    }
    function commit() { clamp(); apply(); }
    function resetView() {
      scale = 1; tx = 0; ty = 0; pinch = null; drag = null;
      if (pic) { pic.style.transition = ''; apply(); }
    }
    function touchDist(a, b) {
      var dx = a.clientX - b.clientX, dy = a.clientY - b.clientY;
      return Math.sqrt(dx * dx + dy * dy) || 1;
    }
    function touchMid(a, b) {
      return { x: (a.clientX + b.clientX) / 2, y: (a.clientY + b.clientY) / 2 };
    }
    // 单击/双击：双击在 原始 ↔ 放大 之间切换（以图片中心为基准）
    function onTap(x, y) {
      var now = Date.now();
      if (now - lastTap < 300 && Math.abs(x - lastTapX) < 40 && Math.abs(y - lastTapY) < 40) {
        lastTap = 0;
        if (scale > 1) { scale = 1; tx = 0; ty = 0; }
        else { scale = DBL_ZOOM; tx = 0; ty = 0; }
        commit();
      } else {
        lastTap = now; lastTapX = x; lastTapY = y;
      }
    }

    function build() {
      if (box) return;
      box = document.createElement('div');
      box.className = 'cmt-lightbox';
      pic = document.createElement('img');
      pic.alt = '';
      box.appendChild(pic);

      // 触摸手势：双指捏合缩放（以两指中点为基准）+ 单指拖动（仅放大后）+ 双击缩放
      pic.addEventListener('touchstart', function (e) {
        pic.style.transition = 'none';   // 手势期间关掉过渡，跟手更顺
        if (e.touches.length >= 2) {
          pinch = {
            d: touchDist(e.touches[0], e.touches[1]),
            m: touchMid(e.touches[0], e.touches[1]),
            s: scale, tx: tx, ty: ty
          };
          drag = null;
        } else if (e.touches.length === 1) {
          drag = { x: e.touches[0].clientX, y: e.touches[0].clientY, tx: tx, ty: ty, moved: false };
        }
      }, { passive: true });

      pic.addEventListener('touchmove', function (e) {
        if (pinch && e.touches.length >= 2) {
          e.preventDefault();
          var d = touchDist(e.touches[0], e.touches[1]);
          var m = touchMid(e.touches[0], e.touches[1]);
          scale = Math.max(MIN_S, Math.min(MAX_S, pinch.s * (d / (pinch.d || 1))));
          // 中点位移叠加到起始平移上，捏合更自然
          tx = pinch.tx + (m.x - pinch.m.x);
          ty = pinch.ty + (m.y - pinch.m.y);
          if (scale <= 1) { tx = 0; ty = 0; }
          commit();
        } else if (drag && e.touches.length === 1 && scale > 1) {
          e.preventDefault();
          var t = e.touches[0];
          tx = drag.tx + (t.clientX - drag.x);
          ty = drag.ty + (t.clientY - drag.y);
          if (Math.abs(t.clientX - drag.x) > 6 || Math.abs(t.clientY - drag.y) > 6) drag.moved = true;
          commit();
        }
      }, { passive: false });

      function endTouch(e) {
        pic.style.transition = '';
        if (e.touches && e.touches.length > 0) return;   // 还有手指按着，等全部抬起
        if (pinch) { pinch = null; drag = null; return; }
        if (drag && !drag.moved && e.changedTouches && e.changedTouches.length) {
          var t = e.changedTouches[0];
          onTap(t.clientX, t.clientY);
        }
        drag = null;
      }
      pic.addEventListener('touchend', endTouch);
      pic.addEventListener('touchcancel', endTouch);

      // 右上角关闭按钮（移动端也能点到；点它不应冒泡成「点空白关闭」）
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'cmt-lightbox-close';
      btn.setAttribute('aria-label', '关闭');
      btn.innerHTML = '&times;';
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        close();
      });
      box.appendChild(btn);
      box.addEventListener('click', function (e) { if (e.target === box) close(); });
      document.body.appendChild(box);
      document.addEventListener('keydown', function (e) { if (e.key === 'Escape' || e.keyCode === 27) close(); });
    }
    function open(src, alt) {
      build();
      resetView();
      pic.src = src;
      pic.alt = alt || '';
      document.body.style.overflow = 'hidden';
      box.classList.add('is-open');
    }
    function close() {
      if (!box || !box.classList.contains('is-open')) return;
      box.classList.remove('is-open');
      document.body.style.overflow = '';
      resetView();
    }
    document.addEventListener('click', function (e) {
      var t = e.target;
      if (!t || !t.closest) return;
      var img = t.closest('.cmt-text .cmt-img');
      if (!img) return;
      e.preventDefault();
      open(img.getAttribute('src'), img.getAttribute('alt'));
    });
  })();
})();
