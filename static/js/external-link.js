/**
 * 站外链接确认：本站与已收录友链不拦截，其余 http(s) 外链先弹确认。
 */
(function () {
    'use strict';

    var dialog = document.getElementById('techExternal');
    if (!dialog) return;

    var hostEl = document.getElementById('techExternalHost');
    var goBtn = document.getElementById('techExternalGo');
    var closeEls = dialog.querySelectorAll('[data-external-close]');
    var safe = [];
    try {
        var node = document.getElementById('techSafeHosts');
        safe = JSON.parse(node ? node.textContent : '[]') || [];
    } catch (err) {
        safe = [];
    }

    function norm(host) {
        return String(host || '').toLowerCase().replace(/\.$/, '').replace(/^www\./, '');
    }

    var selfHost = norm(location.hostname);
    var safeHosts = safe.map(norm).filter(Boolean);

    function isInternal(host) {
        host = norm(host);
        return host === selfHost || host.endsWith('.' + selfHost);
    }

    function isSafe(host) {
        host = norm(host);
        if (!host || isInternal(host)) return true;
        return safeHosts.some(function (item) {
            return host === item || host.endsWith('.' + item);
        });
    }

    function close() {
        dialog.hidden = true;
        if (goBtn) goBtn.setAttribute('href', '#');
        document.documentElement.classList.remove('tech-external-open');
    }

    function open(url, target) {
        if (hostEl) hostEl.textContent = url.hostname;
        if (goBtn) {
            goBtn.setAttribute('href', url.href);
            goBtn.setAttribute('target', target || '_blank');
        }
        dialog.hidden = false;
        document.documentElement.classList.add('tech-external-open');
        var cancel = dialog.querySelector('[data-external-close]');
        if (cancel) {
            try { cancel.focus({ preventScroll: true }); } catch (e) { cancel.focus(); }
        }
    }

    document.addEventListener('click', function (event) {
        if (event.defaultPrevented || event.button !== 0) return;
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        var target = event.target;
        if (!target || target.nodeType !== 1) return;
        var link = target.closest ? target.closest('a[href]') : null;
        if (!link) return;
        if (link.hasAttribute('data-external-allow')) return;
        if (link.hasAttribute('download')) return;
        var href = link.getAttribute('href') || '';
        if (!/^https?:\/\//i.test(href)) return;
        var url;
        try {
            url = new URL(href, location.href);
        } catch (err) {
            return;
        }
        if (url.protocol !== 'http:' && url.protocol !== 'https:') return;
        if (isSafe(url.hostname)) return;
        event.preventDefault();
        open(url, link.getAttribute('target'));
    });

    Array.prototype.forEach.call(closeEls, function (el) {
        el.addEventListener('click', close);
    });

    if (goBtn) {
        goBtn.addEventListener('click', function () {
            close();
        });
    }

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && !dialog.hidden) close();
    });
})();
