"""可插拔的 embedding 接口。

默认关闭（`vector_enabled` 为 False），此时 `get_embedder()` 返回空实现，
召回行为与纯关键词版本完全一致。

三种 provider：

- `hash`   : 零依赖的字符二元组哈希向量。只用来跑通链路和做测试，语义能力有限。
- `ollama` : 本地 Ollama（`POST /api/embeddings`），需要用户自己装，Python 侧仍零依赖。
- `openai` : 任何 OpenAI 兼容的 `/embeddings` 接口（会出网，需显式开启）。
"""
import hashlib
import json
import math
import urllib.request

from . import config

_DIM = 256


class Embedder:
    name = "none"
    enabled = False

    def embed(self, texts):
        return None


class NullEmbedder(Embedder):
    pass


class HashEmbedder(Embedder):
    """字符二元组 + blake2b 哈希到固定维度，再 L2 归一化。

    纯标准库、确定性、无网络。它捕捉的是"字面相近"，不是真正的语义，
    只适合演示链路和单元测试。
    """

    name = "hash"
    enabled = True

    def __init__(self, dim=_DIM):
        self.dim = dim

    def _one(self, text):
        vec = [0.0] * self.dim
        text = (text or "").lower()
        grams = [text[i:i + 2] for i in range(max(1, len(text) - 1))]
        if not grams:
            return vec
        for g in grams:
            h = hashlib.blake2b(g.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(h[:4], "little") % self.dim
            sign = 1.0 if h[4] % 2 == 0 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed(self, texts):
        return [self._one(t) for t in texts]


class OllamaEmbedder(Embedder):
    name = "ollama"
    enabled = True

    def __init__(self, model=None, base_url=None):
        self.model = model or config.get("vector_model") or "nomic-embed-text"
        self.base_url = (base_url or config.get("vector_base_url")
                         or "http://127.0.0.1:11434").rstrip("/")

    def _one(self, text):
        body = json.dumps({"model": self.model, "prompt": text}).encode("utf-8")
        req = urllib.request.Request(self.base_url + "/api/embeddings", data=body,
                                     method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
        return [float(x) for x in (data.get("embedding") or [])]

    def embed(self, texts):
        out = []
        for t in texts:
            v = self._one(t)
            if not v:
                return None
            out.append(v)
        return out


class OpenAIEmbedder(Embedder):
    name = "openai"
    enabled = True

    def __init__(self, model=None, base_url=None, api_key=None):
        self.model = model or config.get("vector_model") or "text-embedding-3-small"
        self.base_url = (base_url or config.get("vector_base_url")
                         or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key or ""

    def embed(self, texts):
        if not self.api_key:
            return None
        body = json.dumps({"model": self.model, "input": list(texts)}).encode("utf-8")
        req = urllib.request.Request(self.base_url + "/embeddings", data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer " + self.api_key)
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
        return [[float(x) for x in item["embedding"]] for item in data.get("data", [])]


class CallableEmbedder(Embedder):
    """测试用：直接把一个函数包成 embedder。"""

    name = "callable"
    enabled = True

    def __init__(self, fn):
        self._fn = fn

    def embed(self, texts):
        return self._fn(list(texts))


_EMBEDDER = None


def build(cfg=None):
    """按配置构造 embedder；关闭时返回 NullEmbedder。"""
    cfg = cfg or {}
    if not cfg.get("vector_enabled") and not config.get("vector_enabled"):
        return NullEmbedder()
    provider = (cfg.get("vector_provider") or config.get("vector_provider") or "hash").lower()
    if provider == "hash":
        return HashEmbedder(int(cfg.get("vector_dim") or config.get("vector_dim") or _DIM))
    if provider == "ollama":
        return OllamaEmbedder(cfg.get("vector_model"), cfg.get("vector_base_url"))
    if provider == "openai":
        import os
        key = cfg.get("vector_api_key") or os.environ.get(
            str(cfg.get("vector_api_key_env") or "OPENAI_API_KEY"), "")
        return OpenAIEmbedder(cfg.get("vector_model"), cfg.get("vector_base_url"), key)
    return NullEmbedder()


def set_embedder(embedder):
    global _EMBEDDER
    _EMBEDDER = embedder
    return _EMBEDDER


def get_embedder():
    global _EMBEDDER
    if _EMBEDDER is None:
        _EMBEDDER = build()
    return _EMBEDDER


def embed(texts):
    """把文本批量转成向量；未启用时返回 None。"""
    return get_embedder().embed(texts)


def cosine(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


def pack(vec):
    """float 列表 → BLOB（float32 小端）。"""
    import struct
    return struct.pack("<%df" % len(vec), *vec)


def unpack(blob):
    import struct
    if not blob:
        return None
    n = len(blob) // 4
    return list(struct.unpack("<%df" % n, blob[: n * 4]))
