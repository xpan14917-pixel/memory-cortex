# 架构

## 进程与数据流

```
QQ 小号
  │ 扫码登录
NapCat（OneBot v11）
  │ HTTP 事件回调 → 127.0.0.1:8080/onebot
  ▼
main.py ── 装配 ──► Engine / Growth / Proactive / InnerLife
  │
  ├─ 收消息
  │    recent_messages(16)
  │    regions = brainmap.query_regions(text)
  │    memories = store.search_memories(text, limit, budget, regions)
  │    prompt = persona.build_chat_messages(...)   ← 静态块在前，动态在后
  │    llm.chat_json(prompt)
  │    humanize.send_bubbles()                      ← 分条 + 打字延迟
  │
  └─ 回复后（异步）
       growth.reflect(user_text, bot_text)
         llm 抽 JSON：memories / profile / intimacy_delta / mood_delta
         store.add_memory(...)                     ← 去重、算 S、算分区
         maybe_decay()                             ← 每天一次归档
       23:00 → write_diary()
```

## 模块边界

| 层 | 模块 | 职责 | 是否可复用 |
|---|---|---|---|
| 记忆引擎 | `memory_brain.store` | SQLite schema、迁移、CRUD、复习、归档 | ✅ |
| | `memory_brain.forgetting` | 纯函数：S / R / 归档判定 | ✅ |
| | `memory_brain.brainmap` | 纯函数：分区分类 + 摘要 | ✅ |
| | `memory_brain.retrieval` | 打分、预算、复习写回 | ✅ |
| 适配层 | `bot.engine` | 组装 prompt、调 LLM、发消息 | ❌（QQ 专用） |
| | `bot.persona` | 人格卡 + 规则 + 历史装配 | 半可复用 |
| | `bot.growth` | 反思抽记忆、日记、每日归档 | 半可复用 |
| | `bot.transport` | OneBot v11 HTTP/事件 | ❌ |
| 表现层 | `panel/*` | 只读可视化，WebGL2 | ✅（只依赖导出的 JSON） |

`memory_brain` 不 import `bot`，所以可以单独 `pip install` 使用；`bot` 依赖 `memory_brain`，反向不成立。

## prompt 的结构（前缀缓存友好）

```
[静态] 你是「知夏」…13 条聊天规则…输出格式     ← 每轮完全一致，可被上下文缓存
[动态] 【现在】时间/间隔
       【你现在的状态】心情/精力/亲密
       【记忆分区】生活 12｜关系 12｜认知 11
       【你记得的事】- [经历] …
       【你了解的 TA】- 作息：…
       【最近的对话】TA：… / 我：…
       [风格提示]
```

静态块用 `persona._static_block()` 生成，`build_system()` 保证它永远在最前面。

## 面板渲染管线

```
data.real.js ──► js/data.js 构建区域/节点/连线
                        │
                  WebGL2（js/gl.js）
                    ├─ 场景 FBO：背景渐变、光束、连线、点精灵
                    ├─ 亮部提取 → 两段高斯 → 叠加
                    └─ ACES 色调映射 + 颗粒 + 暗角 + 色散
                        │
                  DOM HUD（js/hud.js）：小地图、记忆构成、认知流、时间轴
```

关键约束：**全屏后处理必须 `disable(BLEND)`**。场景用的是加性混合（ONE, ONE），
后处理若沿用同一状态，每帧会叠加到上一帧，几秒后整屏变白。
