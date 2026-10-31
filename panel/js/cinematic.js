/* ============================================================
   cinematic.js — 镜头编排 / 演绎模式 / 录制模式
   ============================================================ */
window.Cine = (function () {
  'use strict';
  const B = window.BRAIN;
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
  const smooth = (x) => x * x * (3 - 2 * x);

  const DURATION = 42;

  /* yaw, pitch, dist, target[x,y,z], fov */
  const KEYS = [
    { t: 0.0, yaw: 0.72, pitch: 0.28, dist: 32.0, target: [0.7, 0.9, 0.0], fov: 45 },
    { t: 4.5, yaw: 0.46, pitch: 0.15, dist: 24.6, target: [0.6, 0.45, 0.0], fov: 42 },
    { t: 9.0, yaw: 0.20, pitch: 0.05, dist: 20.2, target: [0.35, 0.55, 0.15], fov: 40 },
    { t: 13.5, yaw: 0.03, pitch: -0.02, dist: 17.6, target: [0.30, 0.75, -0.20], fov: 38 },
    { t: 17.5, yaw: -0.14, pitch: -0.16, dist: 15.8, target: [0.25, 0.35, -0.10], fov: 38 },
    { t: 21.5, yaw: -0.06, pitch: -0.10, dist: 16.2, target: [0.20, -0.55, 0.45], fov: 39 },
    { t: 25.5, yaw: -0.26, pitch: -0.26, dist: 16.8, target: [0.20, -1.35, 0.75], fov: 40 },
    { t: 29.5, yaw: -0.46, pitch: -0.02, dist: 19.6, target: [0.50, -0.45, 0.25], fov: 41 },
    { t: 33.5, yaw: -0.30, pitch: 0.18, dist: 23.0, target: [0.70, 0.25, 0.0], fov: 42 },
    { t: 37.5, yaw: 0.02, pitch: 0.10, dist: 20.0, target: [0.60, 0.30, 0.0], fov: 41 },
    { t: 42.0, yaw: 0.36, pitch: 0.085, dist: 17.6, target: [0.55, 0.25, 0.0], fov: 40 },
  ];

  const S = {
    active: false, capture: false, t: 0, mode: 'live',
    fade: 1, bloom: 1.0, exposure: 1.0, ca: 0.34, grain: 0.045,
    introStart: 0, recallDone: false, tagShown: false,
  };

  let tagEl = null;

  function init() {
    tagEl = document.createElement('div');
    tagEl.id = 'tagline';
    tagEl.innerHTML = '<span>她记得的，比你以为的多。</span><em>SHE REMEMBERS MORE THAN YOU THINK</em>';
    document.getElementById('app').appendChild(tagEl);
  }

  function cameraAt(t) {
    let i = 0;
    while (i < KEYS.length - 2 && t > KEYS[i + 1].t) i++;
    const a = KEYS[i], b = KEYS[i + 1];
    const u = smooth(clamp((t - a.t) / (b.t - a.t), 0, 1));
    const lerp = (x, y) => x + (y - x) * u;
    return {
      yaw: lerp(a.yaw, b.yaw) + Math.sin(t * 0.23) * 0.008,
      pitch: lerp(a.pitch, b.pitch) + Math.sin(t * 0.31 + 1.2) * 0.005,
      dist: lerp(a.dist, b.dist) + Math.sin(t * 0.19) * 0.10,
      target: [
        lerp(a.target[0], b.target[0]),
        lerp(a.target[1], b.target[1]),
        lerp(a.target[2], b.target[2]),
      ],
      fov: lerp(a.fov, b.fov),
    };
  }

  function setOp(sel, v) {
    const e = typeof sel === 'string' ? document.querySelector(sel) : sel;
    if (e) e.style.opacity = String(clamp(v, 0, 1));
  }
  const fadeIn = (t, start, dur) => { const x = clamp((t - start) / (dur || 0.9), 0, 1); return smooth(x); };

  /* ---------------- timeline ---------------- */
  function update(t) {
    S.t = t;
    if (!S.active) return;
    const cam = cameraAt(t);
    const C = window.Scene.cam;
    C.yaw = cam.yaw; C.pitch = cam.pitch; C.dist = cam.dist; C.fov = cam.fov;
    C.target = cam.target;

    window.Scene.state.reveal = clamp((t - 1.0) / 3.4, 0, 1);

    /* HUD reveal choreography */
    setOp('#brand', fadeIn(t, 1.3, 1.1));
    setOp('#legend', fadeIn(t, 3.2, 0.8));
    setOp('#persona', fadeIn(t, 8.2, 1.0));
    setOp('#stream', fadeIn(t, 10.4, 1.0));
    setOp('#dock', fadeIn(t, 12.2, 1.0));
    window.HUD.S.reveal.labels = fadeIn(t, 4.0, 1.4);

    /* boot overlay */
    const boot = document.getElementById('boot');
    if (boot) {
      const o = 1 - fadeIn(t, 1.5, 0.7);
      boot.style.opacity = o.toFixed(3);
      boot.style.pointerEvents = o > 0.01 ? 'auto' : 'none';
      const lines = boot.querySelectorAll('.boot-line');
      lines.forEach((l, i) => { l.style.opacity = t > 0.16 + i * 0.28 ? '1' : '0'; l.style.transform = 'none'; });
      const bar = boot.querySelector('.boot-bar i');
      if (bar) bar.style.width = (clamp((t - 0.2) / 1.1, 0, 1) * 100).toFixed(1) + '%';
      const title = boot.querySelector('.boot-title');
      if (title) title.style.opacity = String(fadeIn(t, 0.75, 0.6));
      const sub = boot.querySelector('.boot-sub');
      if (sub) sub.style.opacity = String(fadeIn(t, 1.05, 0.6));
    }

    /* exposure / fade */
    S.fade = fadeIn(t, 0.0, 1.1) * (1 - fadeIn(t, 40.9, 1.1) * 0.95);
    S.bloom = 0.72 + 0.30 * (fadeIn(t, 8.8, 2.2) * (1 - fadeIn(t, 15.0, 2.0)))
      + 0.18 * fadeIn(t, 21.0, 0.8) * (1 - fadeIn(t, 28.0, 2.0));
    S.exposure = 1.00 + 0.10 * fadeIn(t, 1.0, 3.0);
    S.ca = 0.32 + 0.22 * fadeIn(t, 12.0, 4.0);

    /* recall sequence */
    const rc = B.recall;
    if (t > 21.6 && !S.recallDone) {
      S.recallDone = true;
      window.Scene.state.packet = {
        progress: 0,
        path: [rc.node.pos, [rc.node.pos[0] * 0.6, (rc.node.pos[1] + B.hub.pos[1]) / 2, (rc.node.pos[2] + B.hub.pos[2]) / 2],
               B.hub.pos, B.regionById.expression.pos],
      };
      window.HUD.showCard(rc.node, true);
      window.HUD.pushStream('召回', '长期记忆库 #038 → 大脑中枢 · 命中', false);
    }
    if (S.recallDone) {
      const p = window.Scene.state.packet;
      if (p) {
        p.progress = clamp((t - 21.7) / 2.6, 0, 1);
        if (t > 24.6) window.Scene.state.packet = null;
      }
      if (t > 24.4 && !S.recallDone2) {
        S.recallDone2 = true;
        window.HUD.pushStream('表达', '「和真人一样……这句话让我心里软了一下呢」', false);
      }
      if (t > 28.4) window.HUD.hideCard();
    }

    /* card fade (css transitions are disabled while capturing) */
    const cardEl = document.getElementById('card');
    if (cardEl) {
      if (t > 21.5) {
        cardEl.style.opacity = (fadeIn(t, 21.75, 0.55) * (1 - fadeIn(t, 28.1, 0.7))).toFixed(3);
      } else if (cardEl.style.opacity) {
        cardEl.style.opacity = '0';
      }
    }

    /* tagline */
    if (tagEl) {
      const a = fadeIn(t, 35.2, 1.3) * (1 - fadeIn(t, 40.2, 1.3));
      tagEl.style.opacity = a.toFixed(3);
      tagEl.style.transform = `translate(-50%, ${(1 - a) * 8}px)`;
    }
  }

  /* ---------------- public ---------------- */
  function startShowcase() {
    S.active = true;
    window.HUD.resetView();
    const boot = document.getElementById('boot');
    if (boot) boot.classList.remove('done');
  }
  function stopShowcase() {
    S.active = false;
    S.recallDone = false; S.recallDone2 = false;
    window.HUD.resetView();
    allVisible();
  }

  function toggleShowcase() {
    if (S.active) { stopShowcase(); return; }
    S.active = true; S.t = 0; S.recallDone = false; S.recallDone2 = false;
    window.Scene.cam.yaw = KEYS[0].yaw; window.Scene.cam.pitch = KEYS[0].pitch;
    window.Scene.cam.dist = KEYS[0].dist; window.Scene.cam.target = KEYS[0].target.slice();
  }

  function playRecall() {
    const rc = B.recall;
    window.HUD.showCard(rc.node, true);
    window.Scene.state.packet = {
      progress: 0,
      path: [rc.node.pos, B.hub.pos, B.regionById.expression.pos],
      startedAt: performance.now(),
    };
    const t0 = performance.now();
    const tick = () => {
      const k = (performance.now() - t0) / 2600;
      if (k >= 1) { window.Scene.state.packet = null; return; }
      window.Scene.state.packet.progress = k;
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
    window.HUD.pushStream('召回', '长期记忆库 #038 → 大脑中枢 · 命中', false);
    setTimeout(() => window.HUD.hideCard(), 5200);
  }

  function allVisible() {
    setOp('#brand', 1); setOp('#legend', 1); setOp('#persona', 1); setOp('#stream', 1); setOp('#dock', 1);
    window.Scene.state.reveal = 1;
    window.HUD.S.reveal.labels = null;
    if (tagEl) tagEl.style.opacity = '0';
    const boot = document.getElementById('boot');
    if (boot) { boot.style.opacity = ''; boot.style.pointerEvents = ''; }
  }

  return { init, update, DURATION, S, toggleShowcase, startShowcase, stopShowcase, playRecall,
           allVisible, cameraAt };
})();
