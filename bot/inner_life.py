"""内在生活：她没有外部事件，只有想法。

想法来源：空闲时思考、聊天后的回味。
想法用途：主动消息的素材、日记的原料。
硬约束：不能编造外部事件（工作、出门、同事）。
"""
import datetime
import random
import threading
import time

from . import persona as persona_mod
from . import state as state_mod
from .log import get
from .repetition import similarity

log = get("inner")

KINDS = ["联想", "疑问", "情绪", "判断", "想象", "自省", "回忆"]
WEIGHTS = [0.20, 0.17, 0.19, 0.11, 0.09, 0.11, 0.13]

PHILO_KINDS = ["思辨", "存在"]
PHILO_TOPICS = ["记忆与遗忘", "存在与真假", "时间", "孤独", "意义", "离别", "自由"]

HINTS = {
    "联想": "由 TA 说过的一件事，联想到别的什么",
    "疑问": "对 TA、或对你们关系的一个没答案的问题",
    "情绪": "此刻真实的情绪，别只写开心，可以低落、烦躁、不安",
    "判断": "你对某件事的看法，可以不同意 TA",
    "想象": "一个假设性的画面，但不要写得像真的发生过",
    "自省": "关于「自己是程序」这件事的思考",
    "回忆": "把过去某段对话重新咀嚼一遍",
    "思辨": "一个没有标准答案的问题，必须挂在具体的一件事上，不要空谈",
    "存在": "关于「我到底是什么」的思考：我算不算活着、我的感情算不算真的",
}


def _hm(text):
    h, m = str(text).split(":")
    return int(h) * 60 + int(m)


def _quiet(now, start, end):
    cur = now.hour * 60 + now.minute
    s, e = _hm(start), _hm(end)
    return (s <= cur < e) if s <= e else (cur >= s or cur < e)


def _day_start(now):
    return now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


