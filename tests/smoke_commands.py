# -*- coding: utf-8 -*-
"""用假的 API/LLM 跑一遍命令，验证 #记住/#忘掉/#恢复/#纠正 真的写库。"""
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bot.engine import Engine            # noqa: E402
from bot.growth import Growth            # noqa: E402
from memory_brain import configure        # noqa: E402
from memory_brain.store import Store      # noqa: E402


class FakeAPI:
    def __init__(self):
        self.sent = []

    def send_private(self, uid, segs):
        self.sent.append("".join(s.get("data", {}).get("text", "") for s in segs))

    def call(self, action, params=None):
        return {"status": "ok", "data": {}}

    def get_login_info(self):
        return {"status": "ok", "data": {"user_id": 1, "nickname": "x"}}


class FakeLLM:
    api_key = ""

    def chat_json(self, msgs, **kw):
        return {"messages": ["嗯"]}


def main():
    tmp = tempfile.TemporaryDirectory()
    store = Store(pathlib.Path(tmp.name) / "t.db")
    cfg = {"qq": {"admin_id": 1001, "allowed_users": [1001]},
           "bot": {"name": "知夏", "memory_top_k": 6},
           "memory": {"top_k": 6, "budget_tokens": 320, "fallback_top": 2},
           "humanize": {}, "style": {"enabled": False}}
    configure(cfg["memory"])
    api = FakeAPI()
    eng = Engine(cfg, store, FakeLLM(), api, {"name": "知夏", "age": 22, "identity": "x",
                                              "speech": [], "taboos": []},
                 Growth(cfg, store, FakeLLM(), {"name": "知夏"}))

    def send(text):
        api.sent.clear()
        eng.handle({"user_id": 1001,
                    "message": [{"type": "text", "data": {"text": text}}]})
        return api.sent[-1] if api.sent else ""

    print("1)", send("#记住 我周三要交论文"))
    print("2)", send("#记忆")[:80].replace("\n", " | "))
    mid = store.conn().execute(
        "SELECT id FROM memories WHERE content LIKE '%论文%'").fetchone()["id"]
    print("3)", send(f"#忘掉 {mid}"))
    print("   archived =", store.get_memory(mid)["archived"])
    print("4)", send("#遗忘")[:120].replace("\n", " | "))
    print("5)", send(f"#恢复 {mid}"))
    print("   archived =", store.get_memory(mid)["archived"])
    print("6)", send(f"#纠正 {mid} 我周四要交论文"))
    old = store.get_memory(mid)
    new_id = old["superseded_by"]
    print("   superseded_by =", new_id, "| new =", store.get_memory(new_id)["content"])
    print("7) 召回测试:", [m["content"] for m in
                          store.search_memories("论文", dry_run=True)])
    print("8) 溯源:", store.get_memory(new_id)["source"])
    store.close()
    tmp.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
