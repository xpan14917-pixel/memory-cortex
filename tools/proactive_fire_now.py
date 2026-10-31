"""手动触发一次真实主动消息（走完整生成逻辑，真发送）。"""
import datetime
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot import config as cfgmod  # noqa: E402
from bot import persona as persona_mod  # noqa: E402
from bot import state as state_mod  # noqa: E402
from bot.llm import LLM  # noqa: E402
from bot.proactive import Proactive  # noqa: E402
from memory_brain.store import Store  # noqa: E402
from bot.transport import OneBotAPI  # noqa: E402


def main():
    cfg = cfgmod.load()
    admin = cfg["qq"]["admin_id"]
    if not admin:
        raise SystemExit("还没绑定主人")
    cfg["qq"]["admin_id"] = admin

    store = Store(ROOT / "data" / "bot.db")
    lc = cfg["llm"]
    llm = LLM(lc["base_url"], lc["api_key"], lc["model"])
    api = OneBotAPI(cfg["onebot"]["api_base"], cfg["onebot"]["token"])
    p = Proactive(cfg, store, llm, api, persona_mod.load(ROOT / "persona.json"))

    st = state_mod.load(store)
    trigger = sys.argv[1] if len(sys.argv) > 1 else "idle"
    p.fire(datetime.datetime.now(), st, trigger)
    print("已发送（trigger=%s）" % trigger)
    return 0


if __name__ == "__main__":
    sys.exit(main())
