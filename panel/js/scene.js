/* ============================================================
   scene.js — geometry upload, camera, draw calls, picking
   ============================================================ */
window.Scene = (function () {
  'use strict';
  const B = window.BRAIN;
  const { mat4, Program, makeBuffer } = window.GL;
  const SIZE = 0.0122;          // data units -> world units

  /* ---------------- shaders (extra) ---------------- */
  const VS_RISE = `#version 300 es
  precision highp float;
  layout(location=0) in vec3 aBase;
  layout(location=1) in vec3 aColor;
  layout(location=2) in float aSize;
  layout(location=3) in float aSpeed;
  layout(location=4) in float aOffset;
  layout(location=5) in float aSeed;
  uniform mat4 uMVP;
  uniform float uTime, uScale, uOpacity;
  out vec3 vColor; out float vGlow; out float vFade;
  void main(){
    float life = fract(aOffset + uTime * aSpeed * 0.16);
    float y = aBase.y + life * 3.2;
    vec3 p = vec3(aBase.x + sin(uTime*0.5 + aSeed*9.0)*0.06, y, aBase.z);
    vec4 vp = uMVP * vec4(p,1.0);
    gl_Position = vp;
    gl_PointSize = max(1.0, aSize * SIZE_UNI / max(0.2, vp.w));
    vFade = sin(life*3.14159);
    vColor = aColor;
    vGlow = uOpacity * (0.35 + 0.65*vFade);
  }`.replace('SIZE_UNI', 'uScale');

  const FS_RISE = `#version 300 es
  precision highp float;
  in vec3 vColor; in float vGlow; in float vFade;
  out vec4 o;
  void main(){
    vec2 p = gl_PointCoord*2.0-1.0;
    float r = length(p);
    if (r>1.0) discard;
    float a = exp(-r*r*4.2)*0.85;
    o = vec4(vColor*a*vGlow, a*vGlow);
  }`;

  const VS_WIRE = `#version 300 es
  precision highp float;
  layout(location=0) in vec3 aPos;
  uniform mat4 uMVP;
  uniform float uOpacity;
  uniform vec3 uColor;
  out vec3 vColor;
  void main(){
    gl_Position = uMVP*vec4(aPos,1.0);
    vColor = uColor*uOpacity;
  }`;

  const FS_WIRE = `#version 300 es
  precision highp float;
  in vec3 vColor; out vec4 o;
  void main(){ o = vec4(vColor,1.0); }`;

  const VS_GLOW = `#version 300 es
  precision highp float;
  layout(location=0) in vec2 aPos;
  uniform mat4 uMVP; uniform vec3 uCenter; uniform float uRadius; uniform float uSquash;
  out vec2 vP;
  void main(){
    vec3 p = uCenter + vec3(aPos.x*uRadius, 0.0, aPos.y*uRadius*uSquash);
    gl_Position = uMVP*vec4(p,1.0);
    vP = aPos;
  }`;

  const FS_GLOW = `#version 300 es
  precision highp float;
  in vec2 vP; out vec4 o;
  uniform vec3 uColor; uniform float uIntensity;
  void main(){
    float r = length(vP);
    float a = pow(max(0.0, 1.0-r), 2.6);
    float core = pow(max(0.0, 1.0-r*1.9), 5.0);
    o = vec4(uColor*(a*0.55 + core*1.4)*uIntensity, 1.0);
  }`;

  /* ---------------- camera ---------------- */
  const cam = {
    yaw: 0.36, pitch: 0.085, dist: 17.6, fov: 40,
    target: [0.55, 0.25, 0.0], roll: 0,
  };
  const camSmooth = Object.assign({}, cam, { target: cam.target.slice() });
  const view = mat4.create(), proj = mat4.create(), vp = mat4.create();
  const tmp = mat4.create();

  function eyePos(c) {
    const cp = Math.cos(c.pitch), sp = Math.sin(c.pitch);
    return [
      c.target[0] + c.dist * cp * Math.sin(c.yaw),
      c.target[1] + c.dist * sp,
      c.target[2] + c.dist * cp * Math.cos(c.yaw),
    ];
  }

  /* ---------------- builders ---------------- */
  let gl, R, pts, rise, lines, beams, wire, dyn, glowVAO;
  let pPoint, pLine, pBeam, pRise, pWire, pGlow;
  let buffers = {};
  let cssW = 1, cssH = 1;

  function packPoints(list) {
    const n = list.length;
    const arr = new Float32Array(n * 12);
    const regionIdx = {};
    B.regions.forEach((r, i) => { regionIdx[r.id] = i; });
    for (let i = 0; i < n; i++) {
      const o = list[i], k = i * 12;
      arr[k] = o.pos[0]; arr[k + 1] = o.pos[1]; arr[k + 2] = o.pos[2];
      arr[k + 3] = o.color[0]; arr[k + 4] = o.color[1]; arr[k + 5] = o.color[2];
      arr[k + 6] = o.size * SIZE;
      arr[k + 7] = o.phase || 0;
      arr[k + 8] = o.kind != null ? o.kind : (o.anchor ? 1 : 0);
      arr[k + 9] = o.seed || (i + 1);
      arr[k + 10] = o.region != null ? regionIdx[o.region] : -1;
      arr[k + 11] = o.delay != null ? o.delay : 0.9;
    }
    return arr;
  }

  function bezierPts(a, b, curve, seg) {
    const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2, mz = (a[2] + b[2]) / 2;
    let dx = b[0] - a[0], dy = b[1] - a[1], dz = b[2] - a[2];
    const len = Math.hypot(dx, dy, dz) || 1;
    // perpendicular-ish offset for the bow
    const px = -dz / len, py = 0.35 / len, pz = dx / len;
    const cx = mx + px * curve * len, cy = my + py * curve * len * 0.6, cz = mz + pz * curve * len;
    const out = [];
    for (let i = 0; i <= seg; i++) {
      const t = i / seg, u = 1 - t;
      out.push([
        u * u * a[0] + 2 * u * t * cx + t * t * b[0],
        u * u * a[1] + 2 * u * t * cy + t * t * b[1],
        u * u * a[2] + 2 * u * t * cz + t * t * b[2],
      ]);
    }
    return out;
  }

  function buildLines() {
    const nodeById = {};
    B.nodes.forEach(n => { nodeById[n.id] = n; });
    const verts = [];
    let edgeId = 0;
    B.edges.forEach((e) => {
      const na = nodeById[e.a], nb = nodeById[e.b];
      if (!na || !nb) return;
      const seg = 20;
      const pts2 = bezierPts(na.pos, nb.pos, e.curve || 0.1, seg);
      const raw = e.col || [0.6, 0.8, 1.0];
      const col = [
        raw[0] * 0.45 + 0.55,
        raw[1] * 0.45 + 0.62,
        raw[2] * 0.45 + 0.78,
      ];
      const alpha = (e.alpha != null ? e.alpha : 0.4) * 0.5;
      for (let i = 0; i < seg; i++) {
        for (let s = 0; s < 2; s++) {
          const idx = i + s;
          const t = idx / seg;
          const env = Math.pow(Math.sin(Math.PI * t), 0.55) * 0.85 + 0.15;
          const p = pts2[idx];
          verts.push(p[0], p[1], p[2],
            col[0] * alpha * env, col[1] * alpha * env, col[2] * alpha * env,
            t, edgeId);
        }
      }
      e.edgeId = edgeId;
      edgeId++;
    });
    return { data: new Float32Array(verts), count: verts.length / 8, edges: edgeId };
  }

  function buildBeams() {
    const verts = [];
    B.beams.forEach((b) => {
      const c = b.color;
      const corners = [[0, -1], [0, 1], [1, 1], [0, -1], [1, 1], [1, -1]];
      corners.forEach(([u, s]) => {
        verts.push(b.a[0], b.a[1], b.a[2], b.b[0], b.b[1], b.b[2],
          u, s, c[0], c[1], c[2], b.width, b.seed);
      });
    });
    return new Float32Array(verts);
  }

  function buildRising() {
    const n = B.rising.length;
    const out = new Float32Array(n * 10);
    B.rising.forEach((o, i) => {
      const k = i * 10;
      out[k] = o.base[0]; out[k + 1] = o.base[1]; out[k + 2] = o.base[2];
      out[k + 3] = o.color[0]; out[k + 4] = o.color[1]; out[k + 5] = o.color[2];
      out[k + 6] = o.size * SIZE;
      out[k + 7] = o.speed;
      out[k + 8] = o.offset;
      out[k + 9] = (i % 97) / 97;
    });
    return out;
  }

  /* ---------------- geometry helpers ---------------- */
  function circlePts(n, plane) {
    const v = [];
    for (let i = 0; i <= n; i++) {
      const a = (i / n) * Math.PI * 2;
      const c = Math.cos(a), s = Math.sin(a);
      if (plane === 'xz') v.push(c, 0, s); else v.push(c, s, 0);
    }
    return new Float32Array(v);
  }

  function octaEdges(r) {
    const v = [[0, r, 0], [r, 0, 0], [0, 0, r], [-r, 0, 0], [0, 0, -r], [0, -r, 0]];
    const E = [[0, 1], [0, 2], [0, 3], [0, 4], [5, 1], [5, 2], [5, 3], [5, 4], [1, 2], [2, 3], [3, 4], [4, 1]];
    const arr = [];
    E.forEach(([a, b]) => arr.push(...v[a], ...v[b]));
    return new Float32Array(arr);
  }

  /* ---------------- init ---------------- */
  function init(renderer) {
    R = renderer; gl = renderer.gl;
    cssW = R.canvas.clientWidth; cssH = R.canvas.clientHeight;

    pPoint = new Program(gl, window.GL.VS_POINT, window.GL.FS_POINT, 'point');
    pLine = new Program(gl, window.GL.VS_LINE, window.GL.FS_LINE, 'line');
    pBeam = new Program(gl, window.GL.VS_BEAM, window.GL.FS_BEAM, 'beam');
    pRise = new Program(gl, VS_RISE, FS_RISE, 'rise');
    pWire = new Program(gl, VS_WIRE, FS_WIRE, 'wire');
    pGlow = new Program(gl, VS_GLOW, FS_GLOW, 'glow');

    /* static points */
    const arr = packPoints(B.nodes);
    pts = gl.createVertexArray();
    gl.bindVertexArray(pts);
    buffers.pt = makeBuffer(gl, arr);
    const stride = 12 * 4;
    [[0, 3, 0], [1, 3, 12], [2, 1, 24], [3, 1, 28], [4, 1, 32], [5, 1, 36], [6, 1, 40], [7, 1, 44]].forEach(([loc, size, off]) => {
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, size, gl.FLOAT, false, stride, off);
    });

    /* per-node timeline position + search match flag (own buffers) */
    const tArr = new Float32Array(B.nodes.length);
    const mArr = new Float32Array(B.nodes.length).fill(1);
    B.nodes.forEach((n, i) => { tArr[i] = n.timeNorm != null ? n.timeNorm : -1; });
    buffers.timeArr = tArr;
    buffers.matchArr = mArr;
    buffers.time = makeBuffer(gl, tArr);
    gl.enableVertexAttribArray(8);
    gl.bindBuffer(gl.ARRAY_BUFFER, buffers.time);
    gl.vertexAttribPointer(8, 1, gl.FLOAT, false, 0, 0);
    buffers.match = makeBuffer(gl, mArr);
    gl.enableVertexAttribArray(9);
    gl.bindBuffer(gl.ARRAY_BUFFER, buffers.match);
    gl.vertexAttribPointer(9, 1, gl.FLOAT, false, 0, 0);
    // constant values for VAOs that don't bind these attributes
    gl.vertexAttrib1f(8, -1.0);
    gl.vertexAttrib1f(9, 1.0);

    /* rising */
    const ra = buildRising();
    rise = gl.createVertexArray();
    gl.bindVertexArray(rise);
    buffers.rise = makeBuffer(gl, ra);
    const rstride = 10 * 4;
    [[0, 3, 0], [1, 3, 12], [2, 1, 24], [3, 1, 28], [4, 1, 32], [5, 1, 36]].forEach(([loc, size, off]) => {
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, size, gl.FLOAT, false, rstride, off);
    });

    /* lines */
    const l = buildLines();
    lines = gl.createVertexArray();
    gl.bindVertexArray(lines);
    buffers.line = makeBuffer(gl, l.data);
    const lstride = 8 * 4;
    [[0, 3, 0], [1, 3, 12], [2, 1, 24], [3, 1, 28]].forEach(([loc, size, off]) => {
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, size, gl.FLOAT, false, lstride, off);
    });
    buffers.lineCount = l.count;
    buffers.edgeCount = l.edges;

    /* beams */
    const b = buildBeams();
    beams = gl.createVertexArray();
    gl.bindVertexArray(beams);
    buffers.beam = makeBuffer(gl, b);
    const bstride = 13 * 4;
    [[0, 3, 0], [1, 3, 12], [2, 2, 24], [3, 3, 32], [4, 1, 44], [5, 1, 48]].forEach(([loc, size, off]) => {
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, size, gl.FLOAT, false, bstride, off);
    });
    buffers.beamCount = b.length / 13;

    /* wire geometry: circle + octa */
    wire = gl.createVertexArray();
    gl.bindVertexArray(wire);
    buffers.circle = makeBuffer(gl, circlePts(128, 'xy'));
    buffers.circleXZ = makeBuffer(gl, circlePts(128, 'xz'));
    buffers.octa = makeBuffer(gl, octaEdges(0.62));
    gl.bindVertexArray(null);

    /* dynamic points (hover halo, recall packet trail) */
    dyn = gl.createVertexArray();
    gl.bindVertexArray(dyn);
    buffers.dyn = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffers.dyn);
    gl.bufferData(gl.ARRAY_BUFFER, 64 * 12 * 4, gl.DYNAMIC_DRAW);
    const dstride = 12 * 4;
    [[0, 3, 0], [1, 3, 12], [2, 1, 24], [3, 1, 28], [4, 1, 32], [5, 1, 36], [6, 1, 40], [7, 1, 44]].forEach(([loc, size, off]) => {
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, size, gl.FLOAT, false, dstride, off);
    });
    gl.bindVertexArray(null);

    /* flat glow quad */
    buffers.quad = makeBuffer(gl, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]));
    glowVAO = gl.createVertexArray();
    gl.bindVertexArray(glowVAO);
    gl.bindBuffer(gl.ARRAY_BUFFER, buffers.quad);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    gl.bindVertexArray(null);
  }

  /* ---------------- projection ---------------- */
  function computeMatrices() {
    const eye = eyePos(camSmooth);
    mat4.lookAt(view, eye, camSmooth.target, [0, 1, 0]);
    const aspect = (R.w / R.h) || 1.777;
    mat4.perspective(proj, camSmooth.fov * Math.PI / 180, aspect, 0.1, 120);
    mat4.mul(vp, proj, view);
    return eye;
  }

  function project(p) {
    const m = vp;
    const x = m[0] * p[0] + m[4] * p[1] + m[8] * p[2] + m[12];
    const y = m[1] * p[0] + m[5] * p[1] + m[9] * p[2] + m[13];
    const w = m[3] * p[0] + m[7] * p[1] + m[11] * p[2] + m[15];
    return { x: (x / w * 0.5 + 0.5) * cssW, y: (0.5 - y / w * 0.5) * cssH, w, depth: w };
  }

  /* ---------------- hover / recall state ---------------- */
  const state = {
    hover: null, hoverEdge: -1, focusEdge: -1, recallT: -1, iso: null,
    recallFrom: null, recallTo: null, packet: null,
    opacity: 1, time: 0, reveal: 1, glow: null, noBeams: false,
    showEdges: true, showParticles: true, showBeams: true, showWire: true,
    cursor: -1, search: false, density: 1,
  };

  function isoIdx() {
    if (!state.iso) return -1;
    return B.regions.findIndex(r => r.id === state.iso);
  }

  function setMatches(arr) {
    if (!buffers.match || !arr) return;
    buffers.matchArr = arr;
    gl.bindBuffer(gl.ARRAY_BUFFER, buffers.match);
    gl.bufferSubData(gl.ARRAY_BUFFER, 0, arr);
  }

  function updateDynamic() {
    const verts = [];
    const push = (pos, color, size, kind, phase, seed) => {
      verts.push(pos[0], pos[1], pos[2], color[0], color[1], color[2], size * SIZE, phase, kind, seed, -1, 0);
    };
    if (state.hover) {
      push(state.hover.pos, [1, 1, 1], 26, 4, 0, 999);
    }
    if (state.packet) {
      const P = state.packet;
      for (let i = 0; i < 14; i++) {
        const tt = P.progress - i * 0.035;
        if (tt < 0) continue;
        const p = samplePath(P.path, tt);
        const f = 1 - i / 14;
        push(p, [1, 0.92, 0.7], (10 * f + 3) * (1 - i * 0.04), 4, 0, 100 + i);
      }
    }
    if (!verts.length) { state.dynCount = 0; return; }
    state.dynCount = verts.length / 12;
    gl.bindBuffer(gl.ARRAY_BUFFER, buffers.dyn);
    gl.bufferSubData(gl.ARRAY_BUFFER, 0, new Float32Array(verts));
  }

  function samplePath(path, t) {    // path: array of points -> catmull-like linear with easing
    const n = path.length - 1;
    const f = Math.min(0.9999, Math.max(0, t)) * n;
    const i = Math.floor(f), u = f - i;
    const a = path[i], b = path[Math.min(n, i + 1)];
    return [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u];
  }

  /* ---------------- frame ---------------- */
  function update(t, dt) {
    state.time = t;
    // smooth camera toward target values
    const k = 1 - Math.pow(0.001, dt * 0.9);
    camSmooth.yaw += (cam.yaw - camSmooth.yaw) * k;
    camSmooth.pitch += (cam.pitch - camSmooth.pitch) * k;
    camSmooth.dist += (cam.dist - camSmooth.dist) * k;
    camSmooth.fov += (cam.fov - camSmooth.fov) * k;
    for (let i = 0; i < 3; i++) camSmooth.target[i] += (cam.target[i] - camSmooth.target[i]) * k;
    computeMatrices();
  }

  function drawWire(prog, mvp, color, opacity, geoBuf, mode) {
    gl.uniformMatrix4fv(prog.u.uMVP, false, mvp);
    gl.uniform3f(prog.u.uColor, color[0], color[1], color[2]);
    gl.uniform1f(prog.u.uOpacity, opacity);
    gl.bindBuffer(gl.ARRAY_BUFFER, geoBuf);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);
    gl.drawArrays(mode || gl.LINE_STRIP, 0, geoBuf.__n || 129);
  }

  function render(t) {
    const gl2 = gl;
    computeMatrices();
    const scale = (R.h * 0.5) / Math.tan(camSmooth.fov * Math.PI / 360);
    updateDynamic();

    /* points */
    pPoint.use();
    gl2.uniformMatrix4fv(pPoint.u.uMVP, false, vp);
    gl2.uniform1f(pPoint.u.uTime, t);
    gl2.uniform1f(pPoint.u.uScale, scale);
    gl2.uniform1f(pPoint.u.uDpr, 1);
    gl2.uniform1f(pPoint.u.uOpacity, state.opacity);
    gl2.uniform1f(pPoint.u.uFocus, 0);
    gl2.uniform1f(pPoint.u.uFocusId, -1);
    gl2.uniform1f(pPoint.u.uIso, isoIdx());
    gl2.uniform1f(pPoint.u.uReveal, state.reveal);
    gl2.uniform1f(pPoint.u.uCursor, state.cursor);
    gl2.uniform1f(pPoint.u.uSearch, state.search ? 1 : 0);
    gl2.bindVertexArray(pts);
    gl2.drawArrays(gl2.POINTS, 0, Math.max(1, Math.floor(B.nodes.length * state.density)));

    /* rising */
    if (state.showParticles) {
      pRise.use();
      gl2.uniformMatrix4fv(pRise.u.uMVP, false, vp);
      gl2.uniform1f(pRise.u.uTime, t);
      gl2.uniform1f(pRise.u.uScale, scale);
      gl2.uniform1f(pRise.u.uOpacity, state.opacity * 0.9);
      gl2.bindVertexArray(rise);
      gl2.drawArrays(gl2.POINTS, 0, Math.floor(B.rising.length * state.density));
    }

    /* beams */
    if (state.showBeams) {
      pBeam.use();
      gl2.uniformMatrix4fv(pBeam.u.uMVP, false, vp);
      gl2.uniform1f(pBeam.u.uTime, t);
      gl2.uniform1f(pBeam.u.uReveal, state.reveal * (state.iso ? 0.18 : 1));
      gl2.bindVertexArray(beams);
      gl2.drawArrays(gl2.TRIANGLES, 0, state.noBeams ? 0 : buffers.beamCount);
    }

    /* warm pool of light under the memory lake */
    pGlow.use();
    gl2.uniformMatrix4fv(pGlow.u.uMVP, false, vp);
    gl2.uniform3f(pGlow.u.uCenter, B.lake.pos[0], B.lake.pos[1] + 0.02, B.lake.pos[2]);
    gl2.uniform1f(pGlow.u.uRadius, 6.4);
    gl2.uniform1f(pGlow.u.uSquash, 0.62);
    gl2.uniform3f(pGlow.u.uColor, 1.0, 0.70, 0.36);
    gl2.uniform1f(pGlow.u.uIntensity, (state.glow != null ? state.glow : 0.30) * state.opacity * (state.iso ? 0.2 : 1));
    gl2.bindVertexArray(glowVAO);
    gl2.drawArrays(gl2.TRIANGLE_STRIP, 0, 4);

    /* edges */
    pLine.use();
    gl2.uniformMatrix4fv(pLine.u.uMVP, false, vp);
    gl2.uniform1f(pLine.u.uTime, t);
    gl2.uniform1f(pLine.u.uOpacity, state.opacity * Math.min(1, 0.22 + state.reveal * 0.92) * (state.search ? 0.22 : 1) * (state.iso ? 0.3 : 1));
    gl2.uniform1f(pLine.u.uPulseEdge, state.focusEdge);
    gl2.uniform1f(pLine.u.uPulseT, (t * 0.35) % 1);
    gl2.uniform1f(pLine.u.uFocusEdge, state.hoverEdge);
    gl2.bindVertexArray(lines);
    gl2.drawArrays(gl2.LINES, 0, buffers.lineCount);

    /* dynamic points */
    if (state.dynCount) {
      pPoint.use();
      gl2.uniformMatrix4fv(pPoint.u.uMVP, false, vp);
      gl2.uniform1f(pPoint.u.uTime, t);
      gl2.uniform1f(pPoint.u.uScale, scale);
      gl2.uniform1f(pPoint.u.uDpr, 1);
      gl2.uniform1f(pPoint.u.uOpacity, 1.0);
      gl2.uniform1f(pPoint.u.uFocusId, -1);
      gl2.uniform1f(pPoint.u.uIso, -1);
      gl2.uniform1f(pPoint.u.uReveal, state.reveal);
      gl2.bindVertexArray(dyn);
      gl2.drawArrays(gl2.POINTS, 0, state.dynCount);
    }

    /* hub rings + persona cage + lake scan ring */
    pWire.use();
    gl2.bindVertexArray(wire);
    const hub = B.hub.pos;
    const ringDefs = [
      { r: 0.62, ax: 1.35, ay: 0.0, sp: 0.55, c: [1.0, 0.97, 0.86], a: 0.95 },
      { r: 0.88, ax: 0.2, ay: 1.1, sp: -0.35, c: [1.0, 0.93, 0.72], a: 0.62 },
      { r: 1.18, ax: 1.57, ay: -0.4, sp: 0.22, c: [0.85, 0.9, 1.0], a: 0.40 },
    ];
    ringDefs.forEach((rd) => {
      const m = mat4.create();
      mat4.translate(m, hub[0], hub[1], hub[2]);
      const ry = mat4.create(), rx = mat4.create(), rz = mat4.create();
      mat4.rotateY(ry, rd.ay + t * rd.sp * 0.4);
      mat4.rotateX(rx, rd.ax + Math.sin(t * 0.2) * 0.1);
      mat4.rotateZ(rz, t * rd.sp * 0.2);
      const m2 = mat4.create();
      mat4.mul(m2, m, ry); mat4.mul(m, m2, rx); mat4.mul(m2, m, rz);
      const s = mat4.create();
      mat4.translate(s, 0, 0, 0);
      s[0] = rd.r; s[5] = rd.r; s[10] = rd.r;
      const mm = mat4.create();
      mat4.mul(mm, m2, s);
      const mvp = mat4.create();
      mat4.mul(mvp, vp, mm);
      gl2.uniformMatrix4fv(pWire.u.uMVP, false, mvp);
      gl2.uniform3f(pWire.u.uColor, rd.c[0], rd.c[1], rd.c[2]);
      gl2.uniform1f(pWire.u.uOpacity, rd.a * state.opacity * (state.iso ? 0.18 : 1) * (0.7 + 0.3 * Math.sin(t * 1.3 + rd.r * 4)));
      gl2.bindBuffer(gl2.ARRAY_BUFFER, buffers.circle);
      gl2.enableVertexAttribArray(0);
      gl2.vertexAttribPointer(0, 3, gl2.FLOAT, false, 0, 0);
      gl2.drawArrays(gl2.LINE_STRIP, 0, 129);
    });

    // persona cage
    const cage = window.BRAIN.regionById.persona.pos;
    const cm = mat4.create();
    mat4.translate(cm, cage[0], cage[1] - 0.15, cage[2]);
    const cy = mat4.create(), cx = mat4.create();
    mat4.rotateY(cy, t * 0.25);
    mat4.rotateX(cx, 0.35 + Math.sin(t * 0.3) * 0.1);
    const cm2 = mat4.create();
    mat4.mul(cm2, cm, cy); mat4.mul(cm, cm2, cx);
    const cmvp = mat4.create();
    mat4.mul(cmvp, vp, cm);
    gl2.uniformMatrix4fv(pWire.u.uMVP, false, cmvp);
    gl2.uniform3f(pWire.u.uColor, 0.82, 0.92, 1.0);
    gl2.uniform1f(pWire.u.uOpacity, 0.34 * state.opacity * (state.iso ? 0.25 : 1));
    gl2.bindBuffer(gl2.ARRAY_BUFFER, buffers.octa);
    gl2.vertexAttribPointer(0, 3, gl2.FLOAT, false, 0, 0);
    gl2.drawArrays(gl2.LINES, 0, 24);

    // lake scan ring
    const lake = B.lake.pos;
    const period = 7.0;
    const prog = (t % period) / period;
    const sm = mat4.create();
    mat4.translate(sm, lake[0], lake[1] + 0.05, lake[2]);
    const sc = 0.6 + prog * 6.2;
    sm[0] = sc; sm[5] = 1; sm[10] = sc;
    const smvp = mat4.create();
    mat4.mul(smvp, vp, sm);
    gl2.uniformMatrix4fv(pWire.u.uMVP, false, smvp);
    gl2.uniform3f(pWire.u.uColor, 1.0, 0.85, 0.55);
    gl2.uniform1f(pWire.u.uOpacity, (1 - prog) * 0.22 * state.opacity * (state.iso ? 0.2 : 1));
    gl2.bindBuffer(gl2.ARRAY_BUFFER, buffers.circleXZ);
    gl2.vertexAttribPointer(0, 3, gl2.FLOAT, false, 0, 0);
    gl2.drawArrays(gl2.LINE_STRIP, 0, 129);
  }

  /* ---------------- picking ---------------- */
  function pick(mx, my) {
    let best = null, bestD = 18;
    const anchors = B.nodes.filter(n => n.anchor);
    for (const n of anchors) {
      const p = project(n.pos);
      if (p.w <= 0) continue;
      const d = Math.hypot(p.x - mx, p.y - my);
      const rad = 10 + n.size * 0.9;
      if (d < rad && d < bestD + rad * 0.4) {
        if (!best || d < bestD) { best = n; bestD = d; }
      }
    }
    return best;
  }

  return {
    init, update, render, pick, project, cam, camSmooth, state, setMatches, get vp() { return vp; },
    setSize(w, h) { cssW = w; cssH = h; },
    snap() {
      camSmooth.yaw = cam.yaw; camSmooth.pitch = cam.pitch;
      camSmooth.dist = cam.dist; camSmooth.fov = cam.fov;
      camSmooth.target = cam.target.slice();
    },
  };
})();
