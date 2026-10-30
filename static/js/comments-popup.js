/* 评论浮窗驱动（v3.4.33）：后台 comment_display == 'floating' 时由详情页引入。
   页面源码只有左下角 FAB + 空 <dialog>，评论内容开窗时才 fetch 片段端点注入，
   注入后调用 window.initComments(容器) 复用全部评论交互（分页/回复/表情/上传）。
   依赖：comments.js 先加载（提供 initComments）、toast.js（可选提示）。
   深链：#comment-N（外链或提交 302 回来带 hash）自动开窗并定位该楼层。 */
(function () {
  'use strict';

  var fab = document.getElementById('cmt-fab');
  var pop = document.getElementById('cmt-pop');
  var body = document.getElementById('cmt-pop-body');
  if (!fab || !pop || !body) return;

  /* 原生 <dialog>.showModal() 不可用（很老的浏览器）时保持 FAB 隐藏：
     浮窗能力整体不降级，访客仍可在内嵌模式下正常读写评论的场景不存在，
     这里只保证不出现点了没反应的死按钮 */
  if (typeof pop.showModal !== 'function') return;
  fab.hidden = false;

  var loading = false;

  /* 拉取评论片段注入弹窗；focusId 有值时服务端已按该楼层所在页渲染，
     片段 #cmt-region 会带 data-focus 供定位；focusForm 为真时注入后
     展开评论框并聚焦输入框（供页面「反馈」类按钮调用） */
  function load(fragUrl, focusId, focusForm) {
    if (loading || !window.fetch) return;
    loading = true;
    pop.setAttribute('aria-busy', 'true');
    var url = fragUrl + (focusId
      ? (fragUrl.indexOf('?') >= 0 ? '&' : '?') + 'focus=' + encodeURIComponent(focusId)
      : '');
    fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.text();
      })
      .then(function (html) {
        body.innerHTML = html;
        dockForm();
        // 传 pop 而非 body：表单已停靠 foot（body 之外），
        // initComments 以 root 查找表单，范围必须覆盖整个弹窗子树
        if (window.initComments) window.initComments(pop);
        syncTotal();
        revealFocus(focusId);
        if (focusForm) focusCommentForm();
        pop.removeAttribute('aria-busy');
      })
      .catch(function () {
        pop.removeAttribute('aria-busy');
        if (window.toast) window.toast('评论加载失败，请重试', 'error');
      })
      .then(function () {
        loading = false;
      });
  }

  /* 片段自带的大标题已由 CSS 隐藏（与弹窗头部标题重复），
     这里把最新评论总数同步进头部，开窗期间新增评论也不会让头部数字过期 */
  function syncTotal() {
    var num = body.querySelector('.cmt-title .cmt-num');
    var head = pop.querySelector('.cmt-pop-title .cmt-num');
    if (num && head) head.textContent = num.textContent;
  }

  /* 表单固定在弹窗底部：注入后把 #comment-form 与归位锚点一起搬进 .cmt-pop-foot。
     锚点必须同行——comments.js 的 resetReply() 会把回复中的表单插回 anchor 之前，
     两者都在 foot 里，回复取消后表单自动回到固定底部而不是跳回滚动区。
     回复楼层时表单不再搬进楼层（comments.js 检测到 form 在 .cmt-pop-foot 内
     只切「回复 @某某」上下文），foot 常驻不被搬空。
     先清空 foot：上一次开窗的表单还留在里面，不清就会每开一次窗多一个
     「写下你的想法」（append 只增不减）。翻页不走本函数（只换列表区），输入不受影响。 */
  function dockForm() {
    var foot = pop.querySelector('.cmt-pop-foot');
    var formEl = body.querySelector('#comment-form');
    var anchorEl = body.querySelector('#comment-form-anchor');
    if (!foot || !formEl || !anchorEl) return;
    foot.innerHTML = '';
    foot.appendChild(anchorEl);
    foot.appendChild(formEl);
  }

  /* 页面拉到底时页脚（.tech-footer）露出，页脚高过 108px 会压在 FAB 上：
     页脚顶缘进入 FAB 占据区（真正重叠）才淡出让位，滚离底部再恢复。
     常规页脚（约 104px）与抬到 108px 的 FAB 拉到底恰留 4px 间隙，不重叠就保持可见；
     页脚撑得更高（长页脚）由本判断兜底。开窗时的隐藏由 CSS 的
     :has(.cmt-pop[open]) 联动，与本状态互不干扰。 */
  function syncFabNearBottom() {
    var footer = document.querySelector('.tech-footer');
    if (!footer || pop.open) { fab.classList.remove('is-near-bottom'); return; }
    var fr = fab.getBoundingClientRect();
    var near = footer.getBoundingClientRect().top < fr.bottom;
    fab.classList.toggle('is-near-bottom', near);
  }
  window.addEventListener('scroll', syncFabNearBottom, { passive: true });
  window.addEventListener('resize', syncFabNearBottom, { passive: true });
  syncFabNearBottom();

  /* 定位目标楼层：只滚弹窗内容区，背后页面不动；
     复用 comments.js 的高亮闪烁类（样式在 comments-tech.css） */
  function revealFocus(focusId) {
    if (!focusId) return;
    var target = body.querySelector('#comment-' + focusId);
    if (!target) return;
    var delta = target.getBoundingClientRect().top - body.getBoundingClientRect().top - 8;
    body.scrollTop += delta;
    target.classList.add('cmt-anchor-flash');
    setTimeout(function () { target.classList.remove('cmt-anchor-flash'); }, 1600);
  }

  /* 展开评论框（表单字段包在 <details> 折叠容器里）并聚焦输入框；
     表单已由 dockForm 挪进 foot（body 之外），必须在弹窗整棵子树里找 */
  function focusCommentForm() {
    var ta = pop.querySelector('#comment-form textarea');
    if (!ta) return;
    var box = ta.closest('details');
    if (box) box.open = true;
    try { ta.focus({ preventScroll: true }); } catch (e) { try { ta.focus(); } catch (e2) {} }
  }

  /* 每次开窗都重新拉取，保证角标/列表是最新状态 */
  function open(fragUrl, focusId, focusForm) {
    if (!pop.open) pop.showModal();
    load(fragUrl, focusId || '', !!focusForm);
  }

  /* 页面其他控件调用入口（如项目页「反馈 Bug」按钮）：
     window.__cmtOpen(focusId, focusForm) —— 开窗并定位楼层或聚焦输入框 */
  window.__cmtOpen = function (focusId, focusForm) {
    open(fab.getAttribute('data-frag'), focusId || '', !!focusForm);
  };

  fab.addEventListener('click', function () {
    open(fab.getAttribute('data-frag'), '');
  });

  /* 头部关闭钮 + Esc（cancel 事件默认行为即 close） */
  var closeBtn = document.getElementById('cmt-pop-close');
  if (closeBtn) {
    closeBtn.addEventListener('click', function () { pop.close(); });
  }

  /* 点击 ::backdrop 时事件 target 就是 dialog 自身（内容都在子元素里） */
  pop.addEventListener('click', function (e) {
    if (e.target === pop) pop.close();
  });

  /* 键盘遮挡兜底（iOS Safari 等不支持 interactive-widget 的浏览器）：
     软键盘弹出时布局视口不收缩，贴底的 foot（表单）会被键盘盖住。
     监听 visualViewport：可视高度比布局视口矮出一个键盘的量（>80px）时，
     把弹窗整体上移等量，foot 重新露出；键盘收起即复位。
     Android Chrome 108+ 走 viewport meta 的 resizes-content（视口自己收缩，
     overlap 恒为 0），本兜底自然不触发，两者互不干扰。 */
  var vv = window.visualViewport;
  if (vv) {
    var syncKeyboard = function () {
      if (!pop.open) { pop.style.transform = ''; return; }
      var overlap = window.innerHeight - vv.height - vv.offsetTop;
      pop.style.transform = overlap > 80 ? 'translateY(-' + Math.round(overlap) + 'px)' : '';
    };
    vv.addEventListener('resize', syncKeyboard);
    pop.addEventListener('close', function () { pop.style.transform = ''; });
  }

  /* 滚动条默认隐形：滚动时给弹窗挂 .is-scrolling 让滚动条淡入（样式在 comments-popup.css），
     停手 1.2 秒后自动淡出，避免常驻粗滚动条干扰阅读 */
  var scrollTimer;
  body.addEventListener('scroll', function () {
    pop.classList.add('is-scrolling');
    clearTimeout(scrollTimer);
    scrollTimer = setTimeout(function () { pop.classList.remove('is-scrolling'); }, 1200);
  });

  /* 深链：#comment-N —— 页面加载即带 hash（提交后 302 回来 / 外部分享链接），
     以及运行中 hash 变化（页内 @提及 等）都开窗定位 */
  function hashFocus() {
    var m = /^#comment-(\d+)$/.exec(location.hash || '');
    return m ? m[1] : '';
  }
  var startFocus = hashFocus();
  if (startFocus) open(fab.getAttribute('data-frag'), startFocus);
  window.addEventListener('hashchange', function () {
    var fid = hashFocus();
    if (fid) open(fab.getAttribute('data-frag'), fid);
  });
})();
