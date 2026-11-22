/* 通知中心 → 右侧滑出「我的概览」抽屉。
   数据源：/api/reader/overview（统计/热力图/一周分布/最近发言/回复/@）
           /api/comment/notifies（未读通知列表）
   身份由服务端按「读者登录 Cookie / 评论 Cookie」解析，前端不接触邮箱。 */
(function () {
  'use strict';

  function int(v, d) { var n = parseInt(v, 10); return isNaN(n) ? d : n; }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  /* ── 动态创建抽屉 DOM（两套主题共用，不依赖模板结构） ── */
  var drawer = document.createElement('div');
  drawer.className = 'ov-root';
  drawer.innerHTML = ''
    + '<div class="ov-mask" data-ov-close></div>'
    + '<aside class="ov-drawer" role="dialog" aria-modal="true" aria-label="我的概览">'
    + '  <div class="ov-head">'
    + '    <strong>我的概览</strong>'
    + '    <div class="ov-head-actions">'
    + '      <button type="button" class="ov-icon" id="ov-refresh" aria-label="刷新" title="刷新">⟳</button>'
    + '      <button type="button" class="ov-icon" data-ov-close aria-label="关闭" title="关闭">×</button>'
    + '    </div>'
    + '  </div>'
    + '  <nav class="ov-tabs" id="ov-tabs">'
    + '    <button type="button" class="ov-tab is-active" data-tab="overview">概览</button>'
    + '    <button type="button" class="ov-tab" data-tab="comments">我的评论</button>'
    + '    <button type="button" class="ov-tab" data-tab="replies">我的回复</button>'
    + '    <button type="button" class="ov-tab" data-tab="mentions">我的@</button>'
    + '  </nav>'
    + '  <div class="ov-body" id="ov-body"><div class="ov-loading">加载中…</div></div>'
    + '</aside>';
  document.body.appendChild(drawer);

  var body = drawer.querySelector('#ov-body');
  var tabs = drawer.querySelector('#ov-tabs');
  var mask = drawer.querySelector('.ov-mask');
  var currentTab = 'overview';
  var open = false;

  /* ── 未读角标（铃铛 + 评论区入口） ── */
  function setBadges(n) {
    n = int(n, 0);
    Array.prototype.forEach.call(document.querySelectorAll('[data-notify-badge],#tech-notify-badge'), function (b) {
      if (n > 0) { b.textContent = n > 99 ? '99+' : String(n); b.hidden = false; }
      else { b.textContent = '0'; b.hidden = true; }
    });
  }
  function loadCount() {
    fetch('/api/comment/notifies', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : { count: 0 }; })
      .then(function (d) { setBadgeCount(d && d.count); })
      .catch(function () {});
  }
  function setBadgeCount(n) { setBadges(n); }

  /* ── 渲染：待处理（待审核 + 未读通知合并成一块） ──
     两者都是「等你处理」的事，各自带标题会占两段留白，合成一个收件箱更紧凑；
     按时间倒序混排，靠标签区分类型。 */
  function renderInbox(pending, pendingCount, notifies) {
    var items = [];
    var pendingIds = {};
    (pending || []).forEach(function (it) {
      pendingIds[int(it.id, 0)] = true;
      items.push({
        kind: 'pending',
        nid: 0,
        url: it.url || '#',
        time: it.created_at || '',
        tag: '待审核',
        desc: '「' + esc(it.text) + '」' + (it.source_title ? ' · ' + esc(it.source_title) : '')
      });
    });
    var unread = 0;
    (notifies || []).forEach(function (it) {
      if (int(it.is_read, 0)) return;
      // 博主视角的来源是待审核 / 新评论动态（comment_notify.admin_feed），
      // 类型不止 reply / approved，标签和文案要按类型分开，不能都写成「回复」。
      var type = it.type || 'reply';
      // admin_feed 的待审核项和「我的待审核」是同一条评论，取一次即可
      if (type === 'pending' && pendingIds[int(it.id, 0)]) return;
      unread += 1;
      var tag = type === 'approved' ? '已通过'
        : type === 'pending' ? '待审核'
          : type === 'new' ? '新评论' : '回复';
      var desc;
      if (type === 'approved') desc = '你的评论「' + esc(it.excerpt) + '」已通过审核';
      else if (type === 'pending') desc = esc(it.from_author) + '：「' + esc(it.excerpt) + '」待审核';
      else if (type === 'new') desc = esc(it.from_author) + ' 新评论：' + esc(it.excerpt);
      else desc = esc(it.from_author) + ' 回复了你：' + esc(it.excerpt);
      items.push({
        kind: 'notify',
        nid: int(it.id, 0),
        url: it.url || '#',
        time: it.created_at || '',
        tag: tag,
        desc: desc
      });
    });
    pendingCount = int(pendingCount, 0);
    var total = pendingCount + unread;
    if (!total) return '';
    items.sort(function (a, b) { return String(b.time).localeCompare(String(a.time)); });
    var html = '<div class="ov-section"><div class="ov-section-head"><span>待处理 · ' + total + '</span>'
      + (unread ? '<button type="button" class="ov-link" data-ov-readall>全部已读</button>' : '')
      + '</div><div class="ov-notif-list">';
    items.forEach(function (it) {
      // 待审核条目没有通知 id，写 0：否则点击会拿评论 id 去标记已读
      html += '<a class="ov-notif" href="' + esc(it.url) + '" data-nid="' + it.nid + '">'
        + '<span class="ov-notif-tag' + (it.kind === 'pending' ? ' is-pending' : '') + '">' + it.tag + '</span>'
        + '<span class="ov-notif-text">' + it.desc + '</span>'
        + '<time>' + esc((it.time || '').slice(5, 16)) + '</time></a>';
    });
    html += '</div>';
    if (pendingCount > (pending || []).length) {
      html += '<div class="ov-tip">还有 ' + (pendingCount - pending.length) + ' 条待审核未显示</div>';
    }
    return html + '</div>';
  }

  /* ── 渲染：统计格子 ── */
  function renderStats(stats) {
    var s = stats || {};
    var cells = [
      { n: s.total || 0, t: '评论数' },
      { n: s.active_30d || 0, t: '活跃30天' },
      { n: s.likes || 0, t: '获赞' },
      { n: s.streak || 0, t: '连续发言' }
    ];
    return '<div class="ov-stats">' + cells.map(function (c) {
      return '<div class="ov-stat"><b>' + c.n + '</b><span>' + c.t + '</span></div>';
    }).join('') + '</div>';
  }

  /* ── 渲染：活跃度热力图（26 周 × 7 天，GitHub 风格） ── */
  function renderHeatmap(heatmap) {
    if (!heatmap || !heatmap.length) return '';
    var levels = ['', ' ov-h1', ' ov-h2', ' ov-h3', ' ov-h4'];
    var html = '<div class="ov-section"><div class="ov-section-head"><span>活跃度</span>'
      + '<span class="ov-section-sub">近 ' + heatmap.length + ' 周，颜色越深发言越多</span></div>'
      + '<div class="ov-heat">';
    heatmap.forEach(function (week) {
      html += '<div class="ov-heat-col">';
      week.forEach(function (cell) {
        var lv = cell.c === 0 ? 0 : cell.c <= 2 ? 1 : cell.c <= 4 ? 2 : cell.c <= 7 ? 3 : 4;
        html += '<i class="ov-heat-cell' + levels[lv] + (cell.f ? ' is-future' : '') + '" title="'
          + esc(cell.d) + ' · ' + cell.c + ' 条"></i>';
      });
      html += '</div>';
    });
    html += '</div><div class="ov-heat-legend"><span>少</span>'
      + levels.map(function (l) { return '<i class="ov-heat-cell' + l + '"></i>'; }).join('')
      + '<span>多</span></div></div>';
    return html;
  }

  /* ── 渲染：一周分布（柱状图） ── */
  function renderWeekly(weekly) {
    if (!weekly || !weekly.length) return '';
    var max = 1;
    weekly.forEach(function (d) { if (d.count > max) max = d.count; });
    var html = '<div class="ov-section"><div class="ov-section-head"><span>一周分布</span>'
      + '<span class="ov-section-sub">按星期统计的发言数量</span></div><div class="ov-weekly">';
    weekly.forEach(function (d) {
      var h = Math.max(4, Math.round(d.count / max * 60));
      html += '<div class="ov-week-col"><div class="ov-week-bar-wrap"><div class="ov-week-bar" style="height:'
        + h + 'px" title="' + d.count + ' 条"></div></div><span>' + esc(d.day) + '</span></div>';
    });
    return html + '</div></div>';
  }

  function renderOverview(d) {
    var u = d.user || {};
    var html = '';
    if (!d.identified) {
      return '<div class="ov-empty"><div class="ov-empty-icon">👤</div><p>还没有识别你的身份</p>'
        + '<span>先发表一条评论（昵称 + 邮箱），或邮箱登录后即可查看你的概览。</span></div>';
    }
    var badge = d.identity_type === 'admin' ? '博主'
      : d.identity_type === 'reader' ? '已验证' : d.identity_type === 'guest' ? '访客' : '';
    html += '<div class="ov-user">'
      + '<img class="ov-avatar" src="' + esc(u.avatar) + '" alt="">'
      + '<div class="ov-user-info"><b>' + esc(u.name) + (badge ? ' <span class="ov-id-badge">' + badge + '</span>' : '') + '</b>'
      + (u.email ? '<span class="ov-user-mail">' + esc(u.email) + '</span>' : '')
      + (u.website ? '<a href="' + esc(u.website) + '" target="_blank" rel="noopener nofollow">' + esc(u.website) + '</a>' : '')
      + '</div></div>';
    html += renderStats(d.stats);
    html += renderInbox(d.pending, d.pending_count, d.notifies || []);
    // 一条评论都没有时，热力图是 26 周空格子、一周分布是 7 根最小值柱，
    // 纯粹占高度；这种情况直接给一句空态，比摆两排空图有意义。
    var hasAny = int((d.stats || {}).total, 0) + int(d.pending_count, 0) > 0;
    if (hasAny) {
      html += renderHeatmap(d.heatmap);
      html += renderWeekly(d.weekly);
    } else {
      html += '<div class="ov-tip">还没有发言记录，参与讨论后这里会出现活跃度。</div>';
    }
    return html;
  }

  function moreButton(tab, nextOffset) {
    return '<button type="button" class="ov-more" data-ov-tab-more="' + tab + '" data-ov-more="' + int(nextOffset, 0) + '">加载更多</button>';
  }

  function renderMyComments(items, hasMore, nextOffset) {
    if (!items || !items.length) {
      return '<div class="ov-empty"><div class="ov-empty-icon">📝</div><p>还没有已通过的评论</p>'
        + '<span>审核中的评论在「概览」里单独列出。</span></div>';
    }
    return '<div class="ov-recent-list">' + items.map(function (it) {
      return '<a class="ov-recent" href="' + esc(it.url || '#') + '">'
        + '<p>' + esc(it.text) + '</p>'
        + '<div class="ov-recent-foot"><span>' + esc(it.source_title) + '</span>'
        + '<time>' + esc((it.created_at || '').slice(0, 16)) + '</time></div></a>';
    }).join('') + '</div>' + (hasMore ? moreButton('comments', nextOffset) : '');
  }

  function renderReplies(items, hasMore, nextOffset) {
    if (!items || !items.length) {
      return '<div class="ov-empty"><div class="ov-empty-icon">↩</div><p>还没有回复</p>'
        + '<span>你回复别人的评论会显示在这里。</span></div>';
    }
    return '<div class="ov-recent-list">' + items.map(function (it) {
      return '<a class="ov-recent" href="' + esc(it.url || '#') + '">'
        + (it.reply_to ? '<div class="ov-recent-to">回复 @' + esc(it.reply_to) + '</div>' : '')
        + '<p>' + esc(it.text) + '</p>'
        + '<div class="ov-recent-foot"><span>' + esc(it.source_title) + '</span>'
        + '<time>' + esc((it.created_at || '').slice(0, 16)) + '</time></div></a>';
    }).join('') + '</div>' + (hasMore ? moreButton('replies', nextOffset) : '');
  }

  function renderMentions(items, hasMore, nextOffset) {
    if (!items || !items.length) {
      return '<div class="ov-empty"><div class="ov-empty-icon">@</div><p>还没有人提到你</p>'
        + '<span>别人回复你的评论会显示在这里。</span></div>';
    }
    return '<div class="ov-recent-list">' + items.map(function (it) {
      return '<a class="ov-recent" href="' + esc(it.url || '#') + '">'
        + '<div class="ov-recent-to">' + esc(it.from_author) + ' 回复了你</div>'
        + '<p>' + esc(it.text) + '</p>'
        + '<div class="ov-recent-foot"><span>' + esc(it.source_title) + '</span>'
        + '<time>' + esc((it.created_at || '').slice(0, 16)) + '</time></div></a>';
    }).join('') + '</div>' + (hasMore ? moreButton('mentions', nextOffset) : '');
  }

  /* ── 加载数据 ── */
  function load(force, recentOffset) {
    body.innerHTML = '<div class="ov-loading">加载中…</div>';
    var url = '/api/reader/overview?tab=' + encodeURIComponent(currentTab)
      + (recentOffset ? '&recent_offset=' + recentOffset : '') + (force ? '&_=' + Date.now() : '');
    fetch(url, { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : {}; })
      .then(function (d) {
        if (currentTab === 'overview') {
          // 概览 tab 同时拉未读通知
          fetch('/api/comment/notifies', { credentials: 'same-origin' })
            .then(function (r) { return r.ok ? r.json() : { notifies: [] }; })
            .then(function (nd) {
              d.notifies = (nd && nd.notifies) || [];
              setBadges(nd && nd.count);
              body.innerHTML = renderOverview(d);
              bindOverviewActions();
              bindTabMore();
            })
            .catch(function () { body.innerHTML = renderOverview(d); bindOverviewActions(); bindTabMore(); });
        } else if (currentTab === 'replies') {
          body.innerHTML = renderReplies(d && d.my_replies, d && d.replies_has_more, d && d.replies_next_offset);
        } else if (currentTab === 'mentions') {
          body.innerHTML = renderMentions(d && d.mentions, d && d.mentions_has_more, d && d.mentions_next_offset);
        } else {
          body.innerHTML = renderMyComments(d && d.my_comments, d && d.comments_has_more, d && d.comments_next_offset);
        }
        bindTabMore();
      })
      .catch(function () { body.innerHTML = '<div class="ov-empty"><p>加载失败，请重试</p></div>'; });
  }

  function bindOverviewActions() {
    var readAll = body.querySelector('[data-ov-readall]');
    if (readAll) readAll.addEventListener('click', function () {
      fetch('/api/comment/notifies/read', { method: 'POST', credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (d) { setBadges(d && d.count); load(true); })
        .catch(function () {});
    });
    Array.prototype.forEach.call(body.querySelectorAll('.ov-notif'), function (a) {
      a.addEventListener('click', function () {
        var id = int(a.getAttribute('data-nid'), 0);
        if (id && a.className.indexOf('is-read') < 0) {
          fetch('/api/comment/notifies/read?id=' + id, { method: 'POST', credentials: 'same-origin' })
            .then(function () { loadCount(); })
            .catch(function () {});
        }
      });
    });
  }

  function itemHtml(it, tab) {
    var lead = '';
    if (tab === 'replies' && it.reply_to) lead = '<div class="ov-recent-to">回复 @' + esc(it.reply_to) + '</div>';
    if (tab === 'mentions') lead = '<div class="ov-recent-to">' + esc(it.from_author) + ' 回复了你</div>';
    return '<a class="ov-recent" href="' + esc(it.url || '#') + '">' + lead
      + '<p>' + esc(it.text) + '</p><div class="ov-recent-foot"><span>' + esc(it.source_title)
      + '</span><time>' + esc((it.created_at || '').slice(0, 16)) + '</time></div></a>';
  }

  /* 概览 tab 的「最近发言」/ 我的评论 / 我的回复 / 我的@ 共用一套分页按钮：
     渲染后可能有多个 .ov-more（概览里「最近发言」与其它区块同屏），
     必须逐个绑定并打标记，避免漏绑或重复绑定导致一次点击请求两次。 */
  function bindTabMore() {
    Array.prototype.forEach.call(body.querySelectorAll('.ov-more'), function (moreBtn) {
      if (moreBtn.getAttribute('data-ov-bound') === '1') return;
      moreBtn.setAttribute('data-ov-bound', '1');
      moreBtn.addEventListener('click', function () {
        var tab = moreBtn.getAttribute('data-ov-tab-more') || 'overview';
        var offset = int(moreBtn.getAttribute('data-ov-more'), 0);
        moreBtn.disabled = true;
        moreBtn.textContent = '加载中…';
        var url = '/api/reader/overview?tab=' + tab + '&offset=' + offset;
        if (tab === 'overview') url = '/api/reader/overview?tab=overview&recent_offset=' + offset;
        fetch(url, { credentials: 'same-origin' })
          .then(function (r) { return r.json(); })
          .then(function (d) {
            var list = body.querySelector('.ov-recent-list');
            var picked = {
              overview: [d && d.recent, d && d.recent_has_more, d && d.recent_next_offset],
              comments: [d && d.my_comments, d && d.comments_has_more, d && d.comments_next_offset],
              replies: [d && d.my_replies, d && d.replies_has_more, d && d.replies_next_offset],
              mentions: [d && d.mentions, d && d.mentions_has_more, d && d.mentions_next_offset]
            }[tab] || [];
            var items = picked[0], more = picked[1], next = picked[2];
            if (list && items) {
              items.forEach(function (it) {
                var wrap = document.createElement('div');
                wrap.innerHTML = itemHtml(it, tab);
                list.appendChild(wrap.firstChild);
              });
            }
            if (more) {
              moreBtn.setAttribute('data-ov-more', int(next, 0));
              moreBtn.disabled = false;
              moreBtn.textContent = '加载更多';
            } else if (moreBtn.parentNode) {
              moreBtn.parentNode.removeChild(moreBtn);
            }
          })
          .catch(function () { moreBtn.disabled = false; moreBtn.textContent = '加载更多'; });
      });
    });
  }

  /* ── 打开 / 关闭抽屉 ── */
  function openDrawer() {
    open = true;
    drawer.classList.add('is-open');
    document.body.classList.add('ov-lock');
    // 每次打开都重新拉取：两次打开之间身份可能已经变了（后台登录 / 退出 / 换账号），
    // 复用旧结果会一直停在「还没有识别你的身份」或旧昵称上。
    load();
  }
  function closeDrawer() {
    open = false;
    drawer.classList.remove('is-open');
    document.body.classList.remove('ov-lock');
  }

  // 铃铛按钮（旧 id）与评论区入口统一走抽屉
  var bellBtn = document.getElementById('tech-notify-btn');
  if (bellBtn) bellBtn.addEventListener('click', function (e) { e.stopPropagation(); openDrawer(); });
  document.addEventListener('click', function (e) {
    var trigger = e.target.closest ? e.target.closest('[data-notify-open]') : null;
    if (trigger) { e.preventDefault(); openDrawer(); }
  });
  Array.prototype.forEach.call(drawer.querySelectorAll('[data-ov-close]'), function (el) {
    el.addEventListener('click', closeDrawer);
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && open) closeDrawer(); });
  var refresh = drawer.querySelector('#ov-refresh');
  if (refresh) refresh.addEventListener('click', function () { load(true); });
  Array.prototype.forEach.call(tabs.querySelectorAll('.ov-tab'), function (tab) {
    tab.addEventListener('click', function () {
      Array.prototype.forEach.call(tabs.querySelectorAll('.ov-tab'), function (t) { t.classList.remove('is-active'); });
      tab.classList.add('is-active');
      currentTab = tab.getAttribute('data-tab');
      load();
    });
  });

  loadCount();
})();
