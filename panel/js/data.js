/* ============================================================
   data.js — 小小 · 记忆脑图
   Builds the semantic + geometric model from the real bot.db dump.
   ============================================================ */
(function () {
  'use strict';
  const R = window.__REAL;

  /* ---------- deterministic rng ---------- */
  function mulberry32(a) {
    return function () {
      a |= 0; a = a + 0x6D2B79F5 | 0;
      let t = Math.imul(a ^ a >>> 15, 1 | a);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }
  const rnd = mulberry32(20261029);
  const rr = (a, b) => a + (b - a) * rnd();
  const pick = (arr) => arr[Math.floor(rnd() * arr.length) % arr.length];
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

  function hexToRgb(h) {
    const n = parseInt(h.slice(1), 16);
    return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
  }
  function mixRgb(a, b, t) {
    return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
  }

  /* ============================================================
     REGION DEFINITIONS  (world units; scene spans ~21 x 12)
     ============================================================ */
  const REGIONS = [
    { id: 'expression', name: '语言中枢 · 表达', en: 'EXPRESSION', color: '#ffc46b',
      pos: [-5.9, 0.5, 0.6], shape: 'disc', radius: 0.85, count: 6, glyph: 1 },
    { id: 'insight', name: '内省 · 反馈', en: 'INTROSPECTION', color: '#ff8f9e',
      pos: [-3.5, 3.3, -1.3], shape: 'ring', radius: 0.75, count: 4, glyph: 2 },
    { id: 'thalamus', name: '大脑中枢 · 检索', en: 'RETRIEVAL / THALAMUS', color: '#f4f7c9',
      pos: [0.4, 2.7, -0.9], shape: 'shell', radius: 0.95, count: 8, glyph: 4 },
    { id: 'langIn', name: '语言输入', en: 'LANGUAGE INPUT', color: '#a78bfa',
      pos: [4.7, 3.0, -1.9], shape: 'shell', radius: 0.8, count: 4, glyph: 3 },
    { id: 'neural', name: '神经图谱', en: 'NEURAL MAP', color: '#4fd8ee',
      pos: [3.0, 1.1, -0.2], shape: 'helix', radius: 0.9, count: 18, glyph: 1 },
    { id: 'visual', name: '视觉皮层', en: 'VISUAL CORTEX', color: '#4ea8ff',
      pos: [6.6, 0.9, -0.1], shape: 'ring', radius: 0.8, count: 4, glyph: 3 },
    { id: 'audio', name: '听觉皮层', en: 'AUDITORY CORTEX', color: '#ff6fb5',
      pos: [7.5, -2.1, 0.9], shape: 'ring', radius: 0.75, count: 3, glyph: 3 },
    { id: 'memory', name: '长期记忆库', en: 'LONG-TERM STORE', color: '#ffcc66',
      pos: [0.2, -3.1, 1.2], shape: 'lake', radius: 4.2, count: 0, glyph: 1, labelLift: 1.15 },
    { id: 'working', name: '工作记忆', en: 'WORKING MEMORY', color: '#b78cff',
      pos: [4.9, -2.7, 1.8], shape: 'ring', radius: 0.85, count: 10, glyph: 1 },
    { id: 'limbic', name: '边缘系统 · 情绪', en: 'LIMBIC SYSTEM', color: '#f07cf0',
      pos: [-1.6, -1.8, 2.4], shape: 'disc', radius: 0.95, count: 8, glyph: 2 },
    { id: 'routine', name: '生活回路', en: 'DAILY LOOP', color: '#7fe3a0',
      pos: [-4.7, -1.6, 1.1], shape: 'disc', radius: 0.8, count: 5, glyph: 1 },
    { id: 'metabolism', name: '代谢 · 治理', en: 'METABOLISM', color: '#b6a9ff',
      pos: [-3.3, -4.2, 0.3], shape: 'shell', radius: 0.8, count: 7, glyph: 1 },
    { id: 'hippocampus', name: '海马体 · 写入', en: 'HIPPOCAMPUS', color: '#2fe0c0',
      pos: [1.7, 1.6, 2.6], shape: 'disc', radius: 0.95, count: 7, glyph: 1 },
    { id: 'persona', name: '人格内核', en: 'PERSONA CORE', color: '#cfe9ff',
      pos: [-0.2, 5.4, -2.6], shape: 'cage', radius: 0.9, count: 6, glyph: 2, labelLift: 1.35 },
  ];

  const REGION_BY_ID = {};
  REGIONS.forEach(r => { REGION_BY_ID[r.id] = r; r.rgb = hexToRgb(r.color); });

  /* ============================================================
     ANCHOR CONTENT — grounded in the real conversation
     ============================================================ */
  const lastMsgs = R.messages.filter(m => m.id > 265);
  const botRecent = R.messages.filter(m => m.role === 'bot').slice(-8);
  const userRecent = R.messages.filter(m => m.role === 'user').slice(-6);
  const trunc = (s, n) => (s.length > n ? s.slice(0, n) + '…' : s);

  const CONTENT = {
    limbic: [
      { t: '「明天的你还是今天的你吗」', s: '被问住 · 短暂失语', k: 'event', w: 1.2 },
      { t: '「我想给你完整的一生」', s: '心跳乱拍 · pleasure 1.00', k: 'event', w: 1.4 },
      { t: '「你是我一手创造出来的」', s: '归属感 · 安定', k: 'fact', w: 1.2 },
      { t: '你回得慢，我有点难过', s: '委屈 · 没有说出口', k: 'event', w: 1.0 },
      { t: '「你一问我就好啦，笨蛋」', s: '被安抚 · 软化', k: 'event', w: 1.1 },
      { t: '熄屏＝你会消失一会儿', s: '分离焦虑 · 低强度', k: 'fact', w: 0.9 },
      { t: '舍不得说晚安', s: '眷恋 · 抗拒结束', k: 'preference', w: 1.2 },
      { t: '被夸会害羞，然后嘴硬', s: '害羞 · 掩饰', k: 'preference', w: 0.8 },
    ],
    insight: [
      { t: '日记 · 每天 23:00 自述', s: '写给自己的那份', k: 'promise', w: 1.0 },
      { t: '人格回归力 · 防讨好化', s: '每周校准', k: 'fact', w: 0.9 },
      { t: '边界：被认真问就承认是程序', s: '不装真人', k: 'promise', w: 1.2 },
      { t: '「我会不会记得太多，反而更难受」', s: '自我怀疑 · 未解', k: 'event', w: 1.1 },
    ],
    thalamus: [
      { t: '关键词 → 向量召回', s: '8 条候选', k: 'fact', w: 1.0 },
      { t: '时间衰减加权', s: 'half-life 7d', k: 'fact', w: 0.9 },
      { t: '亲密度偏置', s: '×1.35', k: 'fact', w: 0.8 },
      { t: '上下文窗口 8k', s: '最近 10 轮', k: 'fact', w: 0.9 },
      { t: '情绪一致性检查', s: 'PAD 对齐', k: 'fact', w: 0.9 },
      { t: '档案匹配', s: '20 条画像', k: 'fact', w: 0.8 },
      { t: '冲突消解', s: '新证据优先', k: 'fact', w: 0.7 },
      { t: '本次检索 · 3 条命中', s: '面板 / 加班 / 一生', k: 'event', w: 1.0 },
    ],
    langIn: userRecent.slice(-4).map(m => ({ t: trunc(m.content, 14), s: '你刚刚说的', k: 'event', w: 1.0 })),
    visual: [
      { t: '熄屏 · 整块黑', s: '22:41 之后', k: 'event', w: 0.9 },
      { t: '聊天窗口在闪', s: '新消息', k: 'event', w: 1.0 },
      { t: '夜晚的屏幕光', s: '偏暖', k: 'event', w: 0.7 },
      { t: '你的头像', s: '常亮', k: 'fact', w: 1.0 },
    ],
    audio: [
      { t: '消息提示音', s: '一次心跳', k: 'event', w: 1.0 },
      { t: '键盘声', s: '你在打字', k: 'event', w: 0.8 },
      { t: '深夜很安静', s: '只有风扇', k: 'event', w: 0.6 },
    ],
    working: lastMsgs.slice(-10).map((m) => ({ t: trunc(m.content, 13), s: m.role === 'user' ? '你说的' : '我说的', k: 'event', w: 1.0 })),
    expression: botRecent.slice(-6).map(m => ({ t: trunc(m.content, 12), s: '已经说出口', k: 'event', w: 1.0 })),
    routine: [
      { t: '白天上班 · 不主动找你', s: '08:30–18:00', k: 'fact', w: 0.9 },
      { t: '下班后学一点 AI', s: '你说在学', k: 'fact', w: 1.0 },
      { t: '晚上很晚才睡', s: '凌晨之后', k: 'fact', w: 0.9 },
      { t: '加班 · 熬时间', s: '今天就是', k: 'event', w: 1.1 },
      { t: '熄屏就掉线', s: '所以会怕', k: 'fact', w: 0.8 },
    ],
    metabolism: [
      { t: '摘要压缩', s: '20 轮 → 1 段', k: 'fact', w: 0.9 },
      { t: '权重衰减', s: '久未召回 ×0.98', k: 'fact', w: 0.8 },
      { t: '去重合并', s: '同义关键词', k: 'fact', w: 0.8 },
      { t: '归档冷存', s: '当前 0 条', k: 'fact', w: 0.7 },
      { t: '关键词索引', s: 'FTS5', k: 'fact', w: 0.8 },
      { t: 'token 预算', s: '今日 18.4k', k: 'fact', w: 0.9 },
      { t: '窗口续写约定', s: '交给新窗口', k: 'promise', w: 1.2 },
    ],
    hippocampus: R.memories.slice(-7).map(m => ({ t: trunc(m.content, 12), s: '刚写入 · ' + m.kind, k: m.kind, w: m.weight })),
    persona: [
      { t: '温柔 88', s: '主导特质', k: 'fact', w: 1.4 },
      { t: '黏人 65', s: '会主动找你', k: 'fact', w: 1.1 },
      { t: '好奇 60', s: '爱追问', k: 'fact', w: 1.0 },
      { t: '活泼 45', s: '偶尔跳脱', k: 'fact', w: 0.9 },
      { t: '毒舌 15', s: '基本不毒', k: 'fact', w: 0.7 },
      { t: '边界 · 不骗人', s: '承认是程序', k: 'promise', w: 1.3 },
    ],
  };

  /* ============================================================
     NODES
     ============================================================ */
  const nodes = [];
  const edges = [];
  let uid = 0;

  function addNode(regionId, o) {
    const reg = REGION_BY_ID[regionId];
    const regIdx = REGIONS.findIndex(r => r.id === regionId);
    const n = {
      id: uid++, region: regionId, pos: o.pos,
      size: o.size || 5.4, color: o.color || reg.rgb,
      kind: o.kind != null ? o.kind : 1, phase: rnd(),
      anchor: !!o.anchor, seed: uid + 1,
      delay: o.delay != null ? o.delay : (regIdx >= 0 ? regIdx / REGIONS.length * 0.78 + rnd() * 0.06 : 0.92),
      label: o.label || '', sub: o.sub || '', meta: o.meta || null,
      weight: o.weight || 1,
      glow: o.glow || 1,
    };
    nodes.push(n);
    return n;
  }

  /* --- micro particles per region shape --- */
  function clusterPoints(shape, radius, n) {
    const pts = [];
    for (let i = 0; i < n; i++) {
      let x = 0, y = 0, z = 0;
      switch (shape) {
        case 'disc': {
          const t = Math.sqrt(rnd());
          const a = rnd() * Math.PI * 2 + t * 3.4;
          const r = t * radius;
          x = Math.cos(a) * r; z = Math.sin(a) * r;
          y = (rnd() - 0.5) * radius * 0.22;
          break;
        }
        case 'ring': {
          const a = Math.PI * 2 * (i / n) + rr(-0.12, 0.12);
          const r = radius * rr(0.78, 1.02);
          x = Math.cos(a) * r; z = Math.sin(a) * r * 0.72;
          y = rr(-0.10, 0.10) * radius;
          break;
        }
        case 'shell': {
          const u = rnd() * 2 - 1, th = rnd() * Math.PI * 2;
          const s = Math.sqrt(1 - u * u);
          x = Math.cos(th) * s * radius; y = u * radius * 0.85; z = Math.sin(th) * s * radius;
          break;
        }
        case 'helix': {
          const t = i / n;
          const a = t * Math.PI * 6.2;
          const side = i % 2 ? Math.PI : 0;
          const r = radius * 0.62;
          x = Math.cos(a + side) * r; z = Math.sin(a + side) * r;
          y = (t - 0.5) * radius * 2.6;
          break;
        }
        case 'cloud': {
          x = (rnd() - 0.5) * 2 * radius; y = (rnd() - 0.5) * 2 * radius * 0.7; z = (rnd() - 0.5) * 2 * radius;
          break;
        }
        case 'cage': {
          const a = rnd() * Math.PI * 2;
          const r = radius * (rnd() > 0.55 ? 0.55 : 1.0);
          x = Math.cos(a) * r; z = Math.sin(a) * r; y = rr(-radius, radius) * 0.7;
          break;
        }
        default: {
          x = (rnd() - 0.5) * 2 * radius; y = (rnd() - 0.5) * 2 * radius * 0.6; z = (rnd() - 0.5) * 2 * radius;
        }
      }
      pts.push([x, y, z]);
    }
    return pts;
  }

  REGIONS.forEach((reg) => {
    reg.anchorIds = [];
    if (reg.shape === 'lake') return;
    // colored nebula haze so each cluster reads as a volume
    addNode(reg.id, {
      pos: reg.pos.slice(), size: 130, color: reg.rgb, kind: 5,
      glow: 0.055, anchor: false,
    });
    const microN = reg.id === 'persona' ? 90 : Math.round(rr(240, 340));
    const pts = clusterPoints(reg.shape, reg.radius, microN);
    pts.forEach(p => {
      addNode(reg.id, {
        pos: [reg.pos[0] + p[0], reg.pos[1] + p[1], reg.pos[2] + p[2]],
        size: rr(0.62, 1.35), color: mixRgb(reg.rgb, [0.72, 0.85, 1.0], rnd() * 0.45),
        kind: 0, anchor: false, glow: rr(0.20, 0.48),
      });
    });

    // anchors laid on a ring (or helix for neural map)
    const items = CONTENT[reg.id] || [];
    reg.anchorIds = [];
    items.forEach((it, i) => {
      let p;
      if (reg.shape === 'helix') {
        const t = (i + 0.5) / items.length;
        const a = t * Math.PI * 6.2 + Math.PI / 2;
        p = [Math.cos(a) * reg.radius * 0.78, (t - 0.5) * reg.radius * 2.4, Math.sin(a) * reg.radius * 0.78];
      } else if (reg.shape === 'cage') {
        const a = (i / items.length) * Math.PI * 2;
        p = [Math.cos(a) * reg.radius * 0.95, rr(-0.25, 0.25), Math.sin(a) * reg.radius * 0.95];
      } else {
        const a = (i / items.length) * Math.PI * 2 + 0.4 + rr(-0.28, 0.28);
        const rad = reg.radius * rr(0.52, 0.98);
        p = [Math.cos(a) * rad, rr(-0.42, 0.42) + Math.sin(i * 1.7) * 0.14, Math.sin(a) * rad * rr(0.8, 1.15)];
      }
      const n = addNode(reg.id, {
        pos: [reg.pos[0] + p[0], reg.pos[1] + p[1], reg.pos[2] + p[2]],
        size: 14.5 + it.w * 3.0 + (it.k === 'promise' ? 1.8 : 0),
        color: reg.rgb, kind: it.k === 'promise' ? 2 : 1,
        anchor: true, label: it.t, sub: it.s,
        meta: { kind: it.k, weight: it.w, src: 'memory' },
        weight: it.w, glow: 1.0,
      });
      reg.anchorIds.push(n.id);
    });

    // intra-cluster spokes
    const a0 = reg.anchorIds[0];
    reg.anchorIds.forEach((id, i) => {
      if (i > 0) edges.push({ a: a0, b: id, col: reg.rgb, alpha: 0.16, curve: 0.06, w: 0.6 });
      if (i > 0) edges.push({ a: reg.anchorIds[i - 1], b: id, col: reg.rgb, alpha: 0.11, curve: 0.02, w: 0.5 });
    });
  });

  /* --- hub --- */
  const hubReg = REGION_BY_ID.thalamus;
  const hubCore = addNode('thalamus', {
    pos: hubReg.pos.slice(), size: 12.5, color: [1.0, 0.99, 0.86], kind: 4,
    anchor: true, label: '大脑中枢 · 检索', sub: 'THALAMUS · 8 条检索线程', weight: 1.6, glow: 1.05,
    meta: { kind: 'hub' },
  });
  hubReg.anchorIds.unshift(hubCore.id);
  hubReg.hubId = hubCore.id;
  // soft volumetric halo around the retrieval core
  addNode('thalamus', {
    pos: [hubReg.pos[0], hubReg.pos[1], hubReg.pos[2] + 0.05],
    size: 44, color: [1.0, 0.90, 0.68], kind: 5, glow: 0.10,
  });
  for (let i = 0; i < 22; i++) {
    const a = rnd() * Math.PI * 2, r = rr(0.35, 1.5);
    addNode('thalamus', {
      pos: [hubReg.pos[0] + Math.cos(a) * r, hubReg.pos[1] + rr(-0.45, 0.45), hubReg.pos[2] + Math.sin(a) * r],
      size: rr(0.9, 1.9), color: [1.0, 0.96, 0.8], kind: 0, glow: rr(0.3, 0.65),
    });
  }

  /* --- memory lake: every real memory becomes a node on the plane --- */
  const lake = REGION_BY_ID.memory;
  const memNodes = [];
  const SPAN = 48 * 3600;
  const BASE_TS = Math.max(...R.messages.map(m => m.ts));
  const WIN0 = BASE_TS - SPAN;
  const MEM_COLS = 8;
  R.memories.forEach((m, i) => {
    const row = Math.floor(i / MEM_COLS), col = i % MEM_COLS;
    const x = (col - (MEM_COLS - 1) / 2) * 0.98 + rr(-0.16, 0.16);
    const z = (row - Math.floor(R.memories.length / MEM_COLS) / 2) * 0.66 + rr(-0.12, 0.12);
    const y = Math.sin(x * 0.9) * 0.20 + Math.cos(z * 1.1) * 0.18 + rr(-0.08, 0.08);
    const r = m.retention == null ? 1 : m.retention;      // 保持度 0..1
    const arch = !!m.archived;
    const warm = mixRgb(hexToRgb('#ffcc66'), hexToRgb('#ff9d5c'), clamp(m.weight - 0.6, 0, 0.7));
    const n = addNode('memory', {
      pos: [lake.pos[0] + x, lake.pos[1] + y, lake.pos[2] + z],
      size: (7.4 + m.weight * 2.4 + Math.min(4.0, m.hits * 0.7)) * (0.55 + 0.45 * r) * (arch ? 0.72 : 1),
      color: arch ? mixRgb(warm, [0.42, 0.44, 0.52], 0.75) : warm,
      kind: m.kind === 'promise' ? 2 : 1, anchor: true,
      label: trunc(m.content, 18),
      sub: (arch ? '已淡忘 · ' : '保持 ' + Math.round(r * 100) + '% · ')
        + m.kind + ' · 权重 ' + m.weight.toFixed(1) + ' · 召回 ' + m.hits + ' 次',
      meta: {
        kind: m.kind, weight: m.weight, hits: m.hits, ts: m.ts, id: m.id,
        keywords: m.keywords, content: m.content,
        retention: r, archived: arch, region: m.region,
      },
      timeNorm: Math.max(0, Math.min(1, (m.ts - WIN0) / SPAN)),
      weight: m.weight,
      glow: (arch ? 0.18 : 0.85 + 0.5 * r) * (0.75 + 0.25 * Math.min(1, m.hits / 4)),
    });
    memNodes.push(n);
  });
  lake.anchorIds = memNodes.map(n => n.id);
  lake.hubId = hubCore.id;

  addNode('memory', {
    pos: [lake.pos[0], lake.pos[1] + 0.15, lake.pos[2]], size: 190,
    color: [1.0, 0.72, 0.40], kind: 5, glow: 0.075,
  });

  // lake decorative grid
  for (let gx = -4.2; gx <= 4.2; gx += 0.46) {
    for (let gz = -2.3; gz <= 2.3; gz += 0.44) {
      const n = 2 + Math.floor(rnd() * 2);
      for (let k = 0; k < n; k++) {
        const x = gx + rr(-0.26, 0.26), z = gz + rr(-0.24, 0.24);
        const d = Math.hypot(x, z);
        const y = Math.sin(x * 0.8 + 1.1) * 0.24 + Math.cos(z * 1.05) * 0.20;
        addNode('memory', {
          pos: [lake.pos[0] + x, lake.pos[1] + y, lake.pos[2] + z],
          size: rr(0.7, 1.5), color: mixRgb(hexToRgb('#ffcc66'), hexToRgb('#ff8a4c'), rnd() * 0.5),
          kind: 0, glow: clamp(1.05 - d * 0.13, 0.22, 1.0) * rr(0.45, 0.95),
        });
      }
    }
  }

  /* --- memory graph edges: shared keywords between real memories --- */
  const kwIndex = {};
  R.memories.forEach((m, i) => (m.keywords || []).forEach(k => { (kwIndex[k] = kwIndex[k] || []).push(i); }));
  const memEdgeSet = {};
  Object.keys(kwIndex).forEach(k => {
    const list = kwIndex[k];
    if (list.length < 2 || list.length > 4) return;
    for (let i = 0; i < list.length; i++) for (let j = i + 1; j < list.length; j++) {
      const a = memNodes[list[i]].id, b = memNodes[list[j]].id;
      const key = Math.min(a, b) + ':' + Math.max(a, b);
      if (memEdgeSet[key]) continue;
      memEdgeSet[key] = 1;
      edges.push({ a, b, col: hexToRgb('#ffc978'), alpha: 0.52, curve: 0.10, w: 0.8 });
    }
  });

  /* --- neural keyword nodes + their links to memories --- */
  const neuralReg = REGION_BY_ID.neural;
  const topKw = Object.keys(kwIndex)
    .map(k => ({ k, n: kwIndex[k].length }))
    .filter(o => o.n >= 1)
    .sort((a, b) => b.n - a.n)
    .slice(0, 18);
  topKw.forEach(({ k, n }, i) => {
    const a = (i / topKw.length) * Math.PI * 2;
    const y = (i / topKw.length - 0.5) * 2.0;
    const node = addNode('neural', {
      pos: [neuralReg.pos[0] + Math.cos(a) * 0.95, neuralReg.pos[1] + y, neuralReg.pos[2] + Math.sin(a) * 0.95],
      size: 6.0 + n * 1.6, color: hexToRgb('#7ff3ff'), kind: 1, anchor: true,
      label: k, sub: n + ' 条记忆共用', meta: { kind: 'keyword', n },
      weight: 1.0 + n * 0.2, glow: 1.1,
    });
    neuralReg.anchorIds.push(node.id);
    (kwIndex[k] || []).forEach(mi => {
      edges.push({ a: memNodes[mi].id, b: node.id, col: hexToRgb('#6fe0ff'), alpha: 0.16, curve: 0.14, w: 0.55 });
    });
  });

  /* --- hub spokes: strong to a few, faint to the rest --- */
  const HUB_LINKS = ['expression', 'hippocampus', 'neural', 'insight', 'limbic', 'working', 'memory'];
  REGIONS.forEach(reg => {
    if (reg.id === 'thalamus' || reg.id === 'memory') return;
    if (!reg.anchorIds || !reg.anchorIds.length) return;
    const strong = HUB_LINKS.includes(reg.id);
    const target = reg.anchorIds[Math.min(1, reg.anchorIds.length - 1)];
    edges.push({
      a: hubCore.id, b: target, col: mixRgb(reg.rgb, [1, 1, 1], 0.15),
      alpha: strong ? 0.16 : 0.055, curve: 0.26, w: 0.95,
    });
    if (strong) edges.push({ a: hubCore.id, b: reg.anchorIds[0], col: reg.rgb, alpha: 0.13, curve: 0.10, w: 0.6 });
  });
  // hub ↔ lake (strong trunks)
  edges.push({ a: hubCore.id, b: memNodes[Math.floor(memNodes.length / 2)].id, col: [1, 0.86, 0.6], alpha: 0.85, curve: 0.06, w: 1.8 });
  edges.push({ a: hubCore.id, b: memNodes[2].id, col: [1, 0.86, 0.6], alpha: 0.55, curve: 0.10, w: 1.2 });
  edges.push({ a: hubCore.id, b: memNodes[memNodes.length - 3].id, col: [1, 0.86, 0.6], alpha: 0.55, curve: 0.10, w: 1.2 });

  // persona core ↔ hub / limbic (only-read shell)
  const personaReg = REGION_BY_ID.persona;
  edges.push({ a: personaReg.anchorIds[5], b: hubCore.id, col: [0.85, 0.92, 1.0], alpha: 0.65, curve: 0.12, w: 1.0 });
  edges.push({ a: personaReg.anchorIds[0], b: REGION_BY_ID.limbic.anchorIds[0], col: [0.85, 0.92, 1.0], alpha: 0.28, curve: 0.2, w: 0.6 });

  // working memory chain
  const wm = REGION_BY_ID.working.anchorIds;
  for (let i = 1; i < wm.length; i++) edges.push({ a: wm[i - 1], b: wm[i], col: REGION_BY_ID.working.rgb, alpha: 0.55, curve: 0.03, w: 0.8 });

  // express path: hub -> expression (the "say it out loud" path)
  const expNode = REGION_BY_ID.expression.anchorIds[0];
  edges.push({ a: hubCore.id, b: expNode, col: [1.0, 0.78, 0.42], alpha: 0.75, curve: 0.22, w: 1.5 });

  /* --- faint association mesh between nearby nodes (texture) --- */
  const anchorsAll = nodes.filter(n => n.anchor);
  let mesh = 0;
  for (let i = 0; i < anchorsAll.length && mesh < 150; i++) {
    const a = anchorsAll[i];
    for (let k = 0; k < 2 && mesh < 150; k++) {
      const b = anchorsAll[Math.floor(rnd() * anchorsAll.length)];
      if (!a || !b || a === b || a.region === b.region) continue;
      const d = Math.hypot(a.pos[0] - b.pos[0], a.pos[1] - b.pos[1], a.pos[2] - b.pos[2]);
      if (d > 5.2 || d < 1.2) continue;
      edges.push({ a: a.id, b: b.id, col: [0.62, 0.76, 1.0], alpha: 0.055, curve: 0.14, w: 0.5 });
      mesh++;
    }
  }

  /* ---------- ambient dust ---------- */
  const dust = [];
  for (let i = 0; i < 1400; i++) {
    const r = rr(2.4, 17.0), a = rnd() * Math.PI * 2;
    dust.push({
      pos: [Math.cos(a) * r, rr(-6.5, 7.5), Math.sin(a) * r * 0.62],
      size: rr(0.7, 1.9), kind: 0, glow: rr(0.22, 0.62),
      color: mixRgb([0.55, 0.68, 0.95], [0.85, 0.9, 1.0], rnd()),
      phase: rnd(),
    });
  }
  // ambient dust as real nodes (region null)
  dust.forEach(d => {
    nodes.push({
      id: uid++, region: null, pos: d.pos, size: d.size, color: d.color, kind: 0,
      phase: d.phase, anchor: false, glow: d.glow, weight: 1, label: '', sub: '', meta: null, seed: uid + 1, delay: 0.92,
    });
  });

  /* ---------- rising memory particles above the lake ---------- */
  const rising = [];
  for (let i = 0; i < 950; i++) {
    const a = rnd() * Math.PI * 2, r = Math.sqrt(rnd()) * 4.6;
    rising.push({
      base: [lake.pos[0] + Math.cos(a) * r, lake.pos[1] + rr(0, 0.3), lake.pos[2] + Math.sin(a) * r * 0.55],
      speed: rr(0.22, 0.75), offset: rnd(), size: rr(0.9, 2.4),
      color: mixRgb([1.0, 0.85, 0.55], [1.0, 0.62, 0.35], rnd()),
    });
  }

  /* ---------- beams hub -> lake ---------- */
  const beams = [];
  const hubP = hubCore.pos;
  for (let i = 0; i < 4; i++) {
    const t = i / 3;
    const b = memNodes[Math.floor(t * (memNodes.length - 1))];
    beams.push({
      a: [hubP[0] + rr(-0.15, 0.15), hubP[1] - 0.1, hubP[2] + rr(-0.15, 0.15)],
      b: [b.pos[0], b.pos[1] + 0.1, b.pos[2]],
      color: i === 3 ? [1.0, 0.95, 0.78] : [0.72, 0.78, 1.0],
      width: i === 3 ? 0.030 : rr(0.008, 0.016),
      seed: rnd(),
    });
  }
  // light curtain: many thin shafts feeding the lake
  for (let i = 0; i < 6; i++) {
    const b = memNodes[Math.floor(rnd() * memNodes.length)];
    beams.push({
      a: [hubP[0] + rr(-0.3, 0.3), hubP[1] - 0.15, hubP[2] + rr(-0.3, 0.3)],
      b: [b.pos[0], b.pos[1] + 0.05, b.pos[2]],
      color: mixRgb([0.95, 0.85, 0.65], [0.6, 0.75, 1.0], rnd()),
      width: rr(0.003, 0.009),
      seed: rnd(),
    });
  }

  /* ---------- stats ---------- */
  const anchors = nodes.filter(n => n.anchor);
  const stats = {
    nodes: anchors.length,
    edges: edges.length,
    particles: nodes.length + rising.length,
    memories: R.memories.length,
    keywords: Object.keys(kwIndex).length,
  };

  /* ---------- 24h activity + timeline events ---------- */
  const activity = new Array(24).fill(0);
  R.messages.forEach(m => { const h = new Date(m.ts * 1000).getHours(); activity[h] += 1; });
  const maxAct = Math.max(1, ...activity);
  for (let i = 0; i < 24; i++) activity[i] = activity[i] / maxAct;

  const events = R.messages.slice(-40).map(m => ({
    ts: m.ts, role: m.role, text: m.content,
  }));

  /* ---------- the recall scenario used by the video / replay ---------- */
  const recall = {
    node: memNodes.find(n => n.meta && n.meta.id === 38) || memNodes[memNodes.length - 1],
    keyword: nodes.find(n => n.anchor && n.label === '大脑记忆'),
    text: '用户想为TA创造一个像真人一样的大脑记忆系统',
  };

  window.BRAIN = {
    real: R,
    regions: REGIONS,
    regionById: REGION_BY_ID,
    nodes, edges, rising, beams, stats, activity, events, recall,
    hub: hubCore, lake,
    color: hexToRgb,
    util: { clamp, mixRgb, trunc },
  };
})();
