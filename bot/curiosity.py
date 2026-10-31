"""自主提问：她会真的好奇，而不是关心式反问。"""
import time

from . import state as state_mod
from .log import get

log = get("curiosity")


def count_today(store, day_start_ts):
    return store.count_thoughts_today(day_start_ts, kind="疑问")


def can_ask(cfg, store, day_start_ts):
    cc = cfg.get("curiosity", {})
    if not cc.get("enabled", True):
        return False
    if count_today(store, day_start_ts) >= int(cc.get("max_per_day", 3)):
        return False
    last = store.recent_thoughts(20, days=1)
    last_q = next((t for t in last if t["kind"] == "疑问"), None)
    if last_q and time.time() - last_q["ts"] < int(cc.get("min_gap_minutes", 180)) * 60:
        return False
    return True


def ask(llm, store, persona, st):
    """生成一个真正好奇的问题，存成「疑问」类想法。"""
    if not getattr(llm, "api_key", ""):
        return None
    profile = store.profile_dict()
    recent = store.recent_messages(8)
    mem = "\n".join("- " + m["content"] for m in store.recent_thoughts(5)) or "（无）"
    prof = "\n".join(f"- {k}：{v}" for k, v in list(profile.items())[:8]) or "（无）"
    hist = "\n".join(
        f"{'TA' if m['role'] == 'user' else '我'}：{m['content']}" for m in recent[-8:]
    ) or "（还没聊过）"
    system = (
        f"你是「{persona['name']}」。你想问 TA 一个你**真正好奇**的问题。\n\n"
        "【要求】\n"
        "1. 必须从你们聊过的具体内容出发，别凭空问。\n"
        "2. 问 TA 的想法、选择、看法、为什么——不要问吃饭睡觉、不要「在吗」。\n"
        "3. 不要是非题；要是那种 TA 得想一下才能回答的问题。\n"
        "4. 15-40 字，一条，直接是问题本身，不要写「我想问你」。\n"
        "5. 语气自然，像聊天时突然想到。\n"
        '只输出 JSON：{"question": "..."}'
    )
    user = (
        f"当前状态：{state_mod.describe(st)}\n\n"
        f"你最近的想法：\n{mem}\n\n你知道的 TA：\n{prof}\n\n最近对话：\n{hist}"
    )
    try:
        data = llm.chat_json(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.9, max_tokens=120,
        )
    except Exception:  # noqa: BLE001
        log.warning("提问生成失败", exc_info=True)
        return None
    q = str(data.get("question") or "").strip()
    if not q or len(q) > 60:
        return None
    tid = store.add_thought("疑问", q, 1.2)
    log.info("新提问：%s", q)
    return {"id": tid, "kind": "疑问", "content": q}
