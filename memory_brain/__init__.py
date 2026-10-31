"""Memory Cortex · 会遗忘的记忆引擎。

    from memory_brain import MemoryStore
    store = MemoryStore("data/bot.db")
    store.add_memory("fact", "用户喜欢喝冰美式", weight=1.2)
    picked = store.search_memories("我今天点了什么喝的")

核心概念：
- stability（稳定度 S，天）：这条记忆有多抗遗忘，随「被想起」变大
- retention（保持度 R）：exp(-Δt / S)，1 = 刚用过，0 = 已经淡忘
- region（分区）：routine / limbic / persona / neural / memory
"""
from . import brainmap, config, forgetting, retrieval
from .config import configure, reset
from .store import Store

MemoryStore = Store

__all__ = ["MemoryStore", "Store", "forgetting", "brainmap", "retrieval",
           "config", "configure", "reset"]
__version__ = "0.2.0"
