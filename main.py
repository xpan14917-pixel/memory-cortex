"""qq-soul 入口：装配存储、LLM、对话引擎、主动调度、事件服务。"""
import argparse
import os
import pathlib
import sys
import threading
import time

# 便携版 Python 的 ._pth 不会自动加入脚本目录
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot import config as cfgmod
from bot import persona as persona_mod
from bot.engine import Engine
from bot.growth import Growth
from bot.inner_life import InnerLife
from bot.llm import LLM
from bot.log import get
from bot.proactive import Proactive
from memory_brain import configure as configure_memory
from memory_brain.store import Store
from bot.transport import EventServer, OneBotAPI, SerialWorker

ROOT = pathlib.Path(__file__).resolve().parent
log = get("main")


class App:
    def __init__(self, cfg, config_path=None):
        self.cfg = cfg
        self.config_path = config_path
        self.persona = persona_mod.load(ROOT / "persona.json")
        configure_memory(cfg.get("memory") or {})
        db_path = cfg.get("paths", {}).get("db") or (ROOT / "data" / "bot.db")
        self.store = Store(db_path)

        lc = cfg["llm"]
        self.llm = LLM(
            lc["base_url"],
            lc.get("api_key", ""),
            lc["model"],
            timeout=lc.get("timeout", 60),
            temperature=lc.get("temperature", 0.95),
            max_tokens=lc.get("max_tokens", 400),
        )

        ob = cfg["onebot"]
        self.api = OneBotAPI(ob["api_base"], ob.get("token", ""))
        self.growth = Growth(cfg, self.store, self.llm, self.persona)
        self.inner = InnerLife(cfg, self.store, self.llm, self.persona)
        self.engine = Engine(
            cfg, self.store, self.llm, self.api, self.persona, self.growth,
            config_path=config_path, inner_life=self.inner,
        )
        self.worker = SerialWorker(self.engine.handle)
        self.server = EventServer(
            ob["listen_host"], ob["listen_port"], ob["path"], self.on_event
        )
        self.proactive = Proactive(
            cfg, self.store, self.llm, self.api, self.persona, inner=self.inner
        )

    def on_event(self, ev):
        post = ev.get("post_type")
        if post == "message":
            if ev.get("message_type") == "private":
                self.worker.submit(ev)
        elif post == "notice":
            log.info("notice %s user=%s", ev.get("notice_type"), ev.get("user_id"))
        elif post == "request":
            log.info("request %s user=%s", ev.get("request_type"), ev.get("user_id"))
        elif post == "meta_event" and ev.get("meta_event_type") == "lifecycle":
            log.info("lifecycle %s", ev.get("sub_type"))

    def start(self):
        self.server.start()
        info = self.api.get_login_info()
        if info.get("status") == "ok" and info.get("data"):
            d = info["data"]
            log.info("OneBot 已连接：QQ=%s 昵称=%s", d.get("user_id"), d.get("nickname"))
        else:
            log.warning("OneBot 未连通（NapCat 未启动或 OneBot 配置未生效）")
        if not self.cfg["llm"].get("api_key"):
            log.warning("未配置 llm.api_key，聊天会失败")
        self.proactive.start()
        self.inner.start()
        threading.Thread(target=self._diary_loop, daemon=True).start()
        threading.Thread(target=self._recover_pending, daemon=True).start()

    def _recover_pending(self):
        """重启/崩溃后，如果最后一条是用户消息没人回，补答一次。"""
        time.sleep(6)
        try:
            pending = self.store.unanswered_user(max_age=900)
            if not pending:
                return
            log.info("发现未回复的消息，补答：%s", pending["content"][:40])
            self.engine.handle_recovery(pending["content"])
        except Exception:  # noqa: BLE001
            log.exception("补答失败")

    def _diary_loop(self):
        while True:
            time.sleep(600)
            try:
                self.growth.maybe_write_diary()
            except Exception:  # noqa: BLE001
                log.exception("日记循环异常")

    def stop(self):
        self.server.stop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    cfg = cfgmod.load(args.config)
    app = App(cfg, config_path=args.config)
    app.start()
    log.info("qq-soul 已启动，等待消息…")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("bye")
        app.stop()


if __name__ == "__main__":
    main()
