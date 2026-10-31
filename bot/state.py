"""人格状态：心情、精力、亲密度、性格五维、关系阶段。

精力由**真实时间**决定（白天清醒、深夜困），不再由模型输出控制。
亲密度收益随当前值递减，且有每日上限，避免几天封顶。
"""
import datetime
import time

DEFAULTS = {
    "mood": {"pleasure": 0.0, "arousal": 0.5, "dominance": 0.5},
    "energy": 80.0,
    "intimacy": 12.0,
    "traits": {"活泼": 70, "黏人": 75, "毒舌": 85, "好奇": 60, "温柔": 35},
    "stage": "陌生",
}

STAGES = [(20, "陌生"), (45, "熟悉"), (70, "亲近"), (90, "依赖"), (101, "唯一")]

# 一天里的精力曲线：(小时, 精力)
ENERGY_CURVE = [
    (0, 20), (3, 15), (7, 45), (9, 75), (12, 82),
    (14, 62), (18, 78), (21, 62), (23, 38), (24, 24),
]

INTIMACY_DAILY_CAP = 3.0   # 每天最多涨 3 点
INTIMACY_DECAY_AFTER_DAYS = 3


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def stage_of(intimacy):
    for bound, name in STAGES:
        if intimacy < bound:
            return name
    return "唯一"


def energy_for_time(now=None):
    """按真实时钟插值出当前精力。"""
    now = now or datetime.datetime.now()
    h = now.hour + now.minute / 60.0
    for i in range(len(ENERGY_CURVE) - 1):
        h0, v0 = ENERGY_CURVE[i]
        h1, v1 = ENERGY_CURVE[i + 1]
        if h0 <= h <= h1:
            t = (h - h0) / (h1 - h0) if h1 > h0 else 0.0
            return round(v0 + (v1 - v0) * t, 1)
    return float(ENERGY_CURVE[-1][1])


def load(store):
    s = {}
    s["mood"] = store.get_state("mood", dict(DEFAULTS["mood"]))
    s["energy"] = store.get_float("energy", DEFAULTS["energy"])
    s["intimacy"] = store.get_float("intimacy", DEFAULTS["intimacy"])
    s["traits"] = store.get_state("traits", dict(DEFAULTS["traits"]))
    s["stage"] = stage_of(s["intimacy"])
    return s


def save(store, s):
    s["intimacy"] = clamp(s["intimacy"], 0, 100)
    s["energy"] = clamp(s["energy"], 0, 100)
    s["stage"] = stage_of(s["intimacy"])
    store.set_state("mood", s["mood"])
    store.set_state("energy", s["energy"])
    store.set_state("intimacy", s["intimacy"])
    store.set_state("traits", s["traits"])


def apply_delta(s, mood_delta=None, energy_delta=0.0, intimacy_delta=0.0,
                traits_delta=None):
    """心情与性格的增量。精力与亲密度分别由时间和 add_intimacy 管理。"""
    if mood_delta:
        for k in ("pleasure", "arousal", "dominance"):
            if k in mood_delta:
                try:
                    s["mood"][k] = clamp(s["mood"][k] + float(mood_delta[k]), -1, 1)
                except (TypeError, ValueError):
                    pass
    if traits_delta:
        for k, dv in traits_delta.items():
            if k in s["traits"]:
                try:
                    s["traits"][k] = clamp(s["traits"][k] + float(dv), 0, 100)
                except (TypeError, ValueError):
                    pass


def _today_gain(store):
    d = store.get_state("intimacy_gain") or {}
    if d.get("date") != datetime.date.today().isoformat():
        return 0.0
    return float(d.get("value") or 0)


def _set_today_gain(store, value):
    store.set_state(
        "intimacy_gain",
        {"date": datetime.date.today().isoformat(), "value": round(value, 2)},
    )


def intimacy_factor(v):
    """越靠近上限，涨得越慢。"""
    if v < 50:
        return 1.0
    if v < 75:
        return 0.45
    if v < 90:
        return 0.18
    return 0.04


def add_intimacy(store, s, delta):
    """带边际递减 + 每日上限的亲密度增长。"""
    try:
        delta = float(delta or 0)
    except (TypeError, ValueError):
        return 0.0
    if delta == 0:
        return 0.0
    gain = delta * intimacy_factor(s["intimacy"])
    if gain > 0:
        room = max(0.0, INTIMACY_DAILY_CAP - _today_gain(store))
        gain = min(gain, room)
        if gain <= 0:
            return 0.0
        _set_today_gain(store, _today_gain(store) + gain)
    s["intimacy"] = clamp(s["intimacy"] + gain, 0, 100)
    return gain


def mood_word(s):
    p = s["mood"]["pleasure"]
    a = s["mood"]["arousal"]
    e = s["energy"]
    if e < 25:
        base = "困得不行" if p > -0.3 else "又累又烦"
    elif e < 45:
        base = "有点没精神"
    elif p > 0.35 and a > 0.55:
        base = "挺兴奋"
    elif p > 0.35:
        base = "心情不错"
    elif p < -0.35 and a > 0.6:
        base = "有点烦躁"
    elif p < -0.35:
        base = "有点低落"
    else:
        base = "懒洋洋的"
    return base


def describe(s):
    return (
        f"心情：{mood_word(s)}（愉悦 {s['mood']['pleasure']:+.1f}，"
        f"唤醒 {s['mood']['arousal']:.1f}）；精力 {s['energy']:.0f}/100；"
        f"关系：{s['stage']}（亲密度 {s['intimacy']:.1f}/100）"
    )


def daily_upkeep(store, s):
    """每次对话前调用：精力跟随时钟，长期不聊则缓慢生疏。"""
    s["energy"] = energy_for_time()

    today = datetime.date.today().isoformat()
    if store.get_state("last_decay_date") != today:
        store.set_state("last_decay_date", today)
        last = store.last_user_message()
        if last and time.time() - last["ts"] > INTIMACY_DECAY_AFTER_DAYS * 86400:
            s["intimacy"] = clamp(s["intimacy"] - 1.5, 0, 100)
