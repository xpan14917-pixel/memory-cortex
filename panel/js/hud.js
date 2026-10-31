/* ============================================================
   hud.js — DOM panels, labels, stream, timeline, interaction
   ============================================================ */
window.HUD = (function () {
  'use strict';
  const B = window.BRAIN;
  const R = B.real;
  const $ = (s) => document.querySelector(s);
  const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

  const BASE_TS = Math.max(...R.messages.map(m => m.ts));
  const SPAN = 48 * 3600;
  const T0 = BASE_TS - SPAN;

  const KIND = {
    fact: { cn: '事实', en: 'FACT', c: '#74e4ff' },
    event: { cn: '经历', en: 'EVENT', c: '#ffcb6b' },
    preference: { cn: '喜好', en: 'PREF', c: '#ff9ecb' },
    promise: { cn: '约定', en: 'PROMISE', c: '#b18cff' },
    date: { cn: '日子', en: 'DATE', c: '#7fe3a0' },
    keyword: { cn: '关键词', en: 'KEYWORD', c: '#4fd8ee' },
    hub: { cn: '中枢', en: 'HUB', c: '#f4f7c9' },
  };

  const S = {
    t: 0, mode: 'live', pinned: null, hover: null,
    iso: null, reveal: {}, bootDone: false,
    streamIdx: 0, lastStream: -99, fps: 60,
    autoRotate: true, showLabels: true, bloomOn: true, quality: 1,
    query: '', kindFilter: new Set(), matchCount: 0,
    scrub: null, playing: false,
  };

  /* ---------------- init ---------------- */
  function init() {
    buildNav();
    buildLabels();
    buildRadar();
    buildTimeline();
    buildStreamSeed();
    bindControls();
    updateIdentity();
  }

  function updateIdentity() {
    const st = R.state;
    $('#p-intimacy').textContent = st.intimacy.toFixed(1);
    $('#intimacy-arc').style.strokeDashoffset = String(258 * (1 - st.intimacy / 100));
    $('#v-pleasure').textContent = st.pleasure.toFixed(2);
    $('#v-arousal').textContent = st.arousal.toFixed(2);
    $('#v-dominance').textContent = st.dominance.toFixed(2);
    setTimeout(() => {
      $('#bar-pleasure').style.width = (st.pleasure * 100).toFixed(1) + '%';
      $('#bar-arousal').style.width = (st.arousal * 100).toFixed(1) + '%';
      $('#bar-dominance').style.width = (st.dominance * 100).toFixed(1) + '%';
    }, 400);
    $('#v-energy').textContent = st.energy.toFixed(0) + '%';
    $('#bar-energy').style.width = clamp(st.energy, 3, 100) + '%';
    $('#e-note').textContent = st.energy < 25 ? '低电量 · 有点困了' : (st.energy < 55 ? '还行 · 能再聊会儿' : '精神不错');
    const stage = st.intimacy >= 90 ? '唯一' : st.intimacy >= 70 ? '依赖' : st.intimacy >= 45 ? '亲近' : st.intimacy >= 20 ? '熟悉' : '陌生';
    $('#p-stage').textContent = stage;

    $('#st-nodes').textContent = B.stats.nodes.toLocaleString();
    $('#st-edges').textContent = B.stats.edges.toLocaleString();
    $('#st-particles').textContent = B.stats.particles.toLocaleString();
    $('#st-mem').textContent = B.stats.memories;
    $('#tl-now').textContent = fmtDate(BASE_TS);
  }

  /* ---------------- cortical nav (mini-map) ---------------- */
  const NAV = { cv: null, ctx: null, w: 0, h: 0, dpr: 1, sx: 1, sy: 1, ox: 0, oy: 0, hover: null };

  function buildNav() {
    NAV.cv = document.getElementById('minimap');
    NAV.ctx = NAV.cv.getContext('2d');
    layoutNav();

    const tip = $('#nav-tip');
    NAV.cv.addEventListener('mousemove', (e) => {
      const r = NAV.cv.getBoundingClientRect();
      const mx = e.clientX - r.left, my = e.clientY - r.top;
      const reg = navPick(mx, my);
      NAV.hover = reg ? reg.id : null;
      S.hoverRegion = NAV.hover;
      if (reg) {
        tip.innerHTML = `${reg.name}<b>${reg.anchorIds ? reg.anchorIds.length : 0}</b><em>${reg.en}</em>`;
        tip.style.left = mx + 'px';
        tip.style.top = my + 'px';
        tip.style.opacity = '1';
      } else {
        tip.style.opacity = '0';
      }
      NAV.cv.style.cursor = reg ? 'pointer' : 'crosshair';
    });
    NAV.cv.addEventListener('mouseleave', () => {
      NAV.hover = null; S.hoverRegion = null;
      $('#nav-tip').style.opacity = '0';
    });
    NAV.cv.addEventListener('click', (e) => {
      const r = NAV.cv.getBoundingClientRect();
      const reg = navPick(e.clientX - r.left, e.clientY - r.top);
      if (reg) toggleIso(reg.id);
    });
    $('#nav-reset').addEventListener('click', () => { S.iso = null; window.Scene.state.iso = null; resetView(); });

    buildComp();
    window.addEventListener('resize', () => { layoutNav(); });
  }

  function layoutNav() {
    const cssW = NAV.cv.clientWidth || 282;
    const cssH = Math.round(cssW * 0.60);
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    NAV.cv.width = Math.round(cssW * dpr);
    NAV.cv.height = Math.round(cssH * dpr);
    NAV.cv.style.height = cssH + 'px';
    NAV.w = cssW; NAV.h = cssH; NAV.dpr = dpr;

    let x0 = 1e9, x1 = -1e9, z0 = 1e9, z1 = -1e9;
    B.regions.forEach(r => {
      x0 = Math.min(x0, r.pos[0] - r.radius); x1 = Math.max(x1, r.pos[0] + r.radius);
      z0 = Math.min(z0, r.pos[2] - r.radius); z1 = Math.max(z1, r.pos[2] + r.radius);
    });
    const pad = 16;
    NAV.sx = (cssW - pad * 2) / (x1 - x0);
    NAV.sy = (cssH - pad * 2) / Math.max(1e-3, z1 - z0);
    NAV.ox = pad - x0 * NAV.sx;
    NAV.oy = pad - z0 * NAV.sy;
  }

  const navX = (x) => NAV.ox + x * NAV.sx;
  const navY = (z) => NAV.oy + z * NAV.sy;

  function navPick(mx, my) {
    let best = null, bd = 15;
    B.regions.forEach(r => {
      const d = Math.hypot(navX(r.pos[0]) - mx, navY(r.pos[2]) - my);
      if (d < bd) { bd = d; best = r; }
    });
    return best;
  }

  function drawNav(t) {
    if (!NAV.ctx) return;
    const g = NAV.ctx;
    g.setTransform(NAV.dpr, 0, 0, NAV.dpr, 0, 0);
    g.clearRect(0, 0, NAV.w, NAV.h);

    // cortex envelope
    g.save();
    g.strokeStyle = 'rgba(120,190,255,.16)';
    g.lineWidth = 1;
    g.beginPath();
    g.ellipse(NAV.w / 2, NAV.h / 2, NAV.w * 0.44, NAV.h * 0.42, 0, 0, Math.PI * 2);
    g.stroke();
    g.strokeStyle = 'rgba(120,190,255,.07)';
    g.beginPath();
    g.ellipse(NAV.w / 2, NAV.h / 2, NAV.w * 0.28, NAV.h * 0.27, 0, 0, Math.PI * 2);
    g.stroke();
    // crosshair
    g.strokeStyle = 'rgba(120,190,255,.06)';
    g.beginPath();
    g.moveTo(0, NAV.h / 2); g.lineTo(NAV.w, NAV.h / 2);
    g.moveTo(NAV.w / 2, 0); g.lineTo(NAV.w / 2, NAV.h);
    g.stroke();
    g.restore();

    // radar sweep
    const sweep = (t * 0.55) % (Math.PI * 2);
    g.save();
    g.translate(NAV.w / 2, NAV.h / 2);
    g.rotate(sweep);
    const rad0 = Math.max(NAV.w, NAV.h) * 0.54;
    const grad = g.createLinearGradient(0, 0, rad0 * Math.cos(-0.5), rad0 * Math.sin(-0.5));
    grad.addColorStop(0, 'rgba(120,220,255,.15)');
    grad.addColorStop(1, 'rgba(120,220,255,0)');
    g.fillStyle = grad;
    g.beginPath();
    g.moveTo(0, 0);
    g.arc(0, 0, rad0, -0.55, 0.02);
    g.closePath();
    g.fill();
    g.restore();

    // hub spokes
    const hub = B.hub.pos;
    g.save();
    B.regions.forEach(r => {
      if (r.id === 'thalamus') return;
      g.strokeStyle = 'rgba(130,190,255,.10)';
      g.beginPath();
      g.moveTo(navX(hub[0]), navY(hub[2]));
      g.lineTo(navX(r.pos[0]), navY(r.pos[2]));
      g.stroke();
    });
    g.restore();

    // regions
    B.regions.forEach((r) => {
      const x = navX(r.pos[0]), y = navY(r.pos[2]);
      const n = r.id === 'memory' ? B.stats.memories : (r.anchorIds ? r.anchorIds.length : 0);
      const rad = 3.0 + Math.min(5.0, n * 0.18);
      const hot = NAV.hover === r.id || S.iso === r.id;
      const dimmed = (S.iso && S.iso !== r.id) ? 0.28 : 1;

      g.save();
      g.globalAlpha = dimmed;
      if (hot) {
        g.strokeStyle = r.color;
        g.globalAlpha = dimmed * 0.55;
        g.lineWidth = 1;
        g.beginPath(); g.arc(x, y, rad + 6 + Math.sin(t * 3) * 1.2, 0, Math.PI * 2); g.stroke();
      }
      g.globalAlpha = dimmed;
      g.shadowColor = r.color;
      g.shadowBlur = hot ? 18 : 11;
      g.fillStyle = r.color;
      g.beginPath(); g.arc(x, y, rad, 0, Math.PI * 2); g.fill();
      g.shadowBlur = 0;
      g.fillStyle = 'rgba(5,10,18,.9)';
      g.beginPath(); g.arc(x, y, Math.max(0.7, rad * 0.42), 0, Math.PI * 2); g.fill();
      g.restore();

      if (hot) {
        g.save();
        g.font = '9px "Microsoft YaHei UI", sans-serif';
        g.fillStyle = r.color;
        g.textAlign = 'center';
        g.fillText(r.name, Math.min(NAV.w - 40, Math.max(40, x)), y - rad - 8);
        g.restore();
      }
    });

    // camera frustum on the map
    const c = window.Scene.camSmooth;
    const cp = Math.cos(c.pitch);
    const ex = c.target[0] + c.dist * cp * Math.sin(c.yaw);
    const ez = c.target[2] + c.dist * cp * Math.cos(c.yaw);
    const cx = navX(ex), cy = navY(ez);
    const tx = navX(c.target[0]), ty = navY(c.target[2]);
    const ang = Math.atan2(ty - cy, tx - cx);

    g.save();
    g.strokeStyle = 'rgba(143,230,255,.55)';
    g.setLineDash([3, 3]);
    g.lineWidth = 1;
    g.beginPath(); g.moveTo(cx, cy); g.lineTo(tx, ty); g.stroke();
    g.setLineDash([]);

    // view cone
    g.strokeStyle = 'rgba(143,230,255,.18)';
    g.beginPath();
    g.moveTo(cx, cy);
    g.lineTo(cx + Math.cos(ang - 0.30) * 34, cy + Math.sin(ang - 0.30) * 34);
    g.moveTo(cx, cy);
    g.lineTo(cx + Math.cos(ang + 0.30) * 34, cy + Math.sin(ang + 0.30) * 34);
    g.stroke();

    // camera glyph
    g.translate(cx, cy);
    g.rotate(ang);
    g.fillStyle = '#8fe6ff';
    g.shadowColor = '#5fd0ff';
    g.shadowBlur = 10;
    g.beginPath();
    g.moveTo(5, 0); g.lineTo(-3.5, 3.2); g.lineTo(-3.5, -3.2);
    g.closePath(); g.fill();
    g.restore();

    // target ring
    g.save();
    g.strokeStyle = 'rgba(255,203,107,.65)';
    g.lineWidth = 1;
    const pr = 5 + (Math.sin(t * 2.2) * 0.5 + 0.5) * 3;
    g.beginPath(); g.arc(tx, ty, pr, 0, Math.PI * 2); g.stroke();
    g.restore();

    // compass
    g.save();
    g.font = '7px Bahnschrift, monospace';
    g.fillStyle = 'rgba(140,180,220,.45)';
    g.fillText('DORSAL VIEW', 8, NAV.h - 7);
    g.textAlign = 'right';
    g.fillText('X→ / Z↓', NAV.w - 8, NAV.h - 7);
    g.restore();
  }

  /* ---------------- memory composition ---------------- */
  const KIND_COLORS = {
    fact: '#74e4ff', event: '#ffcb6b', preference: '#ff9ecb',
    promise: '#b18cff', date: '#7fe3a0',
  };
  const KIND_CN = { fact: '事实', event: '经历', preference: '喜好', promise: '约定', date: '日子' };

  function buildComp() {
    const counts = {};
    R.memories.forEach(m => { counts[m.kind] = (counts[m.kind] || 0) + 1; });
    const total = R.memories.length;
    const order = ['fact', 'event', 'preference', 'promise', 'date'].filter(k => counts[k]);
    S.kindFilter = new Set();

    const bar = $('#comp-bar');
    const legend = $('#comp-legend');
    bar.innerHTML = ''; legend.innerHTML = '';
    order.forEach(k => {
      const seg = el('i');
      seg.style.background = KIND_COLORS[k];
      seg.style.flex = String(counts[k]);
      seg.style.boxShadow = `0 0 10px ${KIND_COLORS[k]}55`;
      seg.dataset.kind = k;
      seg.addEventListener('click', () => toggleKind(k));
      bar.appendChild(seg);

      const row = el('div');
      row.style.color = KIND_COLORS[k];
      row.dataset.kind = k;
      row.innerHTML = `<span class="d"></span><span class="k">${KIND_CN[k]}</span><span class="n">${counts[k]}</span>`;
      row.addEventListener('click', () => toggleKind(k));
      legend.appendChild(row);
    });
    const arch = R.memories.filter(m => m.archived).length;
    const avg = total
      ? R.memories.reduce((s, m) => s + (m.retention == null ? 1 : m.retention), 0) / total
      : 0;
    $('#comp-total').textContent = total + ' 条 · 归档 ' + arch + ' · R ' + avg.toFixed(2);
  }

  function toggleKind(k) {
    if (S.kindFilter.has(k)) S.kindFilter.delete(k); else S.kindFilter.add(k);
    document.querySelectorAll('.comp-bar i, .comp-legend div').forEach((e) => {
      if (!S.kindFilter.size) { e.classList.remove('off'); return; }
      e.classList.toggle('off', !S.kindFilter.has(e.dataset.kind));
    });
    applyFilter();
  }

  function applyFilter() {
    const q = (S.query || '').toLowerCase();
    const kinds = S.kindFilter || new Set();
    const on = !!q || kinds.size > 0;
    const arr = new Float32Array(B.nodes.length).fill(on ? 0.10 : 1);
    let matched = 0;
    if (on) {
      B.nodes.forEach((n, i) => {
        let ok = true;
        if (kinds.size) ok = (n.region === 'memory' && n.meta && kinds.has(n.meta.kind));
        if (ok && q) {
          const meta = n.meta || {};
          const kws = Array.isArray(meta.keywords) ? meta.keywords.join(' ') : (meta.keywords || '');
          const hay = ((n.label || '') + ' ' + (n.sub || '') + ' ' + (meta.content || '') + ' ' + kws).toLowerCase();
          ok = hay.indexOf(q) >= 0;
        }
        if (ok) { arr[i] = 1; if (n.anchor) matched++; }
      });
    }
    window.Scene.setMatches(arr);
    window.Scene.state.search = on;
    S.matchCount = matched;
    $('#q-count').textContent = on ? (matched + ' 命中') : '';
  }

  function toggleIso(id) {
    S.iso = (S.iso === id) ? null : id;
    if (S.iso) {
      const r = B.regionById[S.iso];
      window.Scene.state.iso = S.iso;
      window.Scene.cam.target = r.pos.slice();
      window.Scene.cam.dist = clamp(r.radius * 9.5, 10, 18);
    } else {
      window.Scene.state.iso = null;
      resetView();
    }
  }

  function resetView() {
    const c = window.Scene.cam;
    c.target = [0.55, 0.25, 0];
    c.dist = 17.6; c.yaw = 0.36; c.pitch = 0.085; c.fov = 40;
    S.iso = null;
    window.Scene.state.iso = null;
  }

  /* ---------------- labels + callouts ---------------- */
  let ov = null, ovx = null, ovDpr = 1;

  function buildLabels() {
    const wrap = $('#labels');
    ov = document.getElementById('overlay2d');
    ovx = ov.getContext('2d');
    B.regions.forEach((reg) => {
      const n = el('div', 'lbl');
      n.style.color = reg.color;
      const cnt = reg.id === 'memory' ? B.stats.memories : (reg.anchorIds ? reg.anchorIds.length : 0);
      n.innerHTML = `<span class="n">${reg.name}<span class="c">${cnt}</span></span><span class="e">${reg.en}</span>`;
      wrap.appendChild(n);
      reg._lblEl = n;
    });
  }

  function updateLabels() {
    const w = window.innerWidth, h = window.innerHeight;
    const legEl = document.getElementById('legend');
    const sideEl = document.getElementById('side');
    const minX = (legEl && legEl.offsetParent ? legEl.getBoundingClientRect().right : 300) + 86;
    const maxX = (sideEl && sideEl.offsetParent ? sideEl.getBoundingClientRect().left : w - 350) - 46;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    if (ov.width !== Math.round(w * dpr) || ov.height !== Math.round(h * dpr)) {
      ov.width = Math.round(w * dpr); ov.height = Math.round(h * dpr);
      ovDpr = dpr;
    }
    ovx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ovx.clearRect(0, 0, w, h);

    const items = [];
    B.regions.forEach((reg) => {
      const e = reg._lblEl;
      if (!e) return;
      const lift = reg.labelLift != null ? reg.labelLift : reg.radius * 1.05;
      const p = window.Scene.project([reg.pos[0], reg.pos[1] + lift, reg.pos[2]]);
      const c = window.Scene.project(reg.pos);
      if (p.w <= 0.2) { e.style.opacity = '0'; return; }
      let op = 1;
      if (S.iso) op = (S.iso === reg.id) ? 1 : 0.22;
      if (S.hoverRegion && S.hoverRegion !== reg.id) op *= 0.4;
      op *= (S.reveal.labels == null ? 1 : S.reveal.labels);
      if (!S.showLabels) op = 0;
      items.push({
        reg, e, c, op,
        x: clamp(p.x, minX, maxX),
        y: clamp(p.y - 16, 96, h - 152),
        wpx: reg.name.length * 12 + 26,
      });
    });

    // de-overlap: nudge labels vertically when they collide
    items.sort((a, b) => a.y - b.y);
    for (let i = 0; i < items.length; i++) {
      for (let j = 0; j < i; j++) {
        const a = items[i], b = items[j];
        const dx = Math.abs(a.x - b.x), dy = Math.abs(a.y - b.y);
        if (dx < (a.wpx + b.wpx) * 0.42 && dy < 30) a.y = b.y - 30;
      }
    }

    items.forEach(({ reg, e, c, op, x, y }) => {
      e.style.transform = `translate(-50%,-100%) translate(${x}px,${y}px)`;
      e.style.opacity = String(op);
      e.classList.toggle('hot', S.hoverRegion === reg.id || S.iso === reg.id);
      if (op < 0.12) return;
      const dist = Math.hypot(x - c.x, y - c.y);
      if (dist < 34) return;
      const col = reg.color;
      ovx.globalAlpha = 0.28 * op;
      ovx.strokeStyle = col;
      ovx.lineWidth = 1;
      ovx.beginPath();
      ovx.moveTo(c.x, c.y);
      const midY = y + (c.y - y) * 0.55;
      ovx.lineTo(x, midY);
      ovx.lineTo(x, y + 4);
      ovx.stroke();
      ovx.globalAlpha = 0.55 * op;
      ovx.fillStyle = col;
      ovx.beginPath();
      ovx.arc(c.x, c.y, 2.2, 0, Math.PI * 2);
      ovx.fill();
      ovx.globalAlpha = 0.40 * op;
      ovx.beginPath();
      ovx.moveTo(x - 7, y + 4);
      ovx.lineTo(x + 7, y + 4);
      ovx.stroke();
    });
    ovx.globalAlpha = 1;
  }

  /* ---------------- radar ---------------- */
  function buildRadar() {
    const svg = $('#radar');
    const traits = R.state.traits;
    const keys = Object.keys(traits);
    const cx = 100, cy = 70, R0 = 46;
    const N = keys.length;
    const pt = (i, r) => {
      const a = -Math.PI / 2 + (i / N) * Math.PI * 2;
      return [cx + Math.cos(a) * r, cy + Math.sin(a) * r * 0.82];
    };
    let s = '';
    for (let g = 1; g <= 3; g++) {
      const pts = keys.map((_, i) => pt(i, R0 * g / 3).join(',')).join(' ');
      s += `<polygon points="${pts}" fill="none" stroke="rgba(120,180,255,${g === 3 ? .18 : .09})" stroke-width=".7"/>`;
    }
    keys.forEach((k, i) => {
      const p = pt(i, R0);
      s += `<line x1="${cx}" y1="${cy}" x2="${p[0]}" y2="${p[1]}" stroke="rgba(120,180,255,.10)" stroke-width=".7"/>`;
      const lp = pt(i, R0 + 15);
      const anchor = Math.abs(lp[0] - cx) < 12 ? 'middle' : (lp[0] > cx ? 'start' : 'end');
      s += `<text x="${lp[0] + (anchor === 'start' ? 2 : anchor === 'end' ? -2 : 0)}" y="${lp[1] + 3}"
        text-anchor="${anchor}" font-size="8" fill="rgba(180,205,235,.72)"
        font-family="Microsoft YaHei UI" letter-spacing=".04em">${k} <tspan fill="rgba(255,220,160,.85)" font-family="Bahnschrift,monospace">${traits[k]}</tspan></text>`;
    });
    const poly = keys.map((k, i) => pt(i, R0 * clamp(traits[k] / 100, 0.06, 1)).join(',')).join(' ');
    s += `<polygon points="${poly}" fill="rgba(255,203,107,.13)" stroke="#ffcb6b" stroke-width="1.1"
      style="filter:drop-shadow(0 0 6px rgba(255,203,107,.55))"/>`;
    keys.forEach((k, i) => {
      const p = pt(i, R0 * clamp(traits[k] / 100, 0.06, 1));
      s += `<circle cx="${p[0]}" cy="${p[1]}" r="1.7" fill="#ffe6b3"/>`;
    });
    svg.innerHTML = s;
  }

  /* ---------------- timeline ---------------- */
  function buildTimeline() {
    const bars = $('#tl-bars');
    const hours = 48;
    const hist = new Array(hours).fill(0);
    R.messages.forEach(m => {
      const idx = Math.floor((m.ts - T0) / 3600);
      if (idx >= 0 && idx < hours) hist[idx] += 1;
    });
    const mx = Math.max(1, ...hist);
    for (let i = 0; i < hours; i++) {
      const b = el('i');
      b.style.height = Math.max(2, (hist[i] / mx) * 100) + '%';
      b.style.opacity = String(0.35 + (hist[i] / mx) * 0.65);
      bars.appendChild(b);
    }
    const evs = $('#tl-events');
    const winStart = T0, winEnd = BASE_TS;
    R.memories.forEach((m) => {
      const x = clamp((m.ts - winStart) / (winEnd - winStart), 0, 1) * 100;
      const b = el('b', 'mem');
      b.style.left = x + '%';
      b.title = m.content;
      evs.appendChild(b);
    });
    R.messages.slice(-60).forEach((m) => {
      const x = clamp((m.ts - winStart) / (winEnd - winStart), 0, 1) * 100;
      const b = el('b', 'msg');
      b.style.left = x + '%';
      evs.appendChild(b);
    });
    const ticks = $('#tl-ticks');
    const labels = ['D-2', 'D-1 06:00', 'D-1 18:00', '00:00', '12:00', '现在'];
    labels.forEach(t => { ticks.appendChild(el('span', null, t)); });

    const cur = el('div', 'tl-cursor');
    cur.id = 'tl-cursor';
    $('#timeline').appendChild(cur);
  }

  /* ---------------- cognitive stream ---------------- */
  const STREAM_POOL = (() => {
    const mems = R.memories;
    const bots = R.messages.filter(m => m.role === 'bot');
    const users = R.messages.filter(m => m.role === 'user');
    const t = (s, n) => (s.length > n ? s.slice(0, n) + '…' : s);
    return [
      { tag: '召回', c: '#ffcb6b', text: () => '长期记忆库 → 检索 · ' + t(mems[Math.floor(Math.random() * mems.length)].content, 16) },
      { tag: '写入', c: '#38e0c2', text: () => '海马体 写入 1 条 · ' + t(mems[Math.floor(Math.random() * mems.length)].content, 15) },
      { tag: '情绪', c: '#f07cf0', text: () => '边缘系统 · pleasure ' + (0.6 + Math.random() * 0.4).toFixed(2) + ' 上升' },
      { tag: '表达', c: '#74e4ff', text: () => '语言中枢 · 「' + t(bots[Math.floor(Math.random() * bots.length)].content, 14) + '」' },
      { tag: '推导', c: '#b18cff', text: () => '神经图谱 · 关键词「大脑」关联 3 条' },
      { tag: '感知', c: '#a78bfa', text: () => '语言输入 · 「' + t(users[Math.floor(Math.random() * users.length)].content, 12) + '」' },
      { tag: '代谢', c: '#b6a9ff', text: () => '摘要压缩 20 轮 → 1 段 · 权重衰减 0.98' },
      { tag: '回放', c: '#ff8f9e', text: () => '内省 · 今天你说过 2 次「累」' },
    ];
  })();

  function buildStreamSeed() {
    for (let i = 0; i < 6; i++) pushStream(null, null, true);
  }

  function pushStream(tag, text, seed) {
    const list = $('#st-list');
    const item = STREAM_POOL[(S.streamIdx++) % STREAM_POOL.length];
    const row = el('div', 'st-row');
    const ts = BASE_TS + S.t - (5 - (seed ? 0 : (S.streamIdx % 5))) * 1.7;
    row.innerHTML = `<span class="tm">${fmtTime(ts)}</span>
      <span class="tg" style="color:${item.c}">${tag || item.tag}</span>
      <span class="tx">${text || item.text()}</span>`;
    if (item.tag === '召回') row.classList.add('hot');
    list.appendChild(row);
    while (list.children.length > 13) list.removeChild(list.firstChild);
  }

  /* ---------------- controls ---------------- */
  function bindControls() {
    const toggle = (id, get, set) => {
      const b = document.getElementById(id);
      if (!b) return;
      b.addEventListener('click', () => {
        const on = b.dataset.on === '1';
        b.dataset.on = on ? '0' : '1';
        b.classList.toggle('on', !on);
        set(!on);
      });
    };

    $('#btn-rotate').addEventListener('click', (e) => {
      const on = e.currentTarget.dataset.on === '1';
      e.currentTarget.dataset.on = on ? '0' : '1';
      S.autoRotate = !on;
    });
    $('#btn-reset').addEventListener('click', resetView);
    $('#btn-top').addEventListener('click', () => {
      const c = window.Scene.cam;
      c.yaw = 0.0; c.pitch = 1.05; c.dist = 20.5; c.target = [0.55, 0.1, 0.2];
    });
    $('#btn-flat').addEventListener('click', () => {
      const c = window.Scene.cam;
      c.yaw = 0.02; c.pitch = 0.02; c.dist = 17.0; c.target = [0.55, 0.55, 0];
    });
    $('#btn-recall').addEventListener('click', () => window.Cine && window.Cine.playRecall());
    $('#c-close').addEventListener('click', () => { S.pinned = null; hideCard(); });

    toggle('tg-labels', null, (v) => { S.showLabels = v; });
    toggle('tg-edges', null, (v) => { window.Scene.state.showEdges = v; });
    toggle('tg-dust', null, (v) => { window.Scene.state.showParticles = v; });
    toggle('tg-glow', null, (v) => { S.bloomOn = v; });

    document.querySelectorAll('#seg-quality button').forEach((b) => {
      b.addEventListener('click', () => {
        document.querySelectorAll('#seg-quality button').forEach(x => x.classList.remove('on'));
        b.classList.add('on');
        const q = parseFloat(b.dataset.q);
        window.Scene.state.density = q;
        S.quality = q;
      });
    });

    const q = $('#q');
    q.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { S.query = q.value.trim(); applyFilter(); }
      if (e.key === 'Escape') { q.value = ''; S.query = ''; applyFilter(); q.blur(); }
    });
    q.addEventListener('input', () => {
      if (!q.value.trim() && S.query) { S.query = ''; applyFilter(); }
    });

    $('#btn-replay').addEventListener('click', startTimelinePlay);
    $('#btn-shot').addEventListener('click', exportShot);
    $('#btn-full').addEventListener('click', toggleFull);

    bindTimelineScrub();

    window.addEventListener('resize', () => { updateLabels(); layoutNav(); });
    window.addEventListener('keydown', (e) => {
      if (e.target && e.target.tagName === 'INPUT') return;
      if (e.key === ' ') { e.preventDefault(); $('#btn-rotate').click(); }
      if (e.key === 'r' || e.key === 'R') resetView();
      if (e.key === 'f' || e.key === 'F') toggleFull();
      if (e.key === '/') { e.preventDefault(); q.focus(); }
      if (e.key === 'Escape') { S.pinned = null; hideCard(); q.blur(); }
    });
  }

  function bindTimelineScrub() {
    const tl = $('#timeline');
    const cur = document.getElementById('tl-cursor');
    const getV = (e) => {
      const r = tl.getBoundingClientRect();
      return clamp((e.clientX - r.left) / r.width, 0, 1);
    };
    const setV = (v) => {
      S.scrub = v;
      window.Scene.state.cursor = v;
      cur.style.left = (v * 100) + '%';
      cur.style.opacity = '1';
      $('#tcur').textContent = fmtDate(T0 + v * SPAN).slice(5);
    };
    let dragging = false;
    tl.addEventListener('pointerdown', (e) => {
      dragging = true; tl.setPointerCapture(e.pointerId); setV(getV(e));
    });
    tl.addEventListener('pointermove', (e) => {
      if (!dragging) return;
      setV(getV(e));
    });
    tl.addEventListener('pointerup', () => { dragging = false; });
    tl.addEventListener('dblclick', () => {
      S.scrub = null; window.Scene.state.cursor = -1;
      cur.style.opacity = '0'; $('#tcur').textContent = '现在';
    });
    S._setScrub = setV;
  }

  let replayTimer = null;
  function startTimelinePlay() {
    if (replayTimer) { clearInterval(replayTimer); replayTimer = null; }
    let v = 0;
    const step = 0.012;
    S.playing = true;
    replayTimer = setInterval(() => {
      v += step;
      if (v >= 1) {
        v = 1;
        clearInterval(replayTimer); replayTimer = null;
        S.playing = false;
        setTimeout(() => {
          S.scrub = null; window.Scene.state.cursor = -1;
          const c = document.getElementById('tl-cursor');
          if (c) c.style.opacity = '0';
          $('#tcur').textContent = '现在';
        }, 1200);
      }
      S._setScrub(v);
    }, 110);
  }

  function exportShot() {
    try {
      const cv = document.getElementById('gl');
      const a = document.createElement('a');
      a.download = 'memory-cortex-' + Date.now() + '.png';
      a.href = cv.toDataURL('image/png');
      a.click();
    } catch (err) { console.warn(err); }
  }

  function toggleFull() {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {});
    } else {
      document.exitFullscreen().catch(() => {});
    }
  }

  /* ---------------- card ---------------- */
  function showCard(node, pinned) {
    if (!node) { hideCard(); return; }
    const meta = node.meta || {};
    const k = KIND[meta.kind] || KIND.event;
    $('#c-kind').textContent = k.en + ' · ' + k.cn;
    $('#c-kind').style.background = k.c;
    $('#c-id').textContent = meta.id ? ('#' + String(meta.id).padStart(3, '0')) : ('#' + String(node.id).padStart(3, '0'));
    $('#c-text').textContent = meta.content || node.label || '';
    const bits = [];
    if (meta.weight != null) bits.push(`<span>权重 <b>${meta.weight.toFixed(1)}</b></span>`);
    if (meta.hits != null) bits.push(`<span>召回 <b>${meta.hits}</b> 次</span>`);
    if (meta.n != null) bits.push(`<span>关联 <b>${meta.n}</b> 条</span>`);
    if (meta.ts) bits.push(`<span>写入 <b>${fmtDate(meta.ts).slice(5)}</b></span>`);
    $('#c-meta').innerHTML = bits.join('');
    const w = clamp((meta.weight || 1) / 1.6, 0.1, 1);
    $('#c-bar-fill').style.width = '0%';
    setTimeout(() => { $('#c-bar-fill').style.width = (w * 100).toFixed(0) + '%'; }, 30);
    $('#c-foot-l').textContent = node.region ? B.regionById[node.region].name : '环境粒子';
    $('#c-foot-r').textContent = 'WEIGHT ' + (meta.weight != null ? meta.weight.toFixed(1) : '—');
    $('#card').classList.add('show');
    if (pinned) S.pinned = node;
  }

  function hideCard() {
    $('#card').classList.remove('show');
  }

  /* ---------------- live ---------------- */
  function applyLive(s) {
    if (!s || !s.state) return;
    const st = s.state;
    ['intimacy', 'energy', 'pleasure', 'arousal', 'dominance'].forEach((k) => {
      if (st[k] != null && !isNaN(Number(st[k]))) R.state[k] = Number(st[k]);
    });
    if (st.traits && Object.keys(st.traits).length) R.state.traits = st.traits;
    updateIdentity();
    buildRadar();
  }

  /* ---------------- per-frame ---------------- */
  function update(t, dt) {
    S.t = t;
    const scrubbing = S.scrub != null;
    const now = scrubbing ? (T0 + S.scrub * SPAN) : (BASE_TS + t);
    $('#clock').textContent = new Date(now * 1000).toTimeString().slice(0, 8);

    // cortical nav mini-map
    drawNav(t);

    // timeline playhead follows the scrub cursor while scrubbing
    const ph = clamp((now - T0) / SPAN, 0, 1) * 100;
    $('#tl-playhead').style.left = ph + '%';
    if (scrubbing) $('#tl-playhead').style.opacity = '0.25';
    else $('#tl-playhead').style.opacity = '1';

    updateLabels();

    // stream append
    if (S.reveal.stream !== 0 && t - S.lastStream > 1.9) {
      S.lastStream = t;
      pushStream();
    }

    // reticle position handled in mouse handler
  }

  function setFPS(v) { const e = document.getElementById('fps'); if (e) e.textContent = v; }

  function setGPU(v) { const e = document.getElementById('gpu'); if (e) e.textContent = v; }

  function fmtTime(ts) {
    const d = new Date(ts * 1000);
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`;
  }
  function fmtDate(ts) {
    const d = new Date(ts * 1000);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${fmtTime(ts).slice(0, 5)}`;
  }

  return {
    init, update, showCard, hideCard, pushStream, setFPS, setGPU, resetView, fmtTime, applyLive,
    S, BASE_TS, nav: NAV, drawNav,
    get iso() { return S.iso; },
  };
})();
