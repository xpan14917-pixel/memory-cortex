/* live.js — ?live=1 时每 3 秒拉一次 /api/state，更新面板上的数字。
   记忆条数变化时整页刷新一次（3D 场景按新数据重建，比增量改缓冲稳）。 */
(function () {
  'use strict';
  if (!/[?&]live=1/.test(location.search)) return;

  const POLL_MS = 3000;
  let lastMemCount = null;
  let lastOk = 0;

  function badge(text, color) {
    const src = document.querySelector('.brand-right .src');
    if (!src) return;
    src.innerHTML = 'LIVE · ' + text;
    src.style.color = color || '#67f0b5';
  }

  function toast(text) {
    let el = document.getElementById('live-toast');
    if (!el) {
      el = document.createElement('div');
      el.id = 'live-toast';
      el.style.cssText = 'position:fixed;left:50%;top:78px;transform:translateX(-50%);z-index:80;' +
        'padding:7px 14px;background:rgba(8,16,30,.9);border:1px solid rgba(120,220,255,.4);' +
        'color:#cdf1ff;font-size:12px;letter-spacing:.1em;pointer-events:none';
      document.body.appendChild(el);
    }
    el.textContent = text;
    el.style.opacity = '1';
    clearTimeout(el._t);
    el._t = setTimeout(() => { el.style.opacity = '0'; }, 2200);
  }

  async function pull() {
    try {
      const r = await fetch('api/state', { cache: 'no-store' });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const s = await r.json();
      if (s.error) throw new Error(s.error);
      lastOk = Date.now();
      badge('已连接 · ' + (s.serverTime || '').slice(11, 19), '#67f0b5');

      const n = s.counts ? s.counts.memories : null;
      if (lastMemCount === null) lastMemCount = n;
      else if (n !== lastMemCount) {
        toast('记忆数变化 ' + lastMemCount + ' → ' + n + '，重建场景…');
        setTimeout(() => location.reload(), 900);
        return;
      }

      window.HUD.applyLive(s);
    } catch (e) {
      badge('连接断开 · ' + (e.message || e), '#ff8f9e');
    }
  }

  function tick() {
    if (document.hidden) return;
    pull();
  }

  badge('连接中…', '#8fb6d8');
  pull();
  setInterval(tick, POLL_MS);
  setInterval(() => {
    if (lastOk && Date.now() - lastOk > 15000) badge('连接超时', '#ff8f9e');
  }, 5000);
})();