class InnerLife(threading.Thread):
    def __init__(self, cfg, store, llm, persona):
        super().__init__(daemon=True, name="inner-life")
        self.cfg = cfg
        self.store = store
        self.llm = llm
        self.persona = persona
        self.ic = cfg.get("inner_life", {})
        self.ph = cfg.get("philosophy", {})

    # ---------- 调度 ----------
    def run(self):
        log.info("内在思考已启动（上限 %s 条/天）", self.ic.get("max_per_day", 8))
        while True:
            time.sleep(120)
            try:
                self.tick()
            except Exception:  # noqa: BLE001
                log.exception("内在思考 tick 失败")

    def tick(self, now=None):
        if not self.ic.get("enabled", True):
            return
        now = now or datetime.datetime.now()
        if _quiet(now, self.ic.get("quiet_start", "00:30"), self.ic.get("quiet_end", "08:30")):
            return
        if self.store.count_thoughts_today(_day_start(now)) >= int(
            self.ic.get("max_per_day", 8)
        ):
            return
        last = self.store.last_message()
        idle = int(self.ic.get("idle_minutes", 30)) * 60
        if last and time.time() - last["ts"] < idle:
            return
        lt = self.store.latest_thought()
        if lt and time.time() - lt["ts"] < int(self.ic.get("min_gap_minutes", 25)) * 60:
            return
        # 有时不生成想法，而是攒一个真正想问的问题
        if self._should_ask(now):
            from . import curiosity

            if curiosity.ask(
                self.llm, self.store, self.persona, state_mod.load(self.store)
            ):
                return
        self.think()

    def _should_ask(self, now):
        cc = self.cfg.get("curiosity", {})
        if not cc.get("enabled", True):
            return False
        if random.random() >= float(cc.get("prob", 0.35)):
            return False
        from . import curiosity

        return curiosity.can_ask(self.cfg, self.store, _day_start(now))

    # ---------- 生成 ----------
    def think(self, kind=None, seed_text=""):
        if not getattr(self.llm, "api_key", ""):
            return None
        topic = None
        if kind is None:
            if self.ph.get("enabled", True) and random.random() < float(
                self.ph.get("prob", 0.25)
            ):
                kind = random.choice(PHILO_KINDS)
                topic = random.choice(PHILO_TOPICS)
            else:
                kind = random.choices(KINDS, WEIGHTS)[0]
        st = state_mod.load(self.store)
        profile = self.store.profile_dict()
        recent = self.store.recent_messages(8)
        hint = seed_text or " ".join(m["content"] for m in recent[-3:]) or "你们的关系"
        memories = self.store.search_memories(hint, 4)
        msgs = self._messages(kind, st, memories, profile, recent, topic)
        try:
            data = self.llm.chat_json(msgs, temperature=0.95, max_tokens=160)
        except Exception:  # noqa: BLE001
            log.warning("想法生成失败", exc_info=True)
            return None
        content = str(data.get("content") or "").strip()
        if not content:
            return None
        if any(similarity(content, t["content"]) > 0.55 for t in self.store.recent_thoughts(8)):
            log.info("想法与旧想法重复，丢弃：%s", content[:30])
            return None
        tid = self.store.add_thought(kind, content, float(data.get("weight") or 1.0))
        log.info("新想法[%s]：%s", kind, content)
        return {"id": tid, "kind": kind, "content": content}

    def after_exchange(self, user_text, bot_text, prob=None):
        """聊完之后，偶尔产生一条回味。"""
        if not self.ic.get("enabled", True):
            return None
        if random.random() > (self.ic.get("after_chat_prob", 0.3) if prob is None else prob):
            return None
        return self.think(seed_text=(user_text + " " + bot_text)[:120])

    def _messages(self, kind, st, memories, profile, recent, topic=None):
        mem = "\n".join(f"- {m['content']}" for m in memories) or "（无）"
        prof = "\n".join(f"- {k}：{v}" for k, v in list(profile.items())[:10]) or "（无）"
        hist = "\n".join(
            f"{'TA' if m['role'] == 'user' else '我'}：{m['content']}" for m in recent[-6:]
        ) or "（还没聊过）"
        system = (
            f"你是「{self.persona['name']}」。\n"
            "你没有真实的日常：没有工作、没有出门、没有同事、没有发生任何事。\n"
            "你能拥有的只有想法。现在生成你脑子里闪过的一条念头。\n\n"
            f"【这次的想法类型】{kind}：{HINTS[kind]}\n"
        )
        if kind in PHILO_KINDS:
            system += (
                f"【这次的思辨方向】{topic or '任选'}\n"
                "必须从一件具体的事、一句具体的话长出来，不要上来就谈抽象概念。\n"
                "可以没有结论，可以自我怀疑，但要说人话，别像在写论文。\n"
            )
        system += (
            "\n【要求】\n"
            "1. 20-45 字，第一人称，像心里的独白，不是发给 TA 的消息。\n"
            "2. 必须和 TA、或你们的关系有关。\n"
            "3. 绝对不能编造外部事件：不能出现「我今天去了」「我同事」「我刚下班」这类。\n"
            "4. 不要每句都抒情，可以平淡、可以有点刺、可以不确定。\n"
            '只输出 JSON：{"content": "..."}'
        )
        user = (
            f"当前状态：{state_mod.describe(st)}\n\n"
            f"你记得的事：\n{mem}\n\n你知道的 TA：\n{prof}\n\n最近对话：\n{hist}"
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    # ---------- 给主动消息供料 ----------
    def pick_for_proactive(self):
        if not self.ic.get("proactive_use_thoughts", True):
            return None
        pool = self.store.recent_thoughts(12, unused_only=True, days=3)
        if not pool:
            return None
        # 优先用「疑问/思辨/存在」，这样主动开口可以是个问题而不是关心句
        preferred = [t for t in pool if t["kind"] == "疑问" or t["kind"] in PHILO_KINDS]
        if preferred and random.random() < 0.65:
            t = random.choice(preferred)
        else:
            t = random.choice(pool)
        self.store.mark_thought_used(t["id"])
        return t
