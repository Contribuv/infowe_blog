/**
 * 禁用移动端网页缩放（配合 viewport user-scalable=no）。
 * iOS 10+ 起 Safari 忽略 user-scalable=no，必须再拦截 gesturestart 才能禁双指捏合。
 */
(function () {
    'use strict';
    if (typeof window === 'undefined') return;
    // 阻止双指捏合缩放
    document.addEventListener('gesturestart', function (e) { e.preventDefault(); });
    // 阻止双击放大（iOS 上双击仍可能缩放）
    var lastTap = 0;
    document.addEventListener('touchend', function (e) {
        var now = Date.now();
        if (now - lastTap < 400) {
            e.preventDefault();
        }
        lastTap = now;
    }, { passive: false });
})();
