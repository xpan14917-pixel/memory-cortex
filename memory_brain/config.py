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
    # ---- 向量召回（默认关闭，未配置时行为与纯关键词一致）----
    "vector_enabled": False,
    "vector_provider": "hash",     # hash / ollama / openai
    "vector_weight": 0.5,          # RRF 融合时向量通道的权重，0~1
    "rrf_k": 60,                   # RRF 平滑常数
    "vector_model": "",            # 例如 nomic-embed-text / text-embedding-3-small
    "vector_base_url": "",         # 例如 http://127.0.0.1:11434
    "vector_api_key_env": "OPENAI_API_KEY",
    "vector_dim": 256,             # hash provider 的维度
    "vector_min_sim": 0.3,         # 向量相似度下限，低于此值不参与融合
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
