/* 正文图片加载失败：用带说明的占位卡替代破图 */
(function () {
    'use strict';

    var SELECTOR = '.tech-post-body img, .tech-proj-readme-body img';

    function replaceImage(img) {
        if (!img || img.dataset.mediaFallback === '1') return;
        img.dataset.mediaFallback = '1';

        var alt = (img.getAttribute('alt') || '').trim();

        var fallback = document.createElement('span');
        fallback.className = 'md-img-error';
        fallback.setAttribute('role', 'img');
        fallback.setAttribute('aria-label', alt ? '图片暂时无法显示：' + alt : '图片暂时无法显示');
        fallback.title = img.currentSrc || img.src || '';

        var desc = document.createElement('span');
        desc.className = 'md-img-error-desc';
        desc.textContent = '它可能已被移动、删除，或网络暂时不可用。';

        fallback.appendChild(desc);

        // 图片失败时，底部的图片备注也一并隐藏，避免出现“图没了、备注还在”的割裂感
        var figure = img.closest('figure.md-figure');
        if (figure) {
            var caption = figure.querySelector('.md-figure-caption');
            if (caption) caption.remove();
        }

        var parent = img.parentElement;
        // 图片被超链接单独包住时，连链接一起替换，避免点占位卡跳到破图地址
        if (parent && parent.tagName === 'A' && parent.children.length === 1 &&
            !(parent.innerText || '').trim()) {
            parent.replaceWith(fallback);
        } else {
            img.replaceWith(fallback);
        }
    }

    function scan(root) {
        var images = (root || document).querySelectorAll(SELECTOR);
        Array.prototype.forEach.call(images, function (img) {
            if (img.complete && img.naturalWidth === 0) {
                replaceImage(img);
            } else if (!img.complete) {
                img.addEventListener('error', function () { replaceImage(img); }, { once: true });
            }
        });
    }

    // resource 的 error 事件不冒泡，但在捕获阶段可以统一接住
    document.addEventListener('error', function (e) {
        var img = e.target;
        if (!img || img.tagName !== 'IMG' || !img.matches(SELECTOR)) return;
        replaceImage(img);
    }, true);

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { scan(document); });
    } else {
        scan(document);
    }
})();
