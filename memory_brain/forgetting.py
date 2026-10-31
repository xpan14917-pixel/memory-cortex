"""遗忘曲线：稳定度 S、保持度 R、复习强化。

模型（艾宾浩斯 + 间隔重复）：
    S = S0(kind) × (1 + 0.5×hits) × weight^1.2      # 天
    R = exp(-Δt / S)                                  # Δt 为距上次被用的天数
    score = 相关度 × R^γ × weight

S0、复习增幅、归档阈值都可以用 memory_brain.configure() 覆盖。
约定 / 日子两类几乎不遗忘，且不会被归档。
"""
import math
import time

from . import config

# 兼容旧代码 / 测试的常量（实际取值走 config）
S0 = {
    "promise": 120.0,
    "date": 400.0,
    "preference": 45.0,
    "fact": 30.0,
    "event": 10.0,
}
DEFAULT_S0 = 20.0
MIN_S = 0.5
MAX_S = 365.0
MAX_DAYS = 3650.0

PINNED_KINDS = ("promise", "date")
PINNED_WEIGHT = 1.2


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def stability(kind, weight=1.0, hits=0, s0=None):
    """这条记忆有多"抗遗忘"，单位天。"""
    base = float(s0) if s0 else config.s0_for(kind)
    w = max(0.3, min(3.0, _f(weight, 1.0)))
    h = max(0, int(_f(hits, 0)))
    cap = _f(config.get("max_stability"), MAX_S)
    floor = _f(config.get("min_stability"), MIN_S)
    s = base * (1.0 + 0.5 * h) * (w ** 1.2)
    return max(floor, min(cap, s))


def days_since(ts, now=None):
    now = time.time() if now is None else now
    if not ts:
        return 0.0
    return max(0.0, min(MAX_DAYS, (now - _f(ts)) / 86400.0))


def retention(mem, now=None):
    """当前还记得多少，1.0 = 刚用过，0 = 完全淡忘。"""
    now = time.time() if now is None else now
    s = _f((mem or {}).get("stability") or 0)
    if s <= 0:
        s = stability(mem.get("kind"), mem.get("weight"), mem.get("hits"))
    touched = mem.get("last_used") or mem.get("ts")
    return math.exp(-days_since(touched, now) / max(MIN_S, s))


def recall_score(mem, relevance, now=None, gamma=None):
    """召回排序分：既要相关，也要还记得。"""
    r = retention(mem, now)
    rel = max(0.0, _f(relevance))
    w = max(0.2, _f(mem.get("weight"), 1.0))
    g = _f(config.get("gamma"), 0.9) if gamma is None else _f(gamma, 0.9)
    return rel * (r ** g) * w, r


def reinforced(mem, boost=None):
    """被想起来一次，曲线的斜率变缓。"""
    s = _f((mem or {}).get("stability") or 0)
    if s <= 0:
        s = stability(mem.get("kind"), mem.get("weight"), mem.get("hits"))
    b = _f(config.get("review_boost"), 0.25) if boost is None else _f(boost, 0.25)
    cap = _f(config.get("max_stability"), MAX_S)
    return min(cap, s * (1.0 + max(0.0, b)))


def is_pinned(mem):
    """这类记忆即使很久没提也不该归档。"""
    kinds = config.get("pinned_kinds") or PINNED_KINDS
    if (mem.get("kind") or "").strip() in kinds:
        return True
    return _f(mem.get("weight"), 1.0) >= _f(config.get("pinned_weight"), PINNED_WEIGHT)


def should_archive(mem, now=None, min_retention=None, min_days=None):
    """该不该归档。

    判定看「多久没被用过」而不是「有没有被用过」：
    hits 只负责把稳定度变大，不能当成免死金牌 ——
    否则一条两年前偶然被想起过的记忆会永远归档不掉。
    """
    if is_pinned(mem):
        return False
    md = _f(config.get("archive_min_days"), 90) if min_days is None else _f(min_days, 90)
    touched = mem.get("last_used") or mem.get("ts")
    if days_since(touched, now) < md:
        return False
    mr = (_f(config.get("archive_min_retention"), 0.05)
          if min_retention is None else _f(min_retention, 0.05))
    return retention(mem, now) < mr


def estimate_tokens(text):
    """粗估 token：中文约 1 token / 1.6 字，英文/数字约 1 token / 4 字符。"""
    text = text or ""
    cjk = 0
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff" or "\u3000" <= ch <= "\u303f":
            cjk += 1
    other = len(text) - cjk
    return max(1, int(round(cjk / 1.6 + other / 4.0)))


def describe(mem, now=None):
    r = retention(mem, now)
    s = _f(mem.get("stability") or 0) or stability(
        mem.get("kind"), mem.get("weight"), mem.get("hits")
    )
    flags = []
    if mem.get("archived"):
        flags.append("归档")
    if mem.get("superseded_by"):
        flags.append("已被更正")
    suffix = (" " + "/".join(flags)) if flags else ""
    return f"R={r:.2f} S={s:.0f}d hits={int(_f(mem.get('hits')))}" + suffix
