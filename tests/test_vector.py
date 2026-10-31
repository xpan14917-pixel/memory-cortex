# -*- coding: utf-8 -*-
"""向量召回：关闭时零影响、开启后 RRF 融合、provider 缺失时优雅降级。"""
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from memory_brain import config, retrieval, vector
from memory_brain.store import Store

# 一个"迷你语义空间"：同义/近义文本映射到相近方向
VOCAB = {
    "猫": [1.0, 0.0, 0.0],
    "宠物": [0.95, 0.05, 0.0],
    "豆豆": [0.9, 0.1, 0.0],
    "咖啡": [0.0, 1.0, 0.0],
    "冰美式": [0.0, 0.95, 0.05],
    "加班": [0.0, 0.0, 1.0],
    "很累": [0.05, 0.0, 0.95],
}


def fake_embed(texts):
    out = []
    for t in texts:
        acc = [0.0, 0.0, 0.0]
        hit = False
        for k, v in VOCAB.items():
            if k in t:
                hit = True
                for i in range(3):
                    acc[i] += v[i]
        if not hit:
            acc = [0.0, 0.0, 0.0]
        out.append(acc)
    return out


class NullEmb(vector.Embedder):
    enabled = False


class VectorCase(unittest.TestCase):
    def setUp(self):
        config.reset()
        config.configure({"fallback_top": 0})
        vector.set_embedder(NullEmb())
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(pathlib.Path(self.tmp.name) / "t.db")
        self.store.add_memory("fact", "用户养了一只橘猫叫豆豆", weight=1.0)
        self.store.add_memory("preference", "用户喜欢冰美式", weight=1.0)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()
        vector.set_embedder(NullEmb())
        config.reset()

    # ---- 关闭时零影响 ----
    def test_disabled_means_no_embedding_written(self):
        row = self.store.conn().execute(
            "SELECT embedding FROM memories LIMIT 1").fetchone()
        self.assertIsNone(row["embedding"])

    def test_disabled_paraphrase_not_recalled(self):
        got = self.store.search_memories("我的宠物最近怎么样", dry_run=True)
        self.assertEqual(got, [])

    # ---- 开启后 ----
    def test_enabled_writes_embedding(self):
        vector.set_embedder(vector.CallableEmbedder(fake_embed))
        mid = self.store.add_memory("fact", "用户家的猫叫豆豆", weight=1.0)
        row = self.store.conn().execute(
            "SELECT embedding, embed_model FROM memories WHERE id=?", (mid,)).fetchone()
        self.assertIsNotNone(row["embedding"])
        self.assertEqual(row["embed_model"], "callable")

    def test_paraphrase_recalled_with_vector(self):
        vector.set_embedder(vector.CallableEmbedder(fake_embed))
        self.store.backfill_embeddings()
        got = self.store.search_memories("我的宠物最近怎么样", dry_run=True)
        self.assertTrue(got, "开启向量后应能召回近义内容")
        self.assertIn("猫", got[0]["content"])

    def test_vector_off_after_backfill_still_keyword(self):
        vector.set_embedder(vector.CallableEmbedder(fake_embed))
        self.store.backfill_embeddings()
        vector.set_embedder(NullEmb())
        got = self.store.search_memories("我的宠物最近怎么样", dry_run=True)
        self.assertEqual(got, [])

    # ---- 优雅降级 ----
    def test_embedder_returns_none_falls_back(self):
        class Broken(vector.Embedder):
            enabled = True

            def embed(self, texts):
                return None

        vector.set_embedder(Broken())
        got = self.store.search_memories("冰美式", dry_run=True)
        self.assertTrue(got, "provider 不可用时退回关键词")
        self.assertIn("冰美式", got[0]["content"])

    def test_embedder_raises_falls_back(self):
        class Boom(vector.Embedder):
            enabled = True

            def embed(self, texts):
                raise RuntimeError("offline")

        vector.set_embedder(Boom())
        got = self.store.search_memories("冰美式", dry_run=True)
        self.assertTrue(got)

    def test_rows_without_embedding_are_skipped_in_vector_channel(self):
        vector.set_embedder(vector.CallableEmbedder(fake_embed))
        # 不 backfill：老数据没有向量，只能走关键词
        got = self.store.search_memories("我的宠物最近怎么样", dry_run=True)
        self.assertEqual(got, [])

    # ---- RRF 行为 ----
    def test_rrf_ranks_by_fusion_not_raw_score(self):
        vector.set_embedder(vector.CallableEmbedder(fake_embed))
        self.store.backfill_embeddings()
        rows = self.store.conn().execute("SELECT * FROM memories").fetchall()
        rel = retrieval.hybrid_relevance(rows, "我的宠物", now=None)
        best = max(rel, key=rel.get)
        content = self.store.conn().execute(
            "SELECT content FROM memories WHERE id=?", (best,)).fetchone()["content"]
        self.assertIn("猫", content)

    def test_vector_weight_zero_equals_keyword(self):
        vector.set_embedder(vector.CallableEmbedder(fake_embed))
        self.store.backfill_embeddings()
        config.configure({"vector_weight": 0.0})
        got = self.store.search_memories("我的宠物", dry_run=True)
        self.assertEqual(got, [])

    def test_vector_weight_one_prefers_semantic(self):
        vector.set_embedder(vector.CallableEmbedder(fake_embed))
        self.store.backfill_embeddings()
        config.configure({"vector_weight": 1.0})
        got = self.store.search_memories("冰美式", dry_run=True)
        self.assertTrue(got)


class VectorMathCase(unittest.TestCase):
    def test_cosine_basics(self):
        self.assertAlmostEqual(vector.cosine([1, 0], [1, 0]), 1.0, places=6)
        self.assertAlmostEqual(vector.cosine([1, 0], [0, 1]), 0.0, places=6)
        self.assertEqual(vector.cosine([], [1]), 0.0)
        self.assertEqual(vector.cosine([0, 0], [1, 1]), 0.0)

    def test_pack_roundtrip(self):
        v = [0.5, -1.25, 3.0]
        self.assertEqual([round(x, 5) for x in vector.unpack(vector.pack(v))], v)

    def test_hash_embedder_is_deterministic_and_normalized(self):
        e = vector.HashEmbedder(64)
        a = e.embed(["你好世界"])[0]
        b = e.embed(["你好世界"])[0]
        self.assertEqual(a, b)
        norm = sum(x * x for x in a) ** 0.5
        self.assertAlmostEqual(norm, 1.0, places=5)
        self.assertNotEqual(a, e.embed(["完全不同"])[0])


if __name__ == "__main__":
    unittest.main()
