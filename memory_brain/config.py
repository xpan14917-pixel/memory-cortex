"""运行时可调参数。

默认值与 `config.json` 的 `memory` 段一致；`memory_brain.configure({...})` 可在启动时覆盖，
也可以在测试里临时改。所有函数都实时读这里，所以改完立即生效，不需要重启进程。
"""
import copy

DEFAULTS = {
    # 各类记忆的初始稳定度（天）
    "s0": {
        "promise": 120.0,
        "date": 400.0,
        "preference": 45.0,
        "fact": 30.0,
        "event": 10.0,
        "default": 20.0,
    },
    "min_stability": 0.5,
    "max_stability": 365.0,
    # 复习一次，稳定度乘 (1 + review_boost)
    "review_boost": 0.25,
    # score = 相关度 × R^gamma × weight
    "gamma": 0.9,
    # 低于这个 R 且非钉住类型 → 不召回
    "min_retention": 0.06,
    # 归档阈值
    "archive_min_retention": 0.05,
    "archive_min_days": 90,
    # 永不归档的类型 / 权重
    "pinned_kinds": ["promise", "date"],
    "pinned_weight": 1.2,
    # 没命中关键词时，兜底塞几条高权重记忆（0 = 关闭）
    "fallback_top": 2,
    # 召回时合并近似重复（内容 Jaccard ≥ 该值只留分数最高的）
    "dedupe_ratio": 0.6,
}

_state = copy.deepcopy(DEFAULTS)


def configure(params=None):
    """覆盖默认值；返回当前生效的完整配置。"""
    if params:
        for k, v in params.items():
            if k in _state and v is not None:
                if k == "s0" and isinstance(v, dict):
                    _state["s0"].update(v)
                else:
                    _state[k] = v
    return copy.deepcopy(_state)


def reset():
    global _state
    _state = copy.deepcopy(DEFAULTS)
    return copy.deepcopy(_state)


def get(key, default=None):
    return _state.get(key, default)


def s0_for(kind):
    return _state["s0"].get((kind or "").strip(), _state["s0"]["default"])
