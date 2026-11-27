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

  /* 抽屉里的图标一律用线性 SVG，不用 emoji（emoji 在 Windows / 不同字体下
     尺寸和基线都不稳，且一眼就是「AI 生成」的味道） */
  var ICONS = {
    user: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>',
    comment: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-8 8H7l-4 3V12a8 8 0 0 1 8-8h2a8 8 0 0 1 8 8z"/><path d="M8 11h8M8 15h5"/></svg>',
    at: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-3.9 7.9"/></svg>',
    clock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
    mailbox: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z"/><path d="m2 7 10 6 10-6"/></svg>',
    refresh: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 4v5h-5"/></svg>',
    close: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>'
  };

  /* ── 动态创建抽屉 DOM（两套主题共用，不依赖模板结构） ── */
  var drawer = document.createElement('div');
  drawer.className = 'ov-root';
  drawer.innerHTML = ''
    + '<div class="ov-mask" data-ov-close></div>'
    + '<aside class="ov-drawer" role="dialog" aria-modal="true" aria-label="我的概览">'
    + '  <div class="ov-head">'
    + '    <div class="ov-head-main">'
    + '      <span class="ov-head-ico" id="ov-head-ico"></span>'
    + '      <div class="ov-head-txt">'
    + '        <small id="ov-head-kicker">概览</small>'
    + '        <strong id="ov-head-title">我的概览</strong>'
    + '        <span id="ov-head-sub">你在所有站点留下的评论足迹</span>'
    + '      </div>'
    + '    </div>'
    + '    <div class="ov-head-actions">'
    + '      <button type="button" class="ov-icon" id="ov-refresh" aria-label="刷新" title="刷新">' + ICONS.refresh + '</button>'
    + '      <button type="button" class="ov-icon" data-ov-close aria-label="关闭" title="关闭">' + ICONS.close + '</button>'
    + '    </div>'
    + '  </div>'
    + '  <div class="ov-body" id="ov-body"><div class="ov-loading">加载中…</div></div>'
    + '  <nav class="ov-nav" id="ov-nav" aria-label="我的面板">'
    + '    <button type="button" class="ov-nav-item is-active" data-tab="overview" aria-current="page">'
    + '      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2 4.5 13.5H11l-1 8.5 8.5-11.5H12z"/></svg>'
    + '      <span>我的概览</span></button>'
    + '    <button type="button" class="ov-nav-item" data-tab="comments">'
    + '      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-8 8H7l-4 3V12a8 8 0 0 1 8-8h2a8 8 0 0 1 8 8z"/><path d="M8 11h8M8 15h5"/></svg>'
    + '      <span>我的评论</span></button>'
    + '    <button type="button" class="ov-nav-item" data-tab="account">'
    + '      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>'
    + '      <span>我的账户</span></button>'
    + '  </nav>'
    + '</aside>';
  document.body.appendChild(drawer);

  var body = drawer.querySelector('#ov-body');
  var tabs = drawer.querySelector('#ov-nav');
  var mask = drawer.querySelector('.ov-mask');
  var currentTab = 'overview';
  var open = false;
  var cmtFilter = 'all';

  /* ── 头部标题：随 tab 切换（对应原站「概览 / 内容 / 我的」小标题） ── */
  var TAB_META = {
    overview: {
      kicker: '概览', title: '我的概览', sub: '你在所有站点留下的评论足迹',
      ico: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2 4.5 13.5H11l-1 8.5 8.5-11.5H12z"/></svg>'
    },
    comments: {
      kicker: '内容', title: '我的评论', sub: '查看你发表过的全部评论和收到的回复',
      ico: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-8 8H7l-4 3V12a8 8 0 0 1 8-8h2a8 8 0 0 1 8 8z"/><path d="M8 11h8M8 15h5"/></svg>'
    },
    account: {
      kicker: '我的', title: '我的账户', sub: '管理个人资料与登录状态',
      ico: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>'
    }
  };

  function setHead(tab) {
    var meta = TAB_META[tab] || TAB_META.overview;
    var ico = drawer.querySelector('#ov-head-ico');
    var kicker = drawer.querySelector('#ov-head-kicker');
    var title = drawer.querySelector('#ov-head-title');
    var sub = drawer.querySelector('#ov-head-sub');
    if (ico) ico.innerHTML = meta.ico;
    if (kicker) kicker.textContent = meta.kicker;
    if (title) title.textContent = meta.title;
    if (sub) sub.textContent = meta.sub;
  }

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
     按时间倒序混排，靠标签区分类型。
     博主与读者的数据源不同：博主 pending 是待审核评论（comment_id），
     notifies 是 admin_notifications（id 才是通知 id）；读者 pending 来自个人概览。 */
  function renderInbox(pending, pendingCount, notifies, unreadTotal) {
    var items = [];
    var pendingIds = {};
    (pending || []).forEach(function (it) {
      var cid = int(it.comment_id != null ? it.comment_id : it.id, 0);
      pendingIds[cid] = true;
      items.push({
        kind: 'pending',
        nid: 0,
        url: it.url || '#',
        time: it.created_at || '',
        tag: '待审核',
        desc: '「' + esc(it.excerpt || it.text || '') + '」'
          + ((it.label || it.source_title) ? ' · ' + esc(it.label || it.source_title) : '')
      });
    });
    var unread = 0;
    (notifies || []).forEach(function (it) {
      if (int(it.is_read, 0)) return;
      var type = it.type || 'reply';
      var cid = int(it.comment_id != null ? it.comment_id : it.id, 0);
      // 同一条待审核评论已经在上面的 pending 里，不再重复
      if (type === 'pending' && pendingIds[cid]) return;
      unread += 1;
      var tag = type === 'approved' ? '已通过'
        : type === 'avatar_approved' ? '头像已通过'
          : type === 'avatar_rejected' ? '头像未通过'
            : type === 'pending' ? '待审核'
              : type === 'new' ? '新评论' : '回复';
      var desc;
      if (type === 'approved') desc = '你的评论「' + esc(it.excerpt) + '」已通过审核';
      else if (type === 'avatar_approved') desc = '你的新头像已通过审核，现已生效';
      else if (type === 'avatar_rejected') desc = '你的新头像未通过审核'
        + (it.excerpt ? '：' + esc(it.excerpt) : '') + '，当前头像保持不变';
      else if (type === 'pending') desc = esc(it.from_author) + '：「' + esc(it.excerpt) + '」待审核';
      else if (type === 'new') desc = esc(it.from_author) + ' 发表了新评论：' + esc(it.excerpt);
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
    // 未读总数可能大于本次返回的列表（接口只取 20 条），角标与标题用总数
    unread = Math.max(unread, int(unreadTotal, 0));
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
    if (unread > (notifies || []).length) {
      html += '<div class="ov-tip">还有 ' + (unread - (notifies || []).length) + ' 条通知未显示</div>';
    }
    return html + '</div>';
  }

  /* ── 渲染：统计格子（2×2，带图标） ── */
  function renderStats(stats) {
    var s = stats || {};
    var ico = {
      comment: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
      active: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>',
      like: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8l1 1L12 21l7.8-7.6 1-1a5.5 5.5 0 0 0 0-7.8z"/></svg>',
      streak: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2s5 5 5 9a5 5 0 0 1-10 0c0-4 5-9 5-9z"/><path d="M12 12s2 1.5 2 3a2 2 0 0 1-4 0c0-1.5 2-3 2-3z"/></svg>'
    };
    var cells = [
      { n: s.total || 0, t: '评论数', i: ico.comment },
      { n: s.active_30d || 0, t: '活跃 30 天', i: ico.active },
      { n: s.likes || 0, t: '获赞', i: ico.like },
      { n: s.streak || 0, t: '连续发言', i: ico.streak }
    ];
    return '<div class="ov-stats">' + cells.map(function (c) {
      return '<div class="ov-stat"><span class="ov-stat-ico">' + c.i + '</span>'
        + '<div class="ov-stat-txt"><b>' + c.n + '</b><span>' + c.t + '</span></div></div>';
    }).join('') + '</div>';
  }

  /* ── 渲染：活跃度热力图（26 周 × 7 天，GitHub 风格） ── */
  function renderHeatmap(heatmap) {
    if (!heatmap || !heatmap.length) return '';
    var levels = ['', ' ov-h1', ' ov-h2', ' ov-h3', ' ov-h4'];
    var total = 0;
    heatmap.forEach(function (week) {
      week.forEach(function (cell) { total += int(cell.c, 0); });
    });
    var html = '<div class="ov-section"><div class="ov-section-head"><span>活跃度</span>'
      + '<span class="ov-section-sub">近 ' + heatmap.length + ' 周 · 共 ' + total + ' 条</span></div>'
      + '<div class="ov-heat-wrap"><div class="ov-heat-days">'
      + ['一', '', '三', '', '五', '', '日'].map(function (d) {
        return '<span>' + d + '</span>';
      }).join('')
      + '</div><div class="ov-heat">';
    heatmap.forEach(function (week) {
      html += '<div class="ov-heat-col">';
      week.forEach(function (cell) {
        var lv = cell.c === 0 ? 0 : cell.c <= 2 ? 1 : cell.c <= 4 ? 2 : cell.c <= 7 ? 3 : 4;
        html += '<i class="ov-heat-cell' + levels[lv] + (cell.f ? ' is-future' : '') + '" title="'
          + esc(cell.d) + ' · ' + cell.c + ' 条"></i>';
      });
      html += '</div>';
    });
    html += '</div></div><div class="ov-heat-legend"><span>少</span>'
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
      html += '<div class="ov-week-col"><div class="ov-week-bar-wrap"><span class="ov-week-num">' + d.count + '</span>'
        + '<div class="ov-week-bar" style="height:' + h + 'px" title="' + d.count + ' 条"></div></div>'
        + '<span>' + esc(d.day) + '</span></div>';
    });
    return html + '</div></div>';
  }

  /* ── 渲染：最近发言（概览底部，复用 recent 数据） ── */
  function renderRecent(items, hasMore, nextOffset) {
    if (!items || !items.length) return '';
    return '<div class="ov-section"><div class="ov-section-head"><span>最近发言</span>'
      + '<span class="ov-section-sub">你最近的评论</span></div><div class="ov-recent-list">'
      + items.map(function (it) {
        var pending = (it.status || '') === 'pending';
        return '<a class="ov-recent" href="' + esc(it.url || '#') + '">'
          + '<p>' + esc(it.text) + '</p>'
          + '<div class="ov-recent-foot"><span>' + esc(it.source_title)
          + (pending ? ' · 审核中' : '') + '</span>'
          + '<time>' + esc((it.created_at || '').slice(0, 16)) + '</time></div></a>';
      }).join('') + '</div>' + (hasMore ? moreButton('overview', nextOffset) : '') + '</div>';
  }

  function renderOverview(d) {
    var u = d.user || {};
    var html = '';
    if (!d.identified) {
      return '<div class="ov-empty"><div class="ov-empty-icon">' + ICONS.user + '</div><p>还没有识别你的身份</p>'
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
    html += renderInbox(d.pending, d.pending_count, d.notifies || [], d.unread_total);
    // 一条评论都没有时，热力图是 26 周空格子、一周分布是 7 根最小值柱，
    // 纯粹占高度；这种情况直接给一句空态，比摆两排空图有意义。
    var hasAny = int((d.stats || {}).total, 0) + int(d.pending_count, 0) > 0;
    if (hasAny) {
      html += renderHeatmap(d.heatmap);
      html += renderWeekly(d.weekly);
    } else {
      html += '<div class="ov-tip">还没有发言记录，参与讨论后这里会出现活跃度。</div>';
    }
    // 最近发言放最后：概览先给待处理，再给趋势，最后才是明细
    html += renderRecent(d.recent, d.recent_has_more, (d.recent || []).length);
    return html;
  }

  function moreButton(tab, nextOffset) {
    return '<button type="button" class="ov-more" data-ov-tab-more="' + tab + '" data-ov-more="' + int(nextOffset, 0) + '">加载更多</button>';
  }

  /* ── 渲染：我的评论（全部 / 提及 / 我的 / 待审） ── */
  function commentCard(it) {
    var pending = (it.status || '') === 'pending';
    var lead = '';
    // mentions 带 from_author（别人回复我）；my_replies 带 reply_to（我回复谁）
    if (it.from_author) lead = '<div class="ov-recent-to">' + esc(it.from_author) + ' 回复了你</div>';
    else if (it.reply_to) lead = '<div class="ov-recent-to">回复 @' + esc(it.reply_to) + '</div>';
    var hay = [(it.text || ''), (it.source_title || ''), (it.from_author || ''), (it.reply_to || '')]
      .join(' ').toLowerCase();
    return '<a class="ov-recent" href="' + esc(it.url || '#') + '" data-s="' + esc(hay) + '">'
      + lead
      + '<p>' + esc(it.text) + '</p>'
      + '<div class="ov-recent-foot"><span>' + esc(it.source_title || '')
      + (pending ? ' · 审核中' : '') + '</span>'
      + '<time>' + esc((it.created_at || '').slice(0, 16)) + '</time></div></a>';
  }

  function commentPool(d) {
    var mine = ((d && d.my_comments) || []).concat((d && d.my_replies) || []);
    var mentions = (d && d.mentions) || [];
    var pending = (d && d.pending) || [];
    if (cmtFilter === 'mention') return mentions;
    if (cmtFilter === 'mine') return mine;
    if (cmtFilter === 'pending') return pending;
    var seen = {}, all = [];
    mine.concat(mentions).forEach(function (it) {
      var key = String(it.id || '') + '|' + String(it.text || '');
      if (seen[key]) return;
      seen[key] = 1;
      all.push(it);
    });
    all.sort(function (a, b) {
      return String(b.created_at || '').localeCompare(String(a.created_at || ''));
    });
    return all;
  }

  function renderCommentsTab(d) {
    var filters = [
      { k: 'all', t: '全部' },
      { k: 'mention', t: '提及' },
      { k: 'mine', t: '我的' },
      { k: 'pending', t: '待审' }
    ];
    var pendingCount = int(d && d.pending_count, 0);
    var html = '<div class="ov-tools">'
      + '<label class="ov-search">'
      + '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>'
      + '<input type="search" id="ov-search" placeholder="搜索关键字…" autocomplete="off"></label>'
      + '<div class="ov-seg">' + filters.map(function (f) {
        return '<button type="button" class="ov-seg-btn' + (f.k === cmtFilter ? ' is-active' : '') + '" data-cmt-filter="' + f.k + '">'
          + f.t + (f.k === 'pending' && pendingCount ? '<em>' + pendingCount + '</em>' : '') + '</button>';
      }).join('') + '</div></div>';

    var pool = commentPool(d);
    if (!pool.length) {
      var emptyMap = {
        all: [ICONS.comment, '还没有评论', '发布评论后，你和别人的互动都会出现在这里。'],
        mention: [ICONS.at, '还没有人回复你', '别人回复你的评论后会显示在这里。'],
        mine: [ICONS.comment, '还没有已通过的评论', '审核通过的评论会显示在这里。'],
        pending: [ICONS.clock, '没有待审评论', '新评论审核通过前会先放在这里。']
      };
      var e = emptyMap[cmtFilter] || emptyMap.all;
      return html + '<div class="ov-empty"><div class="ov-empty-icon">' + e[0] + '</div><p>' + e[1] + '</p><span>' + e[2] + '</span></div>';
    }
    return html + '<div class="ov-recent-list" id="ov-cmt-list">' + pool.map(commentCard).join('') + '</div>';
  }

  /* ── 渲染：我的账户（身份 / 登录入口） ── */
  function renderAccount(d) {
    if (!d || !d.identified) {
      var canLogin = !!document.querySelector('[data-login-open],#cmt-login-open');
      return '<div class="ov-acc">'
        + '<div class="ov-acc-card"><div class="ov-acc-row">'
        + '<span class="ov-acc-ico"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg></span>'
        + '<div class="ov-acc-txt"><b>访客身份</b><span>你正以访客身份浏览：登录后即可管理个人资料、密码与第三方登录，换台设备也能找回自己的评论。</span></div>'
        + '</div>'
        + (canLogin ? '<button type="button" class="ov-acc-btn" data-ov-login>登录</button>' : '')
        + '</div>'
        + '<p class="ov-tip">不登录也能评论，填写昵称和邮箱即可；登录只是为了让身份跨设备同步。</p>'
        + '</div>';
    }
    var u = d.user || {};
    var badge = d.identity_type === 'admin' ? '博主'
      : d.identity_type === 'reader' ? '已验证' : d.identity_type === 'guest' ? '访客' : '';
    var stats = d.stats || {};
    var rows = [
      { t: '昵称', v: u.name || '' },
      { t: '邮箱', v: u.email || '' },
      { t: '身份', v: badge },
      { t: '评论总数', v: String(stats.total || 0) },
      { t: '覆盖站点', v: u.sources != null ? String(u.sources) : '' },
      { t: '首次发言', v: (u.first_at || '').slice(0, 10) }
    ];
    return '<div class="ov-acc">'
      + '<div class="ov-user"><img class="ov-avatar" src="' + esc(u.avatar) + '" alt="">'
      + '<div class="ov-user-info"><b>' + esc(u.name) + (badge ? ' <span class="ov-id-badge">' + badge + '</span>' : '') + '</b>'
      + (u.email ? '<span class="ov-user-mail">' + esc(u.email) + '</span>' : '')
      + '</div></div>'
      + '<div class="ov-acc-card"><div class="ov-acc-list">' + rows.map(function (r) {
        if (!r.v) return '';
        return '<div class="ov-acc-item"><span>' + r.t + '</span><b>' + esc(r.v) + '</b></div>';
      }).join('') + '</div></div>'
      // 注册用户：资料卡下面直接给管理入口，不用再回评论区找「管理账号」
      + (d.identity_type === 'reader'
        ? '<div class="ov-acc-actions">'
          + '<button type="button" class="ov-acc-btn" data-ov-manage>管理账号</button>'
          + '<button type="button" class="ov-acc-btn ov-acc-btn--ghost" data-ov-logout>退出登录</button>'
          + '</div>'
        : '')
      + '<p class="ov-tip">' + (d.identity_type === 'reader'
        ? '当前为注册账号登录，身份与评论会自动同步。'
        : d.identity_type === 'admin'
          ? '当前为博主身份，评论与通知按博主视角展示。'
          : '当前身份来自评论 Cookie（昵称 + 邮箱），换设备或清理 Cookie 后需要重新填写。')
      + '</p></div>';
  }

  /* ── 加载数据 ── */
  function load(force, recentOffset) {
    setHead(currentTab);
    body.innerHTML = '<div class="ov-loading">加载中…</div>';
    var url = '/api/reader/overview?tab=overview'
      + (recentOffset ? '&recent_offset=' + recentOffset : '') + (force ? '&_=' + Date.now() : '');
    fetch(url, { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : {}; })
      .then(function (d) {
        if (currentTab === 'overview') {
          // 概览 tab 同时拉未读通知
          fetch('/api/comment/notifies', { credentials: 'same-origin' })
            .then(function (r) { return r.ok ? r.json() : { notifies: [] }; })
            .then(function (nd) {
              // 博主与读者的待处理数据源不同：博主用接口返回的待审核列表，
              // 读者继续用个人概览里的 pending（自己的审核中评论）
              if (nd && nd.is_admin) {
                d.pending = nd.pending || [];
                d.pending_count = int(nd.pending_count, 0);
                // 接口给的总数可能大于列表返回的条数，角标和标题都以总数为准
                d.unread_total = Math.max(0, int(nd.count, 0) - int(nd.pending_count, 0));
              }
              d.notifies = (nd && nd.notifies) || [];
              setBadges(nd && nd.count);
              body.innerHTML = renderOverview(d);
              bindOverviewActions();
              bindTabMore();
            })
            .catch(function () { body.innerHTML = renderOverview(d); bindOverviewActions(); bindTabMore(); });
        } else if (currentTab === 'account') {
          body.innerHTML = renderAccount(d);
          bindAccount(d);
        } else {
          loadCommentsData(d);
        }
      })
      .catch(function () { body.innerHTML = '<div class="ov-empty"><p>加载失败，请重试</p></div>'; });
  }

  /* 我的评论：一次并行拉三类列表，筛选与搜索都在本地做，切换不闪 */
  function loadCommentsData(base) {
    var stamp = '&_=' + Date.now();
    var urls = [
      '/api/reader/overview?tab=comments' + stamp,
      '/api/reader/overview?tab=replies' + stamp,
      '/api/reader/overview?tab=mentions' + stamp
    ];
    Promise.all(urls.map(function (u) {
      return fetch(u, { credentials: 'same-origin' }).then(function (r) { return r.ok ? r.json() : {}; });
    })).then(function (arr) {
      var d = {};
      for (var k in base) if (Object.prototype.hasOwnProperty.call(base, k)) d[k] = base[k];
      d.my_comments = (arr[0] && arr[0].my_comments) || [];
      d.my_replies = (arr[1] && arr[1].my_replies) || [];
      d.mentions = (arr[2] && arr[2].mentions) || [];
      body.innerHTML = renderCommentsTab(d);
      bindCommentsTab(d);
    }).catch(function () {
      body.innerHTML = renderCommentsTab(base);
      bindCommentsTab(base);
    });
  }

  function bindCommentsTab(d) {
    Array.prototype.forEach.call(body.querySelectorAll('[data-cmt-filter]'), function (btn) {
      btn.addEventListener('click', function () {
        cmtFilter = btn.getAttribute('data-cmt-filter') || 'all';
        body.innerHTML = renderCommentsTab(d);
        bindCommentsTab(d);
      });
    });
    var search = body.querySelector('#ov-search');
    if (!search) return;
    var apply = function () {
      var q = String(search.value || '').trim().toLowerCase();
      var list = body.querySelector('#ov-cmt-list');
      if (!list) return;
      var shown = 0;
      Array.prototype.forEach.call(list.querySelectorAll('.ov-recent'), function (a) {
        var hit = !q || String(a.getAttribute('data-s') || '').indexOf(q) >= 0;
        a.style.display = hit ? '' : 'none';
        if (hit) shown += 1;
      });
      var tip = list.querySelector('.ov-search-empty');
      if (!shown && !tip) {
        tip = document.createElement('div');
        tip.className = 'ov-tip ov-search-empty';
        tip.textContent = '没有匹配「' + q + '」的内容';
        list.appendChild(tip);
      } else if (shown && tip) {
        tip.remove();
      }
    };
    search.addEventListener('input', apply);
  }

  function bindAccount() {
    var login = body.querySelector('[data-ov-login]');
    if (login) login.addEventListener('click', function () {
      closeDrawer();
      var trigger = document.querySelector('[data-login-open],#cmt-login-open');
      if (trigger) trigger.click();
    });
    // 注册用户：管理账号直接拉起评论区的账号浮窗
    var manage = body.querySelector('[data-ov-manage]');
    if (manage) manage.addEventListener('click', function () {
      closeDrawer();
      var trigger = document.getElementById('cmt-account-open');
      if (trigger) trigger.click();
    });
    var logout = body.querySelector('[data-ov-logout]');
    if (logout) logout.addEventListener('click', function () {
      logout.disabled = true;
      fetch('/api/reader/logout', { method: 'POST', credentials: 'same-origin' })
        .then(function () { window.location.reload(); })
        .catch(function () { window.location.reload(); });
    });
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
          fetch('/api/comment/notifies/read?id=' + id, { method: 'POST', credentials: 'same-origin', keepalive: true })
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
      + (tab === 'overview' && (it.status || '') === 'pending' ? ' · 审核中' : '')
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
  Array.prototype.forEach.call(tabs.querySelectorAll('.ov-nav-item'), function (tab) {
    tab.addEventListener('click', function () {
      Array.prototype.forEach.call(tabs.querySelectorAll('.ov-nav-item'), function (t) {
        t.classList.remove('is-active');
        t.removeAttribute('aria-current');
      });
      tab.classList.add('is-active');
      tab.setAttribute('aria-current', 'page');
      currentTab = tab.getAttribute('data-tab') || 'overview';
      load();
    });
  });

  // 评论区 / 铃铛都不存在时不发请求（评论开关关闭时后台不再加载这个脚本）
  if (bellBtn || document.querySelector('[data-notify-open]')) loadCount();
})();
