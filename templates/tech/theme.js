/* tech 主题交互：主题切换、移动端抽屉菜单、回到顶部 */
(function () {
  'use strict';

  /* ── 主题切换（与后台一致的 infowe-theme 机制） ── */
  var toggle = document.getElementById('theme-toggle');
  if (toggle) {
    toggle.addEventListener('click', function () {
      var cur = document.documentElement.getAttribute('data-theme');
      var next = cur === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      try { localStorage.setItem('infowe-theme', next); } catch (e) {}
    });
  }

  /* ── 移动端抽屉菜单 ── */
  var burger = document.getElementById('tech-burger');
  var overlay = document.getElementById('tech-drawer-overlay');
  var drawer = document.getElementById('tech-drawer');
  var closeBtn = document.getElementById('tech-drawer-close');

  function openDrawer() {
    overlay.classList.add('open');
    drawer.classList.add('open');
    document.body.style.overflow = 'hidden';
  }
  function closeDrawer() {
    overlay.classList.remove('open');
    drawer.classList.remove('open');
    document.body.style.overflow = '';
  }

  if (burger && overlay && drawer) {
    burger.addEventListener('click', openDrawer);
    overlay.addEventListener('click', closeDrawer);
    if (closeBtn) closeBtn.addEventListener('click', closeDrawer);
    drawer.querySelectorAll('a').forEach(function (a) {
      a.addEventListener('click', closeDrawer);
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeDrawer();
    });
  }

  /* ── 回到顶部 ── */
  var topBtn = document.getElementById('tech-top');
  if (topBtn) {
    window.addEventListener('scroll', function () {
      topBtn.classList.toggle('show', window.scrollY > 400);
    }, { passive: true });
    topBtn.addEventListener('click', function () {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }
})();