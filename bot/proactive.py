"""主动消息调度：按粘人档参数决定何时开口、说什么。"""
import datetime
import random
import threading
import time

from . import humanize
from . import persona as persona_mod
from . import state as state_mod
from .log import get

log = get("proactive")


def _parse_hhmm(s):
    h, m = str(s).split(":")
    return int(h) * 60 + int(m)


class Proactive(threading.Thread):
    def __init__(self, cfg, store, llm, api, persona, inner=None):
        super().__init__(daemon=True, name="proactive")
        self.cfg = cfg
        self.store = store
        self.llm = llm
        self.api = api
        self.persona = persona
        self.inner = inner
        self.pc = cfg.get("proactive", {})

    # ---------- 时间判断 ----------
    def _in_quiet(self, now):
        start = _parse_hhmm(self.pc.get("quiet_start", "00:30"))
        end = _parse_hhmm(self.pc.get("quiet_end", "08:30"))
        cur = now.hour * 60 + now.minute
        if start <= end:
            return start <= cur < end
        return cur >= start or cur < end

    def _tod_weight(self, hour):
        if 6 <= hour < 10:
            return 0.8
        if 10 <= hour < 13:
            return 1.0
        if 13 <= hour < 18:
            return 1.2
        if 18 <= hour < 22:
            return 1.5
        return 0.6

    def _day_start(self, now):
        d = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return d.timestamp()

    # ---------- 约束 ----------
    def can_fire(self, now=None):
        if not self.pc.get("enabled", True):
            return False
        now = now or datetime.datetime.now()
        if self._in_quiet(now):
            return False
        ts = now.timestamp()

        cap = int(self.pc.get("daily_cap", 10))
        if self.store.count_proactive_today(self._day_start(now)) >= cap:
            return False

        gap = float(self.pc.get("min_gap_minutes", 8)) * 60
        last_p = self.store.last_proactive()
        if last_p and ts - last_p["ts"] < gap:
            return False

        last_user = self.store.last_user_message()
        last_bot = self.store.last_bot_message()

        # 正在聊，别插嘴
        newest = max(
            [x["ts"] for x in (last_user, last_bot) if x] or [0]
        )
        if newest and ts - newest < float(self.pc.get("idle_minutes", 20)) * 60:
            return False

        # 对方没回，别连环追问
        if last_bot and (not last_user or last_bot["ts"] > last_user["ts"]):
            trailing = self.store.bot_count_after_last_user()
            if trailing >= int(self.pc.get("unanswered_limit", 2)):
                cooldown = float(self.pc.get("unanswered_cooldown_minutes", 180)) * 60
                if ts - last_bot["ts"] < cooldown:
                    return False
        return True

    def _trigger_for(self, now):
        hour = now.hour
        if 6 <= hour < 10:
            return "morning"
        if hour >= 22 or hour < 2:
            return "night"
        return random.choices(
            ["idle", "memory", "mood"], weights=[0.5, 0.3, 0.2]
        )[0]

    # ---------- 主循环 ----------
    def run(self):
        log.info("主动调度已启动（上限 %s 条/天）", self.pc.get("daily_cap", 10))
        tick = int(self.pc.get("tick_seconds", 60))
        while True:
            try:
                time.sleep(tick)
                self.tick()
            except Exception:  # noqa: BLE001
                log.exception("主动调度 tick 失败")

    def tick(self):
        if not self.can_fire():
            return
        now = datetime.datetime.now()
        st = state_mod.load(self.store)
        weight = self._tod_weight(now.hour)
        scale = 0.7 + st["intimacy"] / 200.0
        p = float(self.pc.get("base_prob_per_minute", 0.009)) * weight * scale
        # tick 间隔折算成分钟
        p *= max(0.05, int(self.pc.get("tick_seconds", 60)) / 60.0)
        if random.random() > p:
            return
        self.fire(now, st, self._trigger_for(now))

    def fire(self, now, st, trigger):
        log.info("主动开口：trigger=%s", trigger)
        recent = self.store.recent_messages(10)
        # 优先用她脑子里已生成的想法开口
        thought = self.inner.pick_for_proactive() if self.inner else None
        seed = thought["content"] if thought else " ".join(
            m["content"] for m in recent[-4:]
        ) or "你们的关系"
        if thought:
            log.info("使用想法[%s]：%s", thought["kind"], thought["content"])
        memories = self.store.search_memories(seed, 3)
        profile = self.store.profile_dict()
        diary = self.store.latest_diary()
        life = diary.get("next_day") if diary else None
        last_user = self.store.last_user_message()
        gap = persona_mod.gap_text(last_user["ts"] if last_user else None)

        msgs = persona_mod.build_proactive_messages(
            self.persona, st, memories, profile, diary, life, recent, trigger, gap,
            thought=thought["content"] if thought else None,
            as_question=bool(thought and thought["kind"] == "疑问"),
        )
        try:
            data = self.llm.chat_json(msgs, max_tokens=220)
        except Exception:  # noqa: BLE001
            log.exception("主动消息生成失败")
            return

        bubbles = [
            b.strip() for b in (data.get("messages") or []) if isinstance(b, str) and b.strip()
        ][: int(self.pc.get("max_bubbles", 2))]
        if not bubbles:
            return

        user_id = self._target_user()
        if not user_id:
            log.warning("没有可发送的目标用户")
            return

        humanize.send_bubbles(self.api, user_id, bubbles, self.cfg.get("humanize", {}), self.store)
        self.store.log_proactive(trigger, " ".join(bubbles))
        state_mod.apply_delta(st, data.get("mood_delta"))
        state_mod.add_intimacy(self.store, st, data.get("intimacy_delta", 0))
        state_mod.save(self.store, st)
        log.info("-> %s（主动）: %s", user_id, " | ".join(bubbles))

    def _target_user(self):
        admin = self.cfg["qq"].get("admin_id") or 0
        if admin:
            return admin
        allowed = self.cfg["qq"].get("allowed_users") or []
        if allowed:
            return int(allowed[0])
        return int(self.store.get_state("last_user_id", 0) or 0)
