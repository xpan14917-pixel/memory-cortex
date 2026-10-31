"""连续多轮真实对话测试：验证多轮上下文、记忆累积、人设稳定。"""
import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot import config as cfgmod  # noqa: E402
from bot import persona as persona_mod  # noqa: E402
from bot import state as state_mod  # noqa: E402
from bot.engine import Engine  # noqa: E402
from bot.growth import Growth  # noqa: E402
from bot.llm import LLM  # noqa: E402
from memory_brain.store import Store  # noqa: E402

TURNS = [
    "在吗",
    "今天好累啊，上了一天班",
    "我下周三要考科目二",
    "你觉得我能过吗",
    "中午吃了碗面，难吃死了",
    "对了，我不吃香菜",
    "我妈又催我找对象，烦",
    "晚安，睡了",
]


class MockApi:
    def __init__(self):
        self.sent = []

    def send_private(self, uid, message):
        self.sent.append(message[0]["data"]["text"])
        return {"status": "ok"}

    def call(self, action, payload=None, timeout=None):
        return {"status": "ok", "data": {"nickname": "测试"}}


def main():
    cfg = cfgmod.load()
    cfg["qq"]["admin_id"] = 10001
    cfg["qq"]["allowed_users"] = [10001]
    cfg["humanize"].update({"min_delay": 0, "per_char": 0, "per_char_jitter": 0,
                            "between_min": 0, "between_max": 0})

    persona = persona_mod.load(ROOT / "persona.json")
    store = Store(pathlib.Path(tempfile.mkdtemp()) / "t.db")
    lc = cfg["llm"]
    llm = LLM(lc["base_url"], lc["api_key"], lc["model"])
    api = MockApi()
    growth = Growth(cfg, store, llm, persona)
    engine = Engine(cfg, store, llm, api, persona, growth)

    failures = 0
    for i, text in enumerate(TURNS, 1):
        api.sent.clear()
        try:
            engine.handle({
                "post_type": "message", "message_type": "private",
                "user_id": 10001,
                "message": [{"type": "text", "data": {"text": text}}],
            })
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"{i:02d} TA: {text}\n     ERROR {e}\n")
            continue
        reply = " | ".join(api.sent) if api.sent else "(空)"
        print(f"{i:02d} TA: {text}")
        print(f"   阿七: {reply}\n")

    import time
    time.sleep(2)  # 等反思线程落库
    st = state_mod.load(store)
    print("=== 结束状态 ===")
    print("亲密度:", round(st["intimacy"], 1), "阶段:", st["stage"],
          "心情:", state_mod.mood_word(st))
    print("记忆条数:", len(store.all_memories()))
    for m in store.all_memories()[:8]:
        print("  -", m["content"])
    print("档案:", store.profile_dict())
    print("失败轮次:", failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
