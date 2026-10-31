/* ============================================================
   main.js — bootstrap, loop, interaction, capture API
   ============================================================ */
(function () {
  'use strict';
  const qs = new URLSearchParams(location.search);
  const CAPTURE = qs.has('capture');
  const errEl = document.getElementById('err');

  function fail(msg) {
    console.error(msg);
    if (errEl) { errEl.style.display = 'block'; errEl.textContent += msg + '\n'; }
  }
  window.addEventListener('error', (e) => fail('[error] ' + (e.message || e.error)));
  window.addEventListener('unhandledrejection', (e) => fail('[promise] ' + (e.reason && e.reason.message || e.reason)));

  let renderer = null, scene = null;
  let t = 0, last = 0, started = false;
  let autoRotate = true, userHold = 0;
  let fpsAcc = 0, fpsN = 0, fpsT = 0;

  const canvas = document.getElementById('gl');
  const reticle = document.getElementById('reticle');

  function resize() {
    if (!renderer) return;
    renderer.resize();
    scene.setSize(canvas.clientWidth, canvas.clientHeight);
  }

  function postOpts() {
    const S = window.Cine.S;
    if (S.active) {
      return { time: t, bloom: S.bloom, exposure: S.exposure, grain: 0.05, vignette: 1, ca: S.ca, fade: S.fade };
    }
    const bl = window.HUD.S.bloomOn ? 0.72 : 0.0;
    return { time: t, bloom: bl, exposure: 1.05, grain: 0.045, vignette: 1, ca: 0.34, fade: 1 };
  }

  function draw() {
    renderer.beginScene();
    scene.render(t);
    renderer.post(postOpts());
  }

  function loop(now) {
    if (!started) return;
    const dt = Math.min(0.05, Math.max(0.001, (now - last) / 1000));
    last = now;
    t += dt;

    if (window.Cine.S.active) {
      if (t > window.Cine.DURATION) {
        t = 0; window.Cine.S.t = 0;
        window.Cine.S.recallDone = false; window.Cine.S.recallDone2 = false;
        window.HUD.S.lastStream = -99;
      }
      window.Cine.update(t);
    } else {
      scene.state.reveal = Math.min(1, t / 2.2);
      if (window.HUD.S.autoRotate && performance.now() > userHold) scene.cam.yaw += dt * 0.030;
    }

    scene.update(t, dt);
    draw();
    window.HUD.update(t, dt);

    fpsAcc += dt; fpsN++;
    if (fpsAcc > 0.5) {
      window.HUD.setFPS(Math.round(fpsN / fpsAcc));
      fpsAcc = 0; fpsN = 0;
    }
    requestAnimationFrame(loop);
  }

  /* ---------------- pointer ---------------- */
  let drag = null;

  function bindPointer() {
    canvas.addEventListener('pointerdown', (e) => {
      drag = { x: e.clientX, y: e.clientY, yaw: scene.cam.yaw, pitch: scene.cam.pitch, moved: 0 };
      canvas.setPointerCapture(e.pointerId);
      if (window.Cine.S.active) { /* showcase keeps its own camera */ }
    });
    canvas.addEventListener('pointermove', (e) => {
      moveReticle(e.clientX, e.clientY);
      if (drag) {
        const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
        drag.moved += Math.abs(dx) + Math.abs(dy);
        if (!window.Cine.S.active) {
          scene.cam.yaw = drag.yaw - dx * 0.0032;
          scene.cam.pitch = Math.max(-0.75, Math.min(1.15, drag.pitch + dy * 0.0024));
          userHold = performance.now() + 2500;
        }
        return;
      }
      const n = scene.pick(e.clientX, e.clientY);
      scene.state.hover = n;
      scene.state.hoverEdge = -1;
      if (n && !window.Cine.S.active && !window.HUD.S.pinned) {
        window.HUD.showCard(n, false);
      } else if (!n && !window.HUD.S.pinned) {
        window.HUD.hideCard();
      }
      reticle.classList.toggle('on', !!n);
    });
    canvas.addEventListener('pointerup', (e) => {
      if (drag && drag.moved < 6) {
        const n = scene.pick(e.clientX, e.clientY);
        if (n && !window.Cine.S.active) {
          window.HUD.S.pinned = n;
          window.HUD.showCard(n, true);
          scene.cam.target = n.pos.slice();
          scene.cam.dist = Math.max(8.5, Math.min(scene.cam.dist, 12));
          userHold = performance.now() + 4000;
        }
      }
      drag = null;
    });
    canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      if (window.Cine.S.active) return;
      scene.cam.dist = Math.max(6.5, Math.min(36, scene.cam.dist * (1 + e.deltaY * 0.0009)));
      userHold = performance.now() + 2500;
    }, { passive: false });
    canvas.addEventListener('pointerleave', () => {
      reticle.style.opacity = '0';
      scene.state.hover = null;
    });
    canvas.addEventListener('pointerenter', () => { reticle.style.opacity = ''; });
    window.addEventListener('keydown', (e) => {
      if (e.key === 'r' || e.key === 'R') window.HUD.resetView();
      if (e.key === ' ') { e.preventDefault(); document.getElementById('btn-rotate').click(); }
    });
  }

  function moveReticle(x, y) {
    reticle.style.transform = `translate(${x}px,${y}px)`;
    reticle.style.opacity = '0.55';
  }

  /* ---------------- init ---------------- */
  function boot() {
    try {
      renderer = new window.GL.Renderer(canvas);
      scene = window.Scene;
      scene.init(renderer);
      scene.setSize(canvas.clientWidth, canvas.clientHeight);
      window.HUD.init();
      window.Cine.init();
      bindPointer();
      window.addEventListener('resize', resize);
      resize();

      const gl = renderer.gl;
      const dbg = gl.getExtension('WEBGL_debug_renderer_info');
      window.HUD.setGPU('WEBGL2');

      if (CAPTURE) {
        document.body.classList.add('capture');
        window.Cine.S.active = true;
        window.Cine.S.capture = true;
        t = 0; last = 0;
        window.Cine.update(0);
        scene.snap();
        scene.update(0, 1 / 30);
        draw();
        started = true;
        window.__ready = true;
        const tp = parseFloat(qs.get('t'));
        if (!isNaN(tp)) window.__seek(tp);
      } else {
        started = true;
        last = performance.now();
        requestAnimationFrame(loop);
        setTimeout(() => {
          const b = document.getElementById('boot');
          if (b) b.classList.add('done');
        }, 2600);
        window.__ready = true;
      }
    } catch (err) {
      fail('[boot] ' + (err && err.stack || err));
    }
  }

  /* deterministic seek for capture */
  window.__seek = function (time) {
    if (!CAPTURE) return false;
    t = time;
    window.Cine.S.t = time;
    window.Cine.update(time);
    scene.snap();
    scene.update(time, 1 / 30);
    draw();
    window.HUD.update(time, 1 / 30);
    renderer.gl.finish();
    return true;
  };
  window.__duration = () => window.Cine.DURATION;

  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    setTimeout(boot, 0);
  } else {
    document.addEventListener('DOMContentLoaded', boot);
  }
})();
