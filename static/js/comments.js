/* ═══════════════════════════════════════════════
   评论交互（default / tech 两套主题共用）
   依赖：static/js/toast.js（window.toast）
   结构约定：一个 .cmt-thread = 一条根评论 + 它下面全部回复（.cmt-replies 内平铺）
   ── 回复 ──   表单统一挂到「所属楼层组的回复区末尾」，不再插到已有回复之前
   ── 折叠 ──   回复数 > COLLAPSE_AT 时默认只显示 SHOW_COUNT 条
   ── 提示 ──   提交态、字数、待审核提示均由本文件驱动
   ── v3.4.32 ── 由 IIFE 改为 window.initComments(root) 可重入函数：
     整页加载时文件末尾自动执行 initComments(document)；
     v3.4.33 评论浮窗把片段注入 dialog 后，comments-popup.js
     会再次调用 initComments(片段容器)，因此内部查询一律以 root 为根，
     不得假设 id 在整页唯一；document 级委托监听靠 contains 归属判断，多实例互不串扰。
   ═══════════════════════════════════════════════ */
window.initComments = function (root) {
  'use strict';

  root = root || document;
  /* 以 root 为根按 id 查元素：浮窗片段里会出现与页面同名的 id，
     document.getElementById 只会命中第一个，故必须用根限定查询 */
  function byId(id) { return root.querySelector('#' + id); }

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
  var avImgs = root.querySelectorAll('.cmt-avatar-img');
  Array.prototype.forEach.call(avImgs, initAvatar);

  var form = byId('comment-form');
  if (!form) return;
  /* 同一个表单只初始化一次：防止对同一容器重复调用 initComments 时
     document 级委托监听（回复、表情关闭等）被重复绑定 */
  if (form.dataset.cmtInit === '1') return;
  form.dataset.cmtInit = '1';

  function getList() { return byId('cmt-list'); }
  var parentInput = byId('comment-parent-id');
  var hint = byId('comment-replying');
  var hintName = byId('comment-replying-name');
  var cancelBtn = byId('comment-cancel-reply');
  var anchor = byId('comment-form-anchor');
  var textarea = form.querySelector('textarea');
  var submitBtn = form.querySelector('.submit');
  var counter = form.querySelector('.count');
  var fields = byId('comment-fields');
  var remember = byId('comment-remember');
  var editBtn = byId('comment-remember-edit');
  var authorInput = form.querySelector('input[name="author"]');
  var emailInput = byId('comment-email');
  var emailSuggest = byId('cmt-email-suggest');
  var qqAv = byId('cmt-qq-av');

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

    /* 折叠态整卡可点：卡片四周有内边距，原先只有「写评论」那一行是热区，
       点旁边空白没反应。未展开时点击 form 任意位置都展开并聚焦输入框；
       展开后不拦截，summary 收起与表单控件保持原生行为。 */
    form.addEventListener('click', function (e) {
      if (cmtBox.open) return;
      e.preventDefault();
      cmtBox.open = true;
      if (textarea) textarea.focus();
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
    /* 活表单守卫：initComments 每次注入新片段都会重绑本监听（form.dataset.cmtInit
       防重只认元素，新片段是全新表单元素防不住）。旧闭包持有的表单已随 innerHTML
       销毁，不作废的话点「回复」时旧监听器会把脱离文档的旧表单塞回活楼层——
       浮窗每开一次窗就多出一个「写下你的想法」（inline 翻页重渲染同理）。
       当前 DOM 的活表单不是本闭包这只 → 本批监听器整体作废。 */
    if (document.getElementById('comment-form') !== form) return;

    var btn = e.target.closest ? e.target.closest('.cmt-reply') : null;
    var list = getList();
    if (!btn || !list || !list.contains(btn)) return;

    var item = btn.closest('.cmt-item');
    if (!item) return;

    if (parentInput) parentInput.value = btn.getAttribute('data-reply-to') || '';
    if (hintName) hintName.textContent = btn.getAttribute('data-reply-name') || '';
    if (hint) hint.hidden = false;
    var boxEl = form.querySelector('.cmt-box');
    if (boxEl && !boxEl.open) boxEl.open = true;   // 折叠态下点「回复」自动展开表单

    /* 浮窗模式（表单已停靠 .cmt-pop-foot）：输入框常驻弹窗底部，
       点「回复」只切换上下文——hint 变成「回复 @某某」，不把表单搬进楼层，
       视线无需在楼层与底部之间跳（微博 / X / Twikoo 同款交互）。
       给被回复楼层加高亮闪烁，明确回复对象。foot 不再被搬空，保持显示。 */
    if (form.closest('.cmt-pop-foot')) {
      item.classList.add('cmt-anchor-flash');
      setTimeout(function () { item.classList.remove('cmt-anchor-flash'); }, 1600);
    } else {
      /* 内嵌模式保持原交互：表单搬进该楼层组回复区末尾，紧贴被回复内容 */
      var box = repliesBoxOf(item);
      if (!box) return;
      form.classList.add('is-inline');
      box.appendChild(form);   // 追加到末尾，位于已有回复之后
      scrollFormIntoView();
    }
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
    var list = getList();
    if (!list) return;
    Array.prototype.forEach.call(list.querySelectorAll('.cmt-replies'), setupFold);
  }
  setupAllFolds();

  /* ── 2.5 锚点定位：#comment-N 指向被折叠的回复时，先展开所在折叠区再滚动过去 ──
     折叠是用 hidden 实现的，隐藏元素没有布局盒子，浏览器直接跳转只能停在错误位置
     （后台评论管理点击 /projects/1#comment-68 定位不到就是此因）。这里保留折叠，
     仅在带锚点访问时自动展开命中的那一组，并短暂高亮目标。 */
  var crossPageLoading = false;

  /* 跨页锚点兜底：评论分页开启时，#comment-N 可能指向第 2 页及以后的楼层，
     首屏服务端只渲染 cpage（默认第 1 页），DOM 里没有该元素 → 直接定位必然失败。
     这里 fetch 片段端点 ?focus=N（服务端 page_of 算出目标页一次直出）替换列表，
     再走一遍正常定位；任何旧的纯 hash 链接（后台通知/侧栏推荐）都能生效。 */
  function revealHashCrossPage(id) {
    var regionEl = byId('cmt-region');
    if (!regionEl || crossPageLoading || !window.fetch) return;
    if (regionEl.closest && regionEl.closest('dialog')) return;   // 浮窗有自己的 ?focus 链路
    var frag = regionEl.getAttribute('data-frag');
    if (!frag) return;
    crossPageLoading = true;
    fetch(frag + '?focus=' + encodeURIComponent(id), {
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'fetch' }
    })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.text();
      })
      .then(function (text) {
        var fresh = new DOMParser().parseFromString(text, 'text/html').getElementById('cmt-region');
        if (!fresh) return;
        resetReply();   // 与 AJAX 翻页一致：表单先回主位，避免回复态随旧列表被替换
        regionEl.innerHTML = fresh.innerHTML;
        refreshRegion();
        if (document.getElementById('comment-' + id)) revealHashTarget();   // 此次 DOM 已有，正常定位
      })
      .catch(function () { /* 静默失败：保持页面现状，锚点失效但不影响浏览 */ })
      .then(function () { crossPageLoading = false; });
  }

  function revealHashTarget() {
    var hash = location.hash || '';
    if (hash.indexOf('#comment-') !== 0) return;
    var el = document.getElementById(hash.slice(1));
    if (!el) return revealHashCrossPage(hash.slice('#comment-'.length));
    // 逐层向上展开包含它的折叠区（当前结构只有一层，写法兼容未来嵌套）
    var box = el.closest ? el.closest('.cmt-replies') : null;
    while (box) {
      var foldBtn = box.querySelector('.cmt-fold');
      if (foldBtn && foldBtn.getAttribute('aria-expanded') !== 'true') foldBtn.click();
      box = box.parentElement && box.parentElement.closest
        ? box.parentElement.closest('.cmt-replies') : null;
    }
    // 浮窗（<dialog>）内的滚动与高亮由 comments-popup.js 的 revealFocus 负责
    //（它只滚弹窗内容区）；这里再 scrollIntoView 会连带滚动背后页面，两者叠加会错位
    if (el.closest && el.closest('dialog')) return;
    var scroll = function () {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      var target = el.closest('.cmt-thread') || el.closest('.cmt-item') || el;
      target.classList.add('cmt-anchor-flash');
      setTimeout(function () { target.classList.remove('cmt-anchor-flash'); }, 1600);
    };
    if (typeof requestAnimationFrame === 'function') requestAnimationFrame(scroll);
    else setTimeout(scroll, 30);
  }
  revealHashTarget();
  /* hashchange 处理函数内部用 document.getElementById 全局查找，
     天然覆盖浮窗片段；重复调用 initComments 时只绑一次，避免多次展开 */
  if (!window.__cmtHashRevealBound) {
    window.__cmtHashRevealBound = true;
    window.addEventListener('hashchange', revealHashTarget);
  }

  /* ── 2.6 评论分页：只替换评论区，避免整页跳转触发跨文档过渡动画（闪屏） ──
     渐进增强：不支持 fetch / pushState 时，分页链接仍是普通链接，照常整页跳转。 */
  var region = byId('cmt-region');
  var pageLoading = false;

  function prefersReducedMotion() {
    return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }

  /* 吸顶导航会盖住目标位置，按实际高度留出间距 */
  function stickyHeaderHeight() {
    var nav = document.querySelector('.tech-nav, .site-header, header');
    if (!nav) return 12;
    var style = window.getComputedStyle ? window.getComputedStyle(nav) : null;
    var pinned = style && (style.position === 'fixed' || style.position === 'sticky');
    var height = pinned ? nav.getBoundingClientRect().height : 0;
    return height + 12;
  }

  /* 翻页后定位到「评论区开头」（评论标题处），而不是文章顶部 */
  function scrollToCommentsTop() {
    var title = root.querySelector('.cmt-title') || region;
    if (!title) return;
    var current = window.pageYOffset || document.documentElement.scrollTop || 0;
    var top = Math.max(0, title.getBoundingClientRect().top + current - stickyHeaderHeight());
    // 距离过远时直接定位，避免长时间平滑滚动；尊重系统「减弱动态效果」
    var behavior = prefersReducedMotion() || Math.abs(current - top) > 1500 ? 'auto' : 'smooth';
    try {
      window.scrollTo({ top: top, behavior: behavior });
    } catch (err) {
      window.scrollTo(0, top);
    }
  }

  function refreshRegion() {
    var imgs = region.querySelectorAll('.cmt-avatar-img');
    Array.prototype.forEach.call(imgs, initAvatar);
    setupAllFolds();
  }

  function loadCommentPage(url, push) {
    if (!region || !window.fetch || pageLoading) return;
    /* 浮窗（v3.4.33 <dialog>）里的分页：不写浏览器历史、失败不整页跳转、
       翻页只滚浮窗内容区 —— 否则后退会落在裸片段地址、异常会把整页带到 /comment/... */
    var inDialog = !!(region.closest && region.closest('dialog'));
    pageLoading = true;
    region.setAttribute('aria-busy', 'true');
    fetch(url, {
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'fetch' }
    })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.text();
      })
      .then(function (text) {
        var fresh = new DOMParser().parseFromString(text, 'text/html').getElementById('cmt-region');
        if (!fresh) throw new Error('cmt-region not found');
        resetReply();   // 表单先回到主位置，免得回复态表单随旧楼层一起被替换
        region.innerHTML = fresh.innerHTML;
        refreshRegion();
        if (push !== false && !inDialog) {
          var target = url.split('#')[0] + '#comments';
          history.pushState({ cmtPage: target }, '', target);
        }
        if (inDialog) {
          // 浮窗内只滚内容区（dialog 本身是滚动容器），背后页面保持不动
          var scroller = region.closest('.cmt-pop-body') || region.closest('dialog');
          if (scroller) scroller.scrollTop = 0;
        } else {
          scrollToCommentsTop();
        }
      })
      .catch(function (err) {
        if (err && err.name === 'AbortError') return;
        if (inDialog) return;   // 浮窗内静默恢复，用户可再点一次分页
        location.href = url;   // 任何异常都退回整页跳转，保证分页可用
      })
      .then(function () {
        pageLoading = false;
        region.removeAttribute('aria-busy');
      });
  }

  if (region) {
    /* 点击委托绑在 region 上（不绑 document）：
       浮窗片段里会有自己的分页链接，各实例互不串扰 */
    region.addEventListener('click', function (e) {
      var link = e.target.closest ? e.target.closest('a[data-cmt-page]') : null;
      if (!link) return;
      if (e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      loadCommentPage(link.href, true);
    });

    /* popstate 只属于页面级评论区：浮窗走自己的加载逻辑，不参与浏览器历史 */
    if (root === document && !window.__cmtPopBound) {
      window.__cmtPopBound = true;
      window.addEventListener('popstate', function () {
        loadCommentPage(location.href, false);
      });
    }
  }

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

  /* ── 3.2 草稿自动保存 ──
     按表单提交地址（每篇文章/项目各一条）把未提交内容存进 localStorage，
     误刷新、误返回、断电都不丢稿。input 防抖写入；提交校验全部通过
     （即将整页 POST 跳转）时才清除——校验被拦截的分支不清，用户继续编辑。
     服务端异常 redirect 回来时输入本就已丢，与清除时机无关；若后端拦截
     （极少见，客户端已拦敏感词/格式），代价是重写一次，换取成功提交后
     不会误恢复旧稿造成重复评论。 */
  var DRAFT_KEY = 'cmt-draft:' + (form.getAttribute('action') || location.pathname);
  var draftTimer = null;
  function saveDraftSoon() {
    if (!textarea) return;
    clearTimeout(draftTimer);
    draftTimer = setTimeout(function () {
      try {
        if (textarea.value) localStorage.setItem(DRAFT_KEY, textarea.value);
        else localStorage.removeItem(DRAFT_KEY);
      } catch (e) { /* 隐私模式 / 存储配额满：静默放弃，不影响正常评论 */ }
    }, 400);
  }
  if (textarea) {
    textarea.addEventListener('input', saveDraftSoon);
    // 进入页面恢复：仅当输入框为空（用户尚未输入）时注入草稿，不覆盖任何新输入
    var savedDraft = null;
    try { savedDraft = localStorage.getItem(DRAFT_KEY); } catch (e) {}
    if (savedDraft && !textarea.value) {
      textarea.value = savedDraft;
      if (counter) counter.textContent = textarea.value.length + ' / ' + MAX_LEN;
      var draftBox = form.querySelector('.cmt-box');
      if (draftBox) draftBox.open = true;   // 展开评论框让草稿可见
      if (window.toast) window.toast('已恢复上次未提交的评论草稿', 'info', 2500);
    }
  }

  /* ── 3.5 邮箱必填（实名合规要求，无条件）：就地拦截 ── */
  var EMAIL_HINT = '请填写邮箱（必填，用于回复通知与头像）';
  function clearEmailError() {
    if (emailInput) {
      emailInput.classList.remove('is-invalid');
      emailInput.removeAttribute('aria-invalid');
    }
  }
  function showEmailError() {
    if (fields && fields.hidden) {
      fields.hidden = false;
      if (remember) remember.hidden = true;
    }
    if (emailInput) {
      emailInput.classList.add('is-invalid');
      emailInput.setAttribute('aria-invalid', 'true');
      if (emailInput.scrollIntoView) emailInput.scrollIntoView({ block: 'center' });
      emailInput.focus();
    }
    if (window.toast) window.toast(EMAIL_HINT, 'error');
  }
  if (emailInput) emailInput.addEventListener('input', clearEmailError);

  /* ── 4. 提交防重复 + 前置校验 ── */
  if (submitBtn) {
    form.addEventListener('submit', function (ev) {
      if (form.dataset.submitting === '1') {
        ev.preventDefault();
        if (window.toast) window.toast('正在提交，请稍候…', 'info', 2000);
        return;
      }
      if (emailInput && QQ_RE.test(emailInput.value.trim())) {
        emailInput.value = emailInput.value.trim() + '@qq.com';
      }
      if (authorInput) {
        var author = authorInput.value.trim();
        var authorError = '';
        if (/^\d+$/.test(author)) {
          authorError = '昵称不能是纯数字，请换一个';
        } else if (/^(?:https?:\/\/|www\.)/i.test(author)) {
          authorError = '昵称不能以 http://、https:// 或 www. 开头';
        } else if (author) {
          var raw = form.getAttribute('data-sensitive-words') || '';
          if (raw) {
            try {
              var list = JSON.parse(raw);
              if (Object.prototype.toString.call(list) === '[object Array]') {
                var lowAuthor = author.toLowerCase();
                for (var ai = 0; ai < list.length; ai++) {
                  var word = String(list[ai] || '').toLowerCase();
                  if (word && lowAuthor.indexOf(word) >= 0) {
                    authorError = '昵称包含违规词，请换一个';
                    break;
                  }
                }
              }
            } catch (e) {}
          }
        }
        if (authorError) {
          ev.preventDefault();
          if (window.toast) window.toast(authorError, 'error');
          authorInput.focus();
          return;
        }
      }
      // 邮箱无条件必填：与后台校验保持一致，不勾选邮件通知也不能空着提交
      if (emailInput && !emailInput.value.trim()) {
        ev.preventDefault();
        showEmailError();
        return;
      }
      if (!textarea || !textarea.value.trim()) {
        ev.preventDefault();
        if (window.toast) window.toast('请先填写评论内容', 'error');
        textarea && textarea.focus();
        return;
      }
      if (textarea.value.length > MAX_LEN) {
        ev.preventDefault();
        if (window.toast) window.toast('评论内容不能超过 ' + MAX_LEN + ' 字', 'error');
        textarea.focus();
        return;
      }
      // 校验全部通过，即将整页 POST：清除草稿，避免成功后回来误恢复旧稿
      try { localStorage.removeItem(DRAFT_KEY); } catch (e) {}
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

  /* ── 5.5 邮箱通知勾选：仅同步占位/说明文案 ──
     邮箱本身始终必填（实名合规要求），与是否勾选邮件通知无关；
     真正的必填校验在提交事件里做（避免原生 required + 隐藏控件卡死表单） */
  var notifyInput = byId('comment-notify');
  function syncNotify() {
    if (!emailInput) return;
    // 必填状态固定，aria-required 恒为 true
    emailInput.setAttribute('aria-required', 'true');
    if (!notifyInput) return;
    // 勾选邮件通知时提示语强调"接收回复提醒"，未勾选强调"显示头像"，但都必填
    emailInput.placeholder = notifyInput.checked
      ? (emailInput.getAttribute('data-ph-on') || 'QQ 号或邮箱（必填）')
      : (emailInput.getAttribute('data-ph-off') || 'QQ 号或邮箱（必填）');
    emailInput.title = notifyInput.checked
      ? (emailInput.getAttribute('data-title-on') || '评论需填写邮箱：用于接收回复通知与显示头像')
      : (emailInput.getAttribute('data-title-off') || '评论需填写邮箱：用于接收回复通知与显示头像');
  }
  if (notifyInput) {
    notifyInput.addEventListener('change', syncNotify);
    syncNotify();   // 回填记住的选择后同步一次
  } else if (emailInput) {
    syncNotify();   // 没有通知勾选项时也要把 aria-required 置为必填
  }

  /* ── 6. 待审核评论：轻提示引导（页面上已有提示条，这里补一句可关闭的说明） ── */
  var notice = byId('cmt-notice');
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
  var emojiWrap = byId('cmt-emoji');
  var emojiBtn = byId('cmt-emoji-btn');
  var emojiPanel = byId('cmt-emoji-panel');
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

    /* 浮窗模式定位修正：表单停靠在 .cmt-pop-foot（max-height:45dvh 内部滚动，
       overflow-y:auto），面板按 CSS 向上弹出（absolute bottom:100%）会被 foot
       顶部裁掉一截——overflow 容器裁切所有溢出的后代（含 absolute 定位）。
       打开时改用 fixed（脱离裁切链，foot 不滚动时位置稳定）：优先放按钮上方，
       视口放不下改放按钮下方，水平方向夹在视口内；
       内嵌模式无裁切容器，保持 CSS 定位不动 */
    var clearEmojiPos = function () {
      emojiPanel.style.position = '';
      emojiPanel.style.top = '';
      emojiPanel.style.bottom = '';
      emojiPanel.style.left = '';
    };
    var placeEmojiPanel = function () {
      if (!form || !form.closest('.cmt-pop-foot')) return;   // 非浮窗 foot 无需修正
      emojiPanel.style.position = 'fixed';
      emojiPanel.style.bottom = 'auto';
      var btn = emojiBtn.getBoundingClientRect();
      var w = emojiPanel.offsetWidth;
      var h = emojiPanel.offsetHeight;
      var vw = document.documentElement.clientWidth;
      emojiPanel.style.left = Math.max(8, Math.min(btn.left, vw - w - 8)) + 'px';
      var top = btn.top - 8 - h;                       // 8px = CSS 面板与按钮的间距
      if (top < 8) top = Math.min(btn.bottom + 8, window.innerHeight - h - 8);
      emojiPanel.style.top = Math.max(8, top) + 'px';
    };
    var closeEmoji = function () {
      emojiPanel.hidden = true;
      emojiBtn.setAttribute('aria-expanded', 'false');
      clearEmojiPos();
    };
    emojiBtn.addEventListener('click', function () {
      var willOpen = emojiPanel.hidden;
      emojiPanel.hidden = !willOpen;
      emojiBtn.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
      if (willOpen) placeEmojiPanel();
      else clearEmojiPos();   // 再点按钮收起：与 closeEmoji 走同一清理
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
      /* 旧批次作废：本闭包的表情面板已随旧片段销毁，作废避免每开一次窗
         就累积一个空转监听器（同因见回复委托处的活表单守卫） */
      if (!emojiWrap || document.getElementById('cmt-emoji') !== emojiWrap) return;
      if (!emojiWrap.contains(e.target)) closeEmoji();
    });
    document.addEventListener('keydown', function (e) {
      if (!emojiWrap || document.getElementById('cmt-emoji') !== emojiWrap) return;
      if (e.key === 'Escape') closeEmoji();
    });
  }

  /* ── 9. 图片上传：选本地图 → POST 上传 → 以缩略图卡片展示（正文保持纯文字） ──
     上传成功后不往输入框塞 ![](url)，而是把 URL 记入隐藏域 images、在下方显示缩略图；
     用户可继续打字，也能单独删除某张图。提交时由后端合并进评论并做站内白名单校验。 */
  var imgup = byId('cmt-imgup');
  var imgupBtn = byId('cmt-imgup-btn');
  var imgupInput = byId('cmt-imgup-input');
  var imgupList = byId('cmt-imgup-list');
  var imagesInput = byId('comment-images');
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
  var webInput = byId('comment-website');
  var webSuggest = byId('cmt-website-suggest');
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
    /* 全局只建一份灯箱：document 级委托监听天然覆盖浮窗片段，
       重复调用 initComments 时直接跳过，避免第二个灯箱和重复监听 */
    if (window.__cmtLightboxReady) return;
    window.__cmtLightboxReady = true;
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
};

/* 整页加载自动初始化；浮窗片段由 comments-popup.js 手动调 initComments(容器) */
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', function () { window.initComments(document); });
} else {
  window.initComments(document);
}
