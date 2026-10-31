/* ============================================================
   gl.js — tiny WebGL2 engine: math, buffers, FBOs, bloom pipeline
   ============================================================ */
window.GL = (function () {
  'use strict';

  /* ---------------- mat4 (column major) ---------------- */
  const mat4 = {
    create() { return new Float32Array([1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]); },
    perspective(out, fovy, aspect, near, far) {
      const f = 1 / Math.tan(fovy / 2), nf = 1 / (near - far);
      out[0] = f / aspect; out[1] = 0; out[2] = 0; out[3] = 0;
      out[4] = 0; out[5] = f; out[6] = 0; out[7] = 0;
      out[8] = 0; out[9] = 0; out[10] = (far + near) * nf; out[11] = -1;
      out[12] = 0; out[13] = 0; out[14] = 2 * far * near * nf; out[15] = 0;
      return out;
    },
    lookAt(out, eye, center, up) {
      let z0 = eye[0] - center[0], z1 = eye[1] - center[1], z2 = eye[2] - center[2];
      let len = Math.hypot(z0, z1, z2) || 1; z0 /= len; z1 /= len; z2 /= len;
      let x0 = up[1] * z2 - up[2] * z1, x1 = up[2] * z0 - up[0] * z2, x2 = up[0] * z1 - up[1] * z0;
      len = Math.hypot(x0, x1, x2);
      if (!len) { x0 = 1; x1 = 0; x2 = 0; } else { x0 /= len; x1 /= len; x2 /= len; }
      const y0 = z1 * x2 - z2 * x1, y1 = z2 * x0 - z0 * x2, y2 = z0 * x1 - z1 * x0;
      out[0] = x0; out[1] = y0; out[2] = z0; out[3] = 0;
      out[4] = x1; out[5] = y1; out[6] = z1; out[7] = 0;
      out[8] = x2; out[9] = y2; out[10] = z2; out[11] = 0;
      out[12] = -(x0 * eye[0] + x1 * eye[1] + x2 * eye[2]);
      out[13] = -(y0 * eye[0] + y1 * eye[1] + y2 * eye[2]);
      out[14] = -(z0 * eye[0] + z1 * eye[1] + z2 * eye[2]);
      out[15] = 1;
      return out;
    },
    mul(out, a, b) {
      for (let c = 0; c < 4; c++) {
        const b0 = b[c * 4], b1 = b[c * 4 + 1], b2 = b[c * 4 + 2], b3 = b[c * 4 + 3];
        out[c * 4 + 0] = a[0] * b0 + a[4] * b1 + a[8] * b2 + a[12] * b3;
        out[c * 4 + 1] = a[1] * b0 + a[5] * b1 + a[9] * b2 + a[13] * b3;
        out[c * 4 + 2] = a[2] * b0 + a[6] * b1 + a[10] * b2 + a[14] * b3;
        out[c * 4 + 3] = a[3] * b0 + a[7] * b1 + a[11] * b2 + a[15] * b3;
      }
      return out;
    },
    translate(out, x, y, z) {
      out.set([1,0,0,0, 0,1,0,0, 0,0,1,0, x,y,z,1]); return out;
    },
    rotateY(out, a) {
      const c = Math.cos(a), s = Math.sin(a);
      out.set([c,0,-s,0, 0,1,0,0, s,0,c,0, 0,0,0,1]); return out;
    },
    rotateX(out, a) {
      const c = Math.cos(a), s = Math.sin(a);
      out.set([1,0,0,0, 0,c,s,0, 0,-s,c,0, 0,0,0,1]); return out;
    },
    rotateZ(out, a) {
      const c = Math.cos(a), s = Math.sin(a);
      out.set([c,s,0,0, -s,c,0,0, 0,0,1,0, 0,0,0,1]); return out;
    },
    transformPoint(m, p) {
      const [x, y, z] = p;
      return [
        m[0]*x + m[4]*y + m[8]*z + m[12],
        m[1]*x + m[5]*y + m[9]*z + m[13],
        m[2]*x + m[6]*y + m[10]*z + m[14],
      ];
    }
  };

  /* ---------------- shader/bootstrap helpers ---------------- */
  function compile(gl, type, src) {
    const sh = gl.createShader(type);
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
      const log = gl.getShaderInfoLog(sh);
      console.error('[GL] shader error:', log, '\n', src);
      throw new Error('shader compile: ' + log);
    }
    return sh;
  }

  class Program {
    constructor(gl, vs, fs, name) {
      this.gl = gl; this.name = name || 'prog';
      const p = gl.createProgram();
      gl.attachShader(p, compile(gl, gl.VERTEX_SHADER, vs));
      gl.attachShader(p, compile(gl, gl.FRAGMENT_SHADER, fs));
      gl.linkProgram(p);
      if (!gl.getProgramParameter(p, gl.LINK_STATUS)) {
        throw new Error('link ' + this.name + ': ' + gl.getProgramInfoLog(p));
      }
      this.program = p;
      this.u = {};
      const n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
      for (let i = 0; i < n; i++) {
        const info = gl.getActiveUniform(p, i);
        this.u[info.name] = gl.getUniformLocation(p, info.name);
      }
    }
    use() { this.gl.useProgram(this.program); return this; }
    f(k, v) { const l = this.u[k]; if (l) this.gl.uniform1f(l, v); return this; }
    i(k, v) { const l = this.u[k]; if (l) this.gl.uniform1i(l, v); return this; }
    v2(k, x, y) { const l = this.u[k]; if (l) this.gl.uniform2f(l, x, y); return this; }
    v3(k, x, y, z) { const l = this.u[k]; if (l) this.gl.uniform3f(l, x, y, z); return this; }
    v4(k, x, y, z, w) { const l = this.u[k]; if (l) this.gl.uniform4f(l, x, y, z, w); return this; }
    m4(k, m) { const l = this.u[k]; if (l) this.gl.uniformMatrix4fv(l, false, m); return this; }
  }

  function makeBuffer(gl, data, target) {
    const b = gl.createBuffer();
    gl.bindBuffer(target || gl.ARRAY_BUFFER, b);
    gl.bufferData(target || gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
    return b;
  }

  function makeRT(gl, w, h) {
    const tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    const fbo = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
    const ok = gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE;
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    if (!ok) console.error('[GL] incomplete FBO', w, h);
    return { tex, fbo, w, h };
  }

  /* ---------------- shaders ---------------- */
  const VS_QUAD = `#version 300 es
  in vec2 aPos;
  out vec2 vUv;
  void main(){ vUv = aPos*0.5+0.5; gl_Position = vec4(aPos,0.0,1.0); }`;

  const FS_BG = `#version 300 es
  precision highp float;
  in vec2 vUv; out vec4 o;
  void main(){
    vec2 uv = vUv;
    vec3 c = mix(vec3(0.020,0.030,0.062), vec3(0.048,0.080,0.140), pow(1.0-uv.y,1.5));
    float d = length((uv-vec2(0.60,0.42))*vec2(1.5,1.0));
    c += vec3(0.075,0.130,0.225)*exp(-d*d*2.2);
    float d2 = length((uv-vec2(0.50,0.74))*vec2(1.7,1.1));
    c += vec3(0.105,0.065,0.045)*exp(-d2*d2*2.6);
    float d3 = length((uv-vec2(0.88,0.30))*vec2(2.4,1.4));
    c += vec3(0.030,0.028,0.070)*exp(-d3*d3*2.2);
    c += vec3(0.020,0.038,0.070)*smoothstep(0.55,0.0,uv.y);
    float n = sin(uv.x*3.1+sin(uv.y*4.7)*1.2)*sin(uv.y*2.3+uv.x*1.7);
    c += n*0.004;
    float v = smoothstep(1.30,0.22,length((uv-vec2(0.5,0.48))*vec2(1.20,1.0)));
    c *= mix(0.46,1.0,v);
    o = vec4(c,1.0);
  }`;

  /* point sprite: glyph drawn procedurally in the fragment */
  const VS_POINT = `#version 300 es
  precision highp float;
  layout(location=0) in vec3 aPos;
  layout(location=1) in vec3 aColor;
  layout(location=2) in float aSize;
  layout(location=3) in float aPhase;
  layout(location=4) in float aKind;
  layout(location=5) in float aSeed;
  layout(location=6) in float aRegion;
  layout(location=7) in float aDelay;
  layout(location=8) in float aTime;
  layout(location=9) in float aMatch;
  uniform mat4 uMVP;
  uniform float uTime;
  uniform float uScale;
  uniform float uDpr;
  uniform float uFocus;      // 0..1 focus dim of others
  uniform float uFocusId;
  uniform float uOpacity;
  uniform float uIso;
  uniform float uReveal;
  uniform float uCursor;     // <0 = off, else 0..1 timeline position
  uniform float uSearch;     // 1 = search filter active
  out vec3 vColor; out float vKind; out float vSeed; out float vGlow;
  void main(){
    vec4 vp = uMVP * vec4(aPos,1.0);
    gl_Position = vp;
    float breathe = 0.86 + 0.14*sin(uTime*1.35 + aPhase*6.2831);
    float hl = (aSeed == uFocusId) ? 1.0 : 0.0;
    float dim = (uIso < -0.5 || abs(aRegion - uIso) < 0.5) ? 1.0 : 0.06;
    float dimT = (uCursor < 0.0 || aTime < 0.0 || aTime <= uCursor + 0.002) ? 1.0 : 0.07;
    float dimS = (uSearch < 0.5 || aMatch > 0.5) ? 1.0 : 0.06;
    dim *= dimT * dimS;
    float fog = clamp(1.0 - (vp.w - 9.0) / 30.0, 0.0, 1.0);
    fog = 0.42 + 0.58*fog;
    float ign = clamp((uReveal - aDelay * 0.80) / 0.22, 0.0, 1.0);
    float size = aSize * breathe * (1.0 + hl*0.35) * (0.72 + 0.28*min(1.0, dim*3.0)) * (0.55 + 0.45*ign);
    gl_PointSize = clamp(size * uScale / max(0.20, vp.w) * uDpr, 2.0, 22.0);
    vColor = aColor;
    vKind = aKind;
    vSeed = aSeed;
    vGlow = uOpacity * (0.92 + 0.08*sin(uTime*0.7 + aSeed*17.0)) * dim * fog * ign;
  }`;

  const FS_POINT = `#version 300 es
  precision highp float;
  in vec3 vColor; in float vKind; in float vSeed; in float vGlow;
  out vec4 o;
  void main(){
    vec2 p = gl_PointCoord*2.0-1.0; p.y = -p.y;
    float r = length(p);
    if (r > 1.0) discard;
    int k = int(vKind + 0.5);
    float a;
    if (k == 0) {                       // dust
      a = exp(-r*r*3.4) * 0.72;
    } else if (k == 1) {                // memory node: core + ring
      float core = exp(-r*r*26.0) * 0.62;
      float fill = exp(-r*r*7.0) * 0.09;
      float ring = smoothstep(0.105,0.0,abs(r-0.62)) * 0.95;
      float ring2 = smoothstep(0.030,0.0,abs(r-0.95)) * 0.22;
      float halo = exp(-r*r*3.0) * 0.11;
      a = core + fill + ring + ring2 + halo;
    } else if (k == 2) {                // diamond
      float d = abs(p.x)+abs(p.y);
      float edge = smoothstep(0.055,0.0,abs(d-0.55));
      float core = exp(-d*d*26.0);
      a = edge*1.1 + core*0.85 + exp(-r*r*2.0)*0.24;
    } else if (k == 3) {                // sensor tick ring
      float ring = smoothstep(0.05,0.0,abs(r-0.68));
      float core = exp(-r*r*7.0)*0.55;
      float tick = step(0.82, max(abs(p.x),abs(p.y))) * smoothstep(1.0,0.9,r) * 0.6;
      a = ring + core + tick*0.5;
    } else if (k == 4) {                // spark
      float core = exp(-r*r*16.0)*1.5;
      float cross = smoothstep(0.03,0.0,abs(p.x)) * exp(-abs(p.y)*3.4) * 0.5
                  + smoothstep(0.03,0.0,abs(p.y)) * exp(-abs(p.x)*3.4) * 0.5;
      a = core + cross + exp(-r*r*2.6)*0.35;
    } else if (k == 5) {                // soft volumetric bloom sprite
      float a0 = exp(-r*r*2.4)*0.55 + exp(-r*r*9.0)*0.45;
      a = a0;
    } else {                            // hex node
      vec2 q = abs(p);
      float h = max(q.x*0.866 + q.y*0.5, q.y);
      float edge = smoothstep(0.06,0.0,abs(h-0.52));
      a = edge*0.95 + exp(-r*r*6.0)*0.45;
    }
    o = vec4(vColor * a * vGlow, a * vGlow);
  }`;

  const VS_LINE = `#version 300 es
  precision highp float;
  layout(location=0) in vec3 aPos;
  layout(location=1) in vec3 aColor;
  layout(location=2) in float aT;
  layout(location=3) in float aEdge;
  uniform mat4 uMVP;
  uniform float uTime;
  uniform float uPulseEdge;
  uniform float uPulseT;
  uniform float uOpacity;
  uniform float uFocusEdge;
  out vec3 vColor;
  void main(){
    gl_Position = uMVP * vec4(aPos,1.0);
    float pulse = 0.0;
    if (abs(aEdge - uPulseEdge) < 0.01) {
      float d = abs(aT - uPulseT);
      pulse = exp(-d*d*260.0) * 3.2;
    }
    float flow = 0.55 + 0.45*sin(aT*18.0 - uTime*2.4 + aEdge);
    vec3 c = aColor * (0.55 + 0.65*flow + pulse);
    if (uFocusEdge > 0.5 && abs(aEdge-uFocusEdge) < 0.01) c *= 2.6;
    vColor = c * uOpacity;
  }`;

  const FS_LINE = `#version 300 es
  precision highp float;
  in vec3 vColor; out vec4 o;
  void main(){ o = vec4(vColor, 1.0); }`;

  const VS_BEAM = `#version 300 es
  precision highp float;
  layout(location=0) in vec3 aA;
  layout(location=1) in vec3 aB;
  layout(location=2) in vec2 aCorner;   // x: 0 bottom 1 top ; y: -1..1 side
  layout(location=3) in vec3 aColor;
  layout(location=4) in float aWidth;
  layout(location=5) in float aSeed;
  uniform mat4 uMVP;
  uniform float uTime;
  out vec2 vUv; out vec3 vColor; out float vSeed;
  void main(){
    vec4 ca = uMVP*vec4(aA,1.0);
    vec4 cb = uMVP*vec4(aB,1.0);
    vec3 dir = normalize(cb.xyz/cb.w - ca.xyz/ca.w + vec3(0.0,0.0001,0.0));
    vec3 side = normalize(vec3(-dir.y, dir.x, 0.0));
    vec4 c = mix(ca, cb, aCorner.x);
    // world-space thickness: shrink with distance instead of screen-space NDC
    float persp = mix(ca.w, cb.w, aCorner.x);
    float w = aWidth * (1.0 - 0.55*abs(aCorner.y)) * (17.0 / max(1.0, persp));
    c.xy += side.xy * aCorner.y * w;
    gl_Position = c;
    vUv = aCorner; vColor = aColor; vSeed = aSeed;
  }`;

  const FS_BEAM = `#version 300 es
  precision highp float;
  in vec2 vUv; in vec3 vColor; in float vSeed;
  uniform float uTime;
  uniform float uReveal;
  out vec4 o;
  void main(){
    float s = vUv.x, t = vUv.y;
    float across = exp(-t*t*3.2);
    float along = smoothstep(0.0,0.18,s) * smoothstep(1.0,0.55,s);
    float flick = 0.72 + 0.28*sin(s*22.0 - uTime*3.0 + vSeed*9.0);
    float a = across*along*0.42*flick*uReveal;
    o = vec4(vColor*a, a);
  }`;

  const FS_BRIGHT = `#version 300 es
  precision highp float;
  in vec2 vUv; out vec4 o;
  uniform sampler2D uTex; uniform float uThreshold; uniform float uKnee;
  void main(){
    vec3 c = texture(uTex, vUv).rgb;
    float l = max(c.r,max(c.g,c.b));
    float soft = clamp(l - uThreshold + uKnee, 0.0, 2.0*uKnee);
    soft = soft*soft/(4.0*uKnee + 1e-4);
    float w = max(soft, l - uThreshold) / max(l, 1e-4);
    o = vec4(c*w, 1.0);
  }`;

  const FS_BLUR = `#version 300 es
  precision highp float;
  in vec2 vUv; out vec4 o;
  uniform sampler2D uTex; uniform vec2 uDir; uniform vec2 uTexel;
  void main(){
    vec3 s = texture(uTex,vUv).rgb * 0.2270270270;
    s += (texture(uTex, vUv + uDir*uTexel*1.3846153846).rgb + texture(uTex, vUv - uDir*uTexel*1.3846153846).rgb) * 0.3162162162;
    s += (texture(uTex, vUv + uDir*uTexel*3.2307692308).rgb + texture(uTex, vUv - uDir*uTexel*3.2307692308).rgb) * 0.0702702703;
    o = vec4(s,1.0);
  }`;

  const FS_COMPOSITE = `#version 300 es
  precision highp float;
  in vec2 vUv; out vec4 o;
  uniform sampler2D uScene, uBloomA, uBloomB;
  uniform float uTime, uBloom, uExposure, uGrain, uVignette, uCA, uFade;
  uniform vec2 uRes;
  vec3 aces(vec3 x){
    float a=2.51,b=0.03,c=2.43,d=0.59,e=0.14;
    return clamp((x*(a*x+b))/(x*(c*x+d)+e),0.0,1.0);
  }
  float hash(vec2 p){ p = fract(p*vec2(123.34,456.21)); p += dot(p,p+45.32); return fract(p.x*p.y); }
  void main(){
    vec2 uv = vUv;
    vec2 d = uv - 0.5;
    float rr = dot(d,d);
    float ca = uCA * rr * 0.0045;
    vec3 col;
    col.r = texture(uScene, uv + d*ca).r;
    col.g = texture(uScene, uv).g;
    col.b = texture(uScene, uv - d*ca).b;

    vec3 bA = texture(uBloomA, uv).rgb;
    vec3 bB = texture(uBloomB, uv).rgb;
    col += (bA * 0.42 + bB * 0.66) * uBloom;

    col *= uExposure;
    col = aces(col);
    col = pow(col, vec3(0.92));
    col *= vec3(0.97, 1.0, 1.06);
    col += vec3(0.003, 0.006, 0.013) * (1.0 - col);

    float vig = smoothstep(1.22, 0.28, length(d*vec2(1.18,1.0)));
    col *= mix(1.0, 0.42 + 0.58*vig, uVignette);

    float g = hash(uv*uRes + fract(uTime)*137.0) - 0.5;
    col += g * uGrain;

    col *= uFade;
    o = vec4(col, 1.0);
  }`;

  /* ---------------- renderer ---------------- */
  class Renderer {
    constructor(canvas) {
      this.canvas = canvas;
      const gl = canvas.getContext('webgl2', {
        alpha: false, antialias: false, depth: true, stencil: false,
        premultipliedAlpha: false, preserveDrawingBuffer: true,
        powerPreference: 'high-performance'
      });
      if (!gl) throw new Error('WebGL2 not supported');
      this.gl = gl;
      gl.getExtension('EXT_color_buffer_float');
      gl.getExtension('OES_texture_float_linear');
      gl.disable(gl.DEPTH_TEST);
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.ONE, gl.ONE);

      this.quad = makeBuffer(gl, new Float32Array([-1,-1, 3,-1, -1,3]));
      this.qa = gl.createVertexArray();
      gl.bindVertexArray(this.qa);
      gl.bindBuffer(gl.ARRAY_BUFFER, this.quad);
      gl.enableVertexAttribArray(0);
      gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
      gl.bindVertexArray(null);

      this.pBg = new Program(gl, VS_QUAD, FS_BG, 'bg');
      this.pBright = new Program(gl, VS_QUAD, FS_BRIGHT, 'bright');
      this.pBlur = new Program(gl, VS_QUAD, FS_BLUR, 'blur');
      this.pComp = new Program(gl, VS_QUAD, FS_COMPOSITE, 'comp');

      this.rt = {};
      this.w = 0; this.h = 0; this.dpr = 1;
      this.resize();
    }

    resize() {
      const gl = this.gl, canvas = this.canvas;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = Math.max(2, Math.round(canvas.clientWidth * dpr));
      const h = Math.max(2, Math.round(canvas.clientHeight * dpr));
      if (w === this.w && h === this.h) return;
      this.w = w; this.h = h; this.dpr = dpr;
      canvas.width = w; canvas.height = h;
      for (const k in this.rt) { gl.deleteTexture(this.rt[k].tex); gl.deleteFramebuffer(this.rt[k].fbo); }
      this.rt = {
        scene: makeRT(gl, w, h),
        a1: makeRT(gl, Math.max(2, w >> 1), Math.max(2, h >> 1)),
        a2: makeRT(gl, Math.max(2, w >> 1), Math.max(2, h >> 1)),
        b1: makeRT(gl, Math.max(2, w >> 2), Math.max(2, h >> 2)),
        b2: makeRT(gl, Math.max(2, w >> 2), Math.max(2, h >> 2)),
      };
    }

    beginScene() {
      const gl = this.gl;
      gl.bindFramebuffer(gl.FRAMEBUFFER, this.rt.scene.fbo);
      gl.viewport(0, 0, this.w, this.h);
      gl.clearColor(0, 0, 0, 1);
      gl.clear(gl.COLOR_BUFFER_BIT);
    }

    drawBackground(time) {
      const gl = this.gl;
      gl.disable(gl.DEPTH_TEST);
      this.pBg.use();
      gl.bindVertexArray(this.qa);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    }

    blit(prog, targetTex, extra) {
      const gl = this.gl;
      gl.bindVertexArray(this.qa);
      gl.bindFramebuffer(gl.FRAMEBUFFER, targetTex ? targetTex.fbo : null);
      gl.viewport(0, 0, targetTex ? targetTex.w : this.w, targetTex ? targetTex.h : this.h);
      if (extra) extra(prog);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    }

    post(o) {
      const gl = this.gl, rt = this.rt;
      // post passes must OVERWRITE: the scene uses additive blending (ONE,ONE),
      // which would otherwise make every full-screen pass accumulate frame to frame.
      gl.disable(gl.BLEND);
      gl.disable(gl.DEPTH_TEST);
      // bright pass -> a1
      this.blit(this.pBright, rt.a1, (p) => {
        p.use();
        gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, rt.scene.tex);
        p.i('uTex', 0);
        p.f('uThreshold', o.threshold != null ? o.threshold : 0.72);
        p.f('uKnee', 0.18);
      });
      // blur level A
      const blur = (src, dst, dx, dy) => {
        this.blit(this.pBlur, dst, (p) => {
          p.use();
          gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, src.tex);
          p.i('uTex', 0);
          p.v2('uDir', dx, dy);
          p.v2('uTexel', 1 / src.w, 1 / src.h);
        });
      };
      blur(rt.a1, rt.a2, 1, 0);
      blur(rt.a2, rt.a1, 0, 1);

      // downsample a1 -> b1 then blur (wider halo)
      this.blit(this.pBlur, rt.b1, (p) => {
        p.use();
        gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, rt.a1.tex);
        p.i('uTex', 0);
        p.v2('uDir', 0.0, 0.0);
        p.v2('uTexel', 1 / rt.a1.w, 1 / rt.a1.h);
      });
      blur(rt.b1, rt.b2, 1, 0); blur(rt.b2, rt.b1, 0, 1);

      // composite to screen
      this.blit(this.pComp, null, (p) => {
        p.use();
        gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, rt.scene.tex); p.i('uScene', 0);
        gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, rt.a1.tex); p.i('uBloomA', 1);
        gl.activeTexture(gl.TEXTURE2); gl.bindTexture(gl.TEXTURE_2D, rt.b1.tex); p.i('uBloomB', 2);
        p.f('uTime', o.time || 0);
        p.f('uBloom', o.bloom != null ? o.bloom : 1.0);
        p.f('uExposure', o.exposure != null ? o.exposure : 1.0);
        p.f('uGrain', o.grain != null ? o.grain : 0.045);
        p.f('uVignette', o.vignette != null ? o.vignette : 1.0);
        p.f('uCA', o.ca != null ? o.ca : 0.35);
        p.f('uFade', o.fade != null ? o.fade : 1.0);        p.v2('uRes', this.w, this.h);
      });
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.ONE, gl.ONE);
    }
  }

  return { mat4, Program, makeBuffer, makeRT, Renderer,
           VS_POINT, FS_POINT, VS_LINE, FS_LINE, VS_BEAM, FS_BEAM, VS_QUAD };
})();
