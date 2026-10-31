"""重复检测：记录「今天已经问过什么」，并判断新回复是否在炒冷饭。"""
import datetime
import re

from memory_brain.text import tokenize

TOPICS = [
    ("吃饭", r"吃|饭|饿|外卖|宵夜|零食"),
    ("睡觉", r"睡|困|熬夜|几点睡|失眠|起床"),
    ("累", r"累|加班|辛苦|撑不住|疲惫"),
    ("心情", r"心情|难过|不开心|烦|emo|委屈"),
    ("工作", r"上班|工作|老板|同事|公司"),
    ("回家", r"回家|到家|路上"),
]


def today():
    return datetime.date.today().isoformat()


def topic_of(text):
    return [name for name, pat in TOPICS if re.search(pat, text or "")]


def similarity(a, b):
    ta, tb = tokenize(a), tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def is_question(text):
    return bool(re.search(r"[?？]|吗|呢|没|嘛|咋|怎么|几点", text or ""))


def asked_today(store):
    data = store.get_state("asked_topics") or {}
    return set(data.get("topics") or []) if data.get("date") == today() else set()


def update_topics(store, bubbles):
    """记录这一轮里被当作「关心」问过的话题。"""
    data = store.get_state("asked_topics") or {}
    topics = set(data.get("topics") or []) if data.get("date") == today() else set()
    for b in bubbles:
        if is_question(b):
            topics.update(topic_of(b))
    store.set_state("asked_topics", {"date": today(), "topics": sorted(topics)})


def topics_hint(store):
    topics = sorted(asked_today(store))
    if not topics:
        return ""
    return ("【今天你已经问过】" + "、".join(topics) +
            "。别再重复问同样的事；换个话题，或者直接说你自己这边的。")


def max_similarity(bubbles, recent_bot_msgs):
    if not recent_bot_msgs:
        return 0.0
    return max(
        (similarity(b, old) for b in bubbles for old in recent_bot_msgs),
        default=0.0,
    )
