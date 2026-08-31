/**
 * infowe Blog - 状态页（/status）轮询脚本
 * 每 60 秒拉取 /api/status，增量更新服务可用性、云资源到期时间与最近更新时间。
 */
(function () {
  'use strict';

  var INTERVAL = 60000; // 轮询间隔：60s

  function pad(n) {
    return n < 10 ? '0' + n : '' + n;
  }

  /** unix 秒 -> 相对时间（刚刚 / N 分钟前 / N 小时前 / 日期时间） */
  function fmtTime(ts) {
    if (!ts) return '待探测';
    var ms = ts * 1000;
    var diff = (Date.now() - ms) / 1000;
    if (diff < 60) return '刚刚';
    if (diff < 3600) return Math.floor(diff / 60) + ' 分钟前';
    if (diff < 86400) return Math.floor(diff / 3600) + ' 小时前';
    var d = new Date(ms);
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
      ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  }

  /** 用最新数据渲染服务行 / 云资源卡片（SSR 与轮询共用） */
  function render(expiry, services, generatedAt) {
    // ── 在线服务列表 ──
    document.querySelectorAll('.svc-row[data-svc-name]').forEach(function (row) {
      var name = row.getAttribute('data-svc-name');
      var svc = null;
      for (var i = 0; i < services.length; i++) {
        if (services[i].name === name) { svc = services[i]; break; }
      }
      if (!svc) return;

      // 状态指示灯
      var dot = row.querySelector('.svc-dot');
      if (dot) {
        dot.classList.remove('st-ok', 'st-warn', 'st-down', 'st-none');
        dot.classList.add(svc.ok === true ? 'st-ok' : (svc.ok === false ? 'st-down' : 'st-none'));
      }
      // 延迟 / SSL / 可用率
      var lat = row.querySelector('[data-field="latency"]');
      if (lat) lat.textContent = svc.latency_ms !== null && svc.latency_ms !== undefined ? (svc.latency_ms + ' ms') : '—';
      var cert = row.querySelector('[data-field="cert"]');
      if (cert) cert.textContent = svc.cert_days !== null && svc.cert_days !== undefined && svc.cert_days >= 0 ? (svc.cert_days + ' 天') : '—';
      var upt = row.querySelector('[data-field="uptime"]');
      if (upt) upt.textContent = svc.uptime !== null && svc.uptime !== undefined ? (svc.uptime + '%') : '—';
    });

    // ── 在线计数 ──
    var online = 0;
    for (var j = 0; j < services.length; j++) {
      if (services[j].ok === true) online++;
    }
    var countEl = document.getElementById('svc-count');
    if (countEl && services.length) countEl.textContent = online + '/' + services.length + ' 在线';

    // ── 云资源到期行 ──
    if (expiry) {
      document.querySelectorAll('[data-expiry-key]').forEach(function (row) {
        var key = row.getAttribute('data-expiry-key');
        var info = expiry[key];
        if (!info) return;
        var st = info.status || 'none';
        ['ok', 'warn', 'expired', 'none'].forEach(function (c) { row.classList.remove('st-' + c); });
        row.classList.add('st-' + st);
        var dot = row.querySelector('.svc-dot');
        if (dot) {
          ['ok', 'warn', 'expired', 'down', 'none'].forEach(function (c) { dot.classList.remove('st-' + c); });
          dot.classList.add('st-' + st);
        }
        var dateEl = row.querySelector('[data-expiry-field="date"]');
        if (dateEl) dateEl.textContent = info.expiry || '—';
        var badgeEl = row.querySelector('[data-expiry-field="badge"]');
        if (badgeEl) {
          badgeEl.className = 'svc-metric';
          badgeEl.textContent = st === 'ok' ? '正常'
            : (st === 'warn' ? '即将到期' : (st === 'expired' ? '已到期' : '未配置'));
        }
      });
    }

    // ── 更新提示 ──
    var hint = document.getElementById('status-hint');
    if (hint && generatedAt) {
      hint.textContent = '数据每 5 分钟自动探测 · 最近更新 ' + fmtTime(generatedAt) + ' · 页面每 60 秒自动刷新';
    }
  }

  function poll() {
    fetch('/api/status', { cache: 'no-store' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        render(data.expiry || {}, data.services || [], data.generated_at);
      })
      .catch(function () { /* 静默失败，等待下一个轮询周期 */ });
  }

  // 首屏延迟 1s 拉取一次（待页面挂载完成），随后进入固定轮询
  setTimeout(poll, 1000);
  setInterval(poll, INTERVAL);
})();