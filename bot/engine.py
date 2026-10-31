"""对话引擎：收到消息 -> 装配上下文 -> LLM -> 拟人化发送 -> 成长反思。"""
import datetime
import random
import threading

from . import humanize
from memory_brain import brainmap
from . import persona as persona_mod
from . import repetition
from . import reply_style
from . import state as state_mod
from .log import get
from .transport import segments_to_text

log = get("engine")


class Engine:
    def __init__(self, cfg, store, llm, api, persona, growth, config_path=None,
                 inner_life=None):
        self.cfg = cfg
        self.store = store
        self.llm = llm
        self.api = api
        self.persona = persona
        self.growth = growth
        self.config_path = config_path
        self.inner_life = inner_life
        self.allowed = set(cfg["qq"].get("allowed_users") or [])

    # ---------- 入口 ----------
    def handle(self, ev):
        uid = ev.get("user_id")
        text = segments_to_text(ev.get("message"))
        if not text:
            log.info("空消息，忽略")
            return
        cmd = text.strip().lstrip("/#").strip()

        # 没绑定主人前，只认「绑定」指令，其他人一概不理
        if not self.cfg["qq"].get("admin_id"):
            if cmd in ("绑定", "bind"):
                self._bind_owner(uid)
                self.api.send_private(
                    uid, [{"type": "text", "data": {"text": "行，绑上了。以后只烦你一个。"}}]
                )
            else:
                log.info("未绑定主人，忽略 %s: %s", uid, text[:40])
            return

        if self.allowed and uid not in self.allowed:
            log.info("忽略非白名单 %s", uid)
            return
        log.info("<- %s: %s", uid, text)

        # 先取上下文再落库，避免本轮消息重复
        recent = self.store.recent_messages(16)
        last_user = self.store.last_user_message()
        gap = persona_mod.gap_text(last_user["ts"] if last_user else None)

        msg_id = self.store.add_message("user", text)
        self.store.set_state("last_user_id", uid)
        self.store.mark_proactive_replied()

        if cmd in ("状态", "status"):
            self._send_status(uid)
            return
        if cmd in ("记忆", "memory"):
            self._send_memories(uid)
            return
        if cmd in ("日记", "diary"):
            self._send_diary(uid)
            return
        if cmd in ("遗忘", "forget", "记忆状态"):
            self._send_forgetting(uid)
            return
        if cmd == "记住" or cmd.startswith("记住 "):
            self._cmd_remember(uid, cmd[2:].strip(), msg_id)
            return
        if cmd == "忘掉" or cmd.startswith("忘掉 "):
            self._cmd_forget(uid, cmd[2:].strip())
            return
        if cmd == "恢复" or cmd.startswith("恢复 "):
            self._cmd_restore(uid, cmd[2:].strip())
            return
        if cmd == "纠正" or cmd.startswith("纠正 "):
            self._cmd_correct(uid, cmd[2:].strip(), msg_id)
            return
        if cmd in ("帮助", "help", "指令"):
            self.api.send_private(
                uid,
                [{"type": "text", "data": {"text":
                    "状态 看心情/亲密度\n记忆 看她记住了什么（带编号）\n"
                    "记住 <一句话> 让她记下来\n忘掉 <编号> 让她别再提这条\n"
                    "恢复 <编号> 把忘掉/更正的找回来\n纠正 <编号> <新说法> 用新的覆盖旧的\n"
                    "遗忘 看哪些记忆快淡了\n日记 看昨天的日记\n帮助 这条"}}],
            )
            return

        st = state_mod.load(self.store)
        state_mod.daily_upkeep(self.store, st)

        try:
            bubbles = self._reply(uid, text, st, recent, gap)
        except Exception as e:  # noqa: BLE001
            log.exception("生成回复失败: %s", e)
            self.api.send_private(
                uid,
                [{"type": "text", "data": {"text": "等下，我这边卡了一下"}}],
            )
            return

        joined = " ".join(bubbles)
        if getattr(self.llm, "api_key", ""):
            self.growth.reflect_async(text, joined, msg_id=msg_id)
            if self.inner_life:
                threading.Thread(
                    target=self.inner_life.after_exchange,
                    args=(text, joined), daemon=True,
                ).start()

    # ---------- 生成 ----------
    def _reply(self, uid, text, st, recent, gap, extra_note=""):
        if not getattr(self.llm, "api_key", ""):
            from . import fallback

            bubbles = fallback.reply(text, st)
            humanize.send_bubbles(
                self.api, uid, bubbles, self.cfg.get("humanize", {}), self.store
            )
            log.info("-> %s（离线模板）: %s", uid, " | ".join(bubbles))
            return bubbles

        mem_cfg = self.cfg.get("memory") or {}
        k = int(mem_cfg.get("top_k") or self.cfg["bot"].get("memory_top_k", 6))
        budget = int(mem_cfg.get("budget_tokens", 320))
        min_r = float(mem_cfg.get("min_retention", 0.06))
        profile_n = int(mem_cfg.get("profile_top_n", 10))
        bm_on = bool(mem_cfg.get("brainmap_enabled", True))
        regions = brainmap.query_regions(text) if bm_on else set()
        memories = self.store.search_memories(
            text, limit=k, budget_tokens=budget, min_retention=min_r, regions=regions
        )
        recall = getattr(self.store, "last_recall", {}) or {}
        bm_text = ""
        if bm_on:
            counts, archived = self.store.region_counts()
            bm_text = brainmap.summary(counts, archived)
        log.info(
            "召回 %d 条 / 约 %d tok（候选 %d，预算 %d，区域 %s）",
            len(memories), recall.get("tokens", 0),
            recall.get("candidates", 0), budget,
            "/".join(brainmap.label(r) for r in sorted(regions)) or "全部",
        )
        profile = self.store.profile_ranked(profile_n)
        diary = self.store.latest_diary()
        life = diary.get("next_day") if diary else None

        style = reply_style.pick(self.cfg)
        extra = self._extra_hint(text) + "\n\n" + reply_style.prompt(style)
        if extra_note:
            extra += "\n\n" + extra_note
        msgs = persona_mod.build_chat_messages(
            self.persona, st, memories, profile, diary, life, recent, text, gap,
            history_limit=int(self.cfg["bot"].get("history_messages", 10)),
            brainmap=bm_text,
            max_prompt_chars=int(self.cfg["bot"].get("max_prompt_chars", 6000)),
            extra=extra,
            profile_limit=profile_n,
        )
        try:
            data = self.llm.chat_json(msgs)
        except Exception:  # noqa: BLE001
            # 兜底：去掉历史与记忆，用最短提示词再试一次
            log.warning("首次生成失败，改用精简提示词重试")
            short_msgs = persona_mod.build_chat_messages(
                self.persona, st, [], {}, None, None, [], text, ""
            )
            data = self.llm.chat_json(
                short_msgs, temperature=0.9, max_tokens=220
            )

        bubbles = self._bubbles_of(data)
        if not bubbles:
            bubbles = [random.choice(["……", "行吧", "嗯"])]

        # 炒冷饭检测：和最近说过的话太像，就重写一次
        bubbles = self._avoid_repeat(
            bubbles, msgs, st, memories, profile, diary, life, recent, text, gap,
            brainmap_text=bm_text,
        )
        bubbles = reply_style.apply(bubbles, style, self.cfg)

        # 禁用词：命中就重写一次，仍命中就删掉那一句
        if self._has_banned(bubbles):
            log.info("命中禁用词，重写一次：%s", " | ".join(bubbles))
            try:
                banned_note = ("\n\n注意：绝对不要出现这些词：" +
                               "、".join(self._banned()) + "，换个说法表达同样的意思。")
                msgs2 = persona_mod.build_chat_messages(
                    self.persona, st, memories, profile, diary, life, recent, text, gap,
                    history_limit=int(self.cfg["bot"].get("history_messages", 10)),
                    max_prompt_chars=int(self.cfg["bot"].get("max_prompt_chars", 6000)),
                    extra=extra + banned_note,
                )
                bubbles2 = self._bubbles_of(self.llm.chat_json(msgs2))
                if bubbles2:
                    bubbles = bubbles2
            except Exception:  # noqa: BLE001
                log.warning("禁用词重写失败", exc_info=True)
            bubbles = self._drop_banned(bubbles)
            if not bubbles:
                bubbles = ["嗯。"]

        humanize.send_bubbles(
            self.api, uid, bubbles, self.cfg.get("humanize", {}), self.store
        )
        repetition.update_topics(self.store, bubbles)

        state_mod.apply_delta(st, data.get("mood_delta"))
        state_mod.add_intimacy(self.store, st, data.get("intimacy_delta", 0))
        state_mod.save(self.store, st)
        log.info("-> %s: %s", uid, " | ".join(bubbles))
        return bubbles

    def handle_recovery(self, text):
        """重启补答：消息已在库里，只补生成与发送，不重复入库。"""
        uid = int(self.cfg["qq"].get("admin_id") or 0)
        if not uid:
            return
        st = state_mod.load(self.store)
        recent = self.store.recent_messages(16)
        last_user = self.store.last_user_message()
        gap = persona_mod.gap_text(last_user["ts"] if last_user else None)
        note = ("【补答】你刚才掉线了，现在才看到 TA 这句话。自然补上就行，"
                "别解释太多，也别复述对方的话。")
        bubbles = self._reply(uid, text, st, recent, gap, extra_note=note)
        repetition.update_topics(self.store, bubbles)
        log.info("补答完成: %s", " | ".join(bubbles))

    # ---------- 工具 ----------
    def _extra_hint(self, text):
        """把「今天已经问过什么」塞进提示词，避免复读。"""
        if not self.cfg["bot"].get("anti_repeat", True):
            return ""
        return repetition.topics_hint(self.store)

    def _bubbles_of(self, data):
        return [
            b.strip()
            for b in (data.get("messages") or [])
            if isinstance(b, str) and b.strip()
        ][:3]

    def _avoid_repeat(self, bubbles, msgs, st, memories, profile, diary, life,
                      recent, text, gap, brainmap_text=""):
        """和最近说过的话太像时，重写一次。"""
        threshold = float(self.cfg["bot"].get("repeat_threshold", 0.6))
        recent_bot = [
            m["content"] for m in self.store.recent_messages(30) if m["role"] == "bot"
        ][-8:]
        worst = repetition.max_similarity(bubbles, recent_bot)
        asked = repetition.asked_today(self.store)
        dup_topic = any(
            repetition.is_question(b) and (set(repetition.topic_of(b)) & asked)
            for b in bubbles
        )
        if not dup_topic and worst < threshold:
            return bubbles
        log.info("检测到重复（话题重复=%s，相似度 %.2f），重写一次", dup_topic, worst)
        sample = recent_bot[-1][:30] if recent_bot else ""
        note = ("\n\n你刚才已经说过类似的话（例如「%s」），这次必须换个说法和话题，"
                "别再问同一件事。" % sample)
        try:
            msgs2 = persona_mod.build_chat_messages(
                self.persona, st, memories, profile, diary, life, recent, text, gap,
                history_limit=int(self.cfg["bot"].get("history_messages", 10)),
                max_prompt_chars=int(self.cfg["bot"].get("max_prompt_chars", 6000)),
                extra=self._extra_hint(text) + note,
                brainmap=brainmap_text,
            )
            new_bubbles = self._bubbles_of(self.llm.chat_json(msgs2))
            if new_bubbles:
                return new_bubbles
        except Exception:  # noqa: BLE001
            log.warning("重写失败，沿用原回复", exc_info=True)
        return bubbles

    def _banned(self):
        return [w for w in (self.persona.get("banned") or []) if w]

    def _has_banned(self, bubbles):
        return any(w in b for w in self._banned() for b in bubbles)

    def _drop_banned(self, bubbles):
        banned = self._banned()
        return [b for b in bubbles if not any(w in b for w in banned)]

    def _bind_owner(self, uid):
        """第一次收到私聊时，把对方设为主人和唯一白名单。"""
        if self.cfg["qq"].get("admin_id"):
            return
        if not uid:
            return
        self.cfg["qq"]["admin_id"] = int(uid)
        self.cfg["qq"]["allowed_users"] = [int(uid)]
        self.allowed = {int(uid)}
        try:
            from . import config as cfgmod

            cfgmod.save(self.cfg, self.config_path)
        except Exception:  # noqa: BLE001
            log.exception("保存主人绑定失败")
        try:
            info = self.api.call("get_stranger_info", {"user_id": int(uid)})
            nick = (info.get("data") or {}).get("nickname")
            if nick:
                self.store.upsert_profile("QQ昵称", nick, 0.9)
        except Exception:  # noqa: BLE001
            log.debug("获取昵称失败", exc_info=True)
        log.info("首次绑定主人：QQ=%s", uid)

    def _send_memories(self, uid):
        mems = self.store.all_memories(12)
        if not mems:
            self.api.send_private(uid, [{"type": "text", "data": {"text": "还没记住什么。"}}])
            return
        lines = ["她还记着（编号 · 内容）："]
        for m in mems:
            mark = ""
            if m.get("archived"):
                mark = "〔已忘〕"
            elif m.get("superseded_by"):
                mark = "〔已更正〕"
            lines.append(f"#{m['id']} {mark}{m['content']}")
        lines.append("（想说“忘掉 #3”或“纠正 #3 新的说法”都行）")
        self.api.send_private(uid, [{"type": "text", "data": {"text": "\n".join(lines)}}])

    def _cmd_remember(self, uid, content, msg_id=None):
        if not content:
            self._say(uid, "记住什么？例如「记住 我周三要交论文」")
            return
        mid = self.store.add_memory("fact", content, weight=1.3,
                                    source=("msg:%s" % msg_id) if msg_id else "manual")
        self._say(uid, f"记下了 #{mid}：{content}" if mid else "这句我没记下来。")

    def _cmd_forget(self, uid, arg):
        mid = self._parse_id(arg)
        if not mid:
            self._say(uid, "要忘掉哪条？先发「记忆」看编号。")
            return
        m = self.store.get_memory(mid)
        if not m:
            self._say(uid, f"没有 #{mid} 这条。")
            return
        self.store.forget(mid)
        self._say(uid, f"行，#{mid} 我不提了。（想找回：恢复 #{mid}）")

    def _cmd_restore(self, uid, arg):
        mid = self._parse_id(arg)
        if not mid:
            self._say(uid, "要恢复哪条？先发「遗忘」看已忘掉的编号。")
            return
        m = self.store.get_memory(mid)
        if not m:
            self._say(uid, f"没有 #{mid} 这条。")
            return
        self.store.restore(mid)
        self._say(uid, f"想起来了 #{mid}：{m['content'][:24]}")

    def _cmd_correct(self, uid, arg, msg_id=None):
        parts = arg.split(" ", 1)
        mid = self._parse_id(parts[0]) if parts else None
        new_text = (parts[1] if len(parts) > 1 else "").strip()
        if not mid or not new_text:
            self._say(uid, "用法：纠正 #12 用户现在在杭州做后端")
            return
        old = self.store.get_memory(mid)
        if not old:
            self._say(uid, f"没有 #{mid} 这条。")
            return
        new_id = self.store.add_memory(old["kind"], new_text, weight=max(1.2, old["weight"]),
                                       source=("msg:%s" % msg_id) if msg_id else "manual")
        self.store.supersede(mid, new_id)
        self._say(uid, f"改了：{old['content'][:18]} → {new_text[:18]}（旧的那条不再提）")

    def _parse_id(self, s):
        s = (s or "").strip().lstrip("#")
        return int(s) if s.isdigit() else None

    def _say(self, uid, text):
        self.api.send_private(uid, [{"type": "text", "data": {"text": text}}])

    def _send_forgetting(self, uid):
        """#遗忘：看看哪些记忆快淡了。"""
        try:
            from memory_brain import forgetting as fog
        except Exception:  # noqa: BLE001
            return
        stats = self.store.memory_stats()
        mems = self.store.all_memories(400)
        active = [m for m in mems if not m.get("archived") and not m.get("superseded_by")]
        rows = sorted(active, key=lambda m: fog.retention(m))
        fading = rows[:5]
        lines = [
            f"【记忆】共 {stats['total']} 条，活跃 {stats['active']} 条，"
            f"归档 {stats['archived']} 条，已更正 {stats['superseded']} 条，"
            f"平均保持度 {stats['avg_retention']:.2f}",
        ]
        if fading:
            lines.append("最可能被忘掉的：")
            for m in fading:
                lines.append(f"#{m['id']} [{m['kind']}] {m['content'][:24]}（{fog.describe(m)}）")
        archived = [m for m in mems if m.get("archived")][:5]
        if archived:
            lines.append("已忘掉的（可恢复 #编号）：" + "、".join("#%d" % m["id"] for m in archived))
        self.api.send_private(uid, [{"type": "text", "data": {"text": "\n".join(lines)}}])

    def _send_diary(self, uid):
        d = self.store.latest_diary()
        if not d:
            self.api.send_private(uid, [{"type": "text", "data": {"text": "还没写过日记，晚上 11 点再说。"}}])
            return
        lines = [
            f"【{d['date']} 的日记】",
            d.get("summary") or "",
            f"记住的细节：{d.get('highlights') or '无'}",
            f"明天打算：{d.get('next_day') or '无'}",
        ]
        self.api.send_private(uid, [{"type": "text", "data": {"text": "\n".join(lines)}}])

    def _send_status(self, uid):
        st = state_mod.load(self.store)
        profile = self.store.profile_dict()
        diary = self.store.latest_diary()
        lines = [
            f"【状态】{state_mod.describe(st)}",
            f"【性格】" + "，".join(f"{k}{v:.0f}" for k, v in st["traits"].items()),
        ]
        if profile:
            lines.append("【档案】" + "；".join(f"{k}:{v}" for k, v in list(profile.items())[:8]))
        if diary:
            lines.append(f"【昨天】{diary.get('summary', '')}")
        self.api.send_private(uid, [{"type": "text", "data": {"text": "\n".join(lines)}}])
