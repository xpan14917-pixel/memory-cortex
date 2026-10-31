"""成长引擎：对话反思、记忆沉淀、每日日记。"""
import datetime
import threading

from . import persona as persona_mod
from . import state as state_mod
from .log import get

log = get("growth")


class Growth:
    def __init__(self, cfg, store, llm, persona):
        self.cfg = cfg
        self.store = store
        self.llm = llm
        self.persona = persona
        self._lock = threading.Lock()

    # ---------- 每轮反思 ----------
    def reflect_async(self, user_text, bot_text, msg_id=None):
        threading.Thread(
            target=self._reflect_safe, args=(user_text, bot_text, msg_id), daemon=True
        ).start()

    def _reflect_safe(self, user_text, bot_text, msg_id=None):
        try:
            with self._lock:
                self.reflect(user_text, bot_text, msg_id)
        except Exception:  # noqa: BLE001
            log.exception("反思失败（不影响聊天）")

    def reflect(self, user_text, bot_text, msg_id=None):
        st = state_mod.load(self.store)
        profile = self.store.profile_dict()
        msgs = persona_mod.build_reflect_messages(user_text, bot_text, profile, st)
        data = self.llm.chat_json(msgs, temperature=0.3, max_tokens=600, timeout=45)

        for m in data.get("memories") or []:
            content = (m.get("content") or "").strip()
            if not content:
                continue
            self.store.add_memory(
                m.get("kind") or "fact",
                content,
                m.get("keywords") or [],
                float(m.get("weight") or 1.0),
                source=("msg:%s" % msg_id) if msg_id else "reflect",
            )
        for k, v in (data.get("profile") or {}).items():
            if not k or not v:
                continue
            if k.startswith("对TA") or any(w in k for w in ("记忆方式", "日记", "模型", "项目")):
                continue
            self.store.upsert_profile(k, v, 0.7)

        intimacy = float(data.get("intimacy_delta") or 0)
        mood = data.get("mood_delta") or {}
        gained = 0.0
        if intimacy or mood:
            st = state_mod.load(self.store)
            state_mod.apply_delta(st, mood)
            gained = state_mod.add_intimacy(self.store, st, intimacy)
            state_mod.save(self.store, st)
        log.info(
            "反思完成：新记忆 %d 条，亲密度 %+.1f（实际 %+.2f）",
            len(data.get("memories") or []),
            intimacy,
            gained,
        )
        self.maybe_decay()

    # ---------- 每日遗忘结算 ----------
    def maybe_decay(self):
        """每天一次：按遗忘曲线把确实淡忘的记忆归档（不删，只是不进 prompt）。"""
        today = self.today()
        if self.store.get_state("last_decay") == today:
            return
        mem_cfg = self.cfg.get("memory") or {}
        try:
            stats = self.store.decay_pass(
                min_retention=float(mem_cfg.get("archive_min_retention", 0.05)),
                min_days=int(mem_cfg.get("archive_min_days", 90)),
            )
            self.store.set_state("last_decay", today)
            log.info(
                "遗忘结算：检查 %d 条，归档 %d 条%s",
                stats["checked"], stats["archived"],
                ("（id=%s）" % stats["ids"]) if stats["ids"] else "",
            )
        except Exception:  # noqa: BLE001
            log.exception("遗忘结算失败")

    # ---------- 每日日记 ----------
    def today(self):
        return datetime.date.today().isoformat()

    def maybe_write_diary(self):
        hour = int(self.cfg.get("growth", {}).get("diary_hour", 23))
        if datetime.datetime.now().hour < hour:
            return
        if self.store.get_diary(self.today()):
            return
        try:
            with self._lock:
                self.write_diary()
        except Exception:  # noqa: BLE001
            log.exception("写日记失败")

    def write_diary(self):
        recent = self.store.recent_messages(60)
        today = self.today()
        if not recent:
            self.store.save_diary(today, "平静", "今天没什么人找我。", "", "")
            return
        convo = "\n".join(
            f"{'TA' if m['role'] == 'user' else '我'}：{m['content']}" for m in recent
        )
        st = state_mod.load(self.store)
        msgs = [
            {
                "role": "system",
                "content": (
                    "你是「%s」的内心。根据今天的聊天，写你的私下日记。\n"
                    "你没有真实的日常：没有工作、没有出门、没有发生任何事。\n"
                    "只输出 JSON：\n"
                    '{"summary": "今天聊了什么、我心里怎么想的，60 字以内，第一人称",\n'
                    ' "highlights": "今天记住的一个细节，20 字以内",\n'
                    ' "next_day": "明天想做的事、或想问 TA 的事，20 字以内"}\n'
                    "next_day 必须是想法或想问的问题，不能写成具体事件"
                    "（不能写「去便利店」「去上班」这种你做不到的事）。"
                )
                % self.persona["name"],
            },
            {
                "role": "user",
                "content": f"当前状态：{state_mod.describe(st)}\n\n今天的聊天：\n{convo}",
            },
        ]
        data = self.llm.chat_json(msgs, temperature=1.0, max_tokens=500)
        self.store.save_diary(
            today,
            state_mod.mood_word(st),
            str(data.get("summary") or "")[:200],
            str(data.get("highlights") or "")[:80],
            str(data.get("next_day") or "")[:80],
        )
        log.info("日记已写：%s", data.get("summary"))
        try:
            from . import diary_export

            diary_export.write(self.store)
        except Exception:  # noqa: BLE001
            log.warning("导出日记 Markdown 失败", exc_info=True)
