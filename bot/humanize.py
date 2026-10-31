"""拟人化输出：分条、打字延迟、连发节奏。"""
import random
import re
import time

from .log import get

log = get("humanize")


def split_bubbles(text, max_bubbles=3):
    """把一段回复切成 1-3 条，模拟真人连发。"""
    text = (text or "").strip()
    if not text:
        return []
    # 已显式分行的情况，按行切
    if "\n" in text:
        parts = [p.strip() for p in text.split("\n") if p.strip()]
    else:
        # 按句末标点切
        parts = [p.strip() for p in re.split(r"(?<=[。！？!?~～…])", text) if p.strip()]

    if len(parts) <= 1:
        # 太长的单条，在逗号处再切一刀
        if len(text) > 45:
            chunks = re.split(r"(?<=[，,])", text)
            parts = [c.strip() for c in chunks if c.strip()]
        if len(parts) <= 1:
            return [text]

    if len(parts) > max_bubbles:
        head = parts[: max_bubbles - 1]
        tail = "".join(parts[max_bubbles - 1 :])
        parts = head + [tail]
    return parts


def typing_seconds(text, cfg):
    per_char = cfg.get("per_char", 0.045)
    jitter = cfg.get("per_char_jitter", 0.045)
    base = cfg.get("min_delay", 0.6)
    return base + len(text) * random.uniform(per_char, per_char + jitter)


def send_bubbles(api, user_id, bubbles, cfg, store=None):
    """逐条发送并插入拟人延迟。返回实际发出的条数。"""
    if not bubbles:
        return 0
    sent = 0
    for i, b in enumerate(bubbles):
        delay = typing_seconds(b, cfg)
        if i == 0 and random.random() < float(cfg.get("long_delay_prob", 0)):
            delay += random.uniform(
                float(cfg.get("long_delay_min", 20)),
                float(cfg.get("long_delay_max", 60)),
            )
        if i > 0:
            delay += random.uniform(
                cfg.get("between_min", 0.7), cfg.get("between_max", 1.9)
            )
        log.info("typing %.1fs -> %s", delay, b)
        time.sleep(delay)
        api.send_private(user_id, [{"type": "text", "data": {"text": b}}])
        if store:
            store.add_message("bot", b)
        sent += 1
    return sent
