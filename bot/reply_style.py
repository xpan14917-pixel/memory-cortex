"""回复风格分布：长度、条数、语气词。

真人不会每轮都回 2-3 条 15 字的整句。这里在生成前摇一个风格，
让模型按风格回答，生成后再做一次硬约束。
"""
import random


def pick(cfg):
    sc = cfg.get("style", {})
    if not sc.get("enabled", True):
        return {"name": "normal", "max_bubbles": 3}
    r = random.random()
    terse = float(sc.get("terse_prob", 0.30))
    multi = float(sc.get("multi_prob", 0.20))
    if r < terse:
        return {"name": "terse", "max_bubbles": 1}
    if r < terse + multi:
        return {"name": "multi", "max_bubbles": 3}
    return {"name": "normal", "max_bubbles": 2}


def prompt(style):
    if style["name"] == "terse":
        return ("【这轮的语气】你现在没什么力气展开，只回一句很短的话（8 个字以内），"
                "像随口应一声；不要解释，不要反问。")
    if style["name"] == "multi":
        return ("【这轮的语气】可以多说两句，2-3 条短句；可以说自己的感受，"
                "最多问一个问题。")
    return ("【这轮的语气】1-2 条，每条不超过 20 字；大多数时候直接回应，"
            "不要为了接话而反问。")


def apply(bubbles, style, cfg):
    """硬约束：条数上限 + 概率去掉句尾波浪号。"""
    out = list(bubbles)[: style["max_bubbles"]]
    strip_p = float(cfg.get("style", {}).get("tilde_strip_prob", 0.5))
    cleaned = []
    for b in out:
        if b.endswith(("~", "～")) and random.random() < strip_p:
            b = b.rstrip("~～ ")
        b = b.strip()
        if b:
            cleaned.append(b)
    return cleaned
