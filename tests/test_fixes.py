# -*- coding: utf-8 -*-
"""整改清单 C 段的回归测试：归档、预算、候选池、token 估算、min_sim。"""
import pathlib
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from memory_brain import config, forgetting, retrieval, vector
from memory_brain.store import Store

DAY = 86400


class ArchiveCase(unittest.TestCase):
    def test_hits_no_longer_blocks_archive(self):
        now = time.time()
        m = {"kind": "event", "weight": 1.0, "hits": 5,
             "stability": 10, "ts": now - 500 * DAY, "last_used": now - 400 * DAY}
        self.assertTrue(forgetting.should_archive(m, now))

    def test_recent_use_blocks_archive(self):
        now = time.time()
        m = {"kind": "event", "weight": 1.0, "hits": 5,
             "stability": 10, "ts": now - 500 * DAY, "last_used": now - 5 * DAY}
        self.assertFalse(forgetting.should_archive(m, now))


class BudgetCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(pathlib.Path(self.tmp.name) / "t.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()
        config.reset()

    def test_first_item_is_truncated_not_overflowed(self):
        self.store.add_memory("event", "用户" + "很长的经历描述" * 60, weight=1.0)
        got = self.store.search_memories("很长", limit=3, budget_tokens=40)
        self.assertTrue(got)
        used = self.store.last_recall["tokens"]
        self.assertLessEqual(used, 40)
        self.assertLess(len(got[0]["content_shown"]), len(got[0]["content"]))

    def test_normal_budget_still_keeps_full_text(self):
        self.store.add_memory("fact", "用户住在杭州", weight=1.0)
        got = self.store.search_memories("杭州", budget_tokens=320)
        self.assertTrue(got)
        self.assertEqual(got[0]["tier"], "full")
        self.assertEqual(got[0]["content_shown"], got[0]["content"])


class CandidateCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(pathlib.Path(self.tmp.name) / "t.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()
        config.reset()

    def test_recent_low_weight_memory_enters_pool(self):
        """低权重但很新的记忆，应通过"最新池"进入候选。"""
        # 灌入一批高权重老记忆，把权重池挤满
        for i in range(30):
            self.store.add_memory("fact", "老旧高权重记忆 %d 咨询" % i, weight=3.0)
        self.store.conn().execute(
            "UPDATE memories SET ts=?", (time.time() - 300 * DAY,))
        self.store.conn().commit()
        # 一条低权重、刚刚写入、关键词精确命中的记忆
        mid = self.store.add_memory("fact", "齿轮箱异响", weight=0.6)
        rows = retrieval._candidates(self.store)
        self.assertIn(mid, [r["id"] for r in rows])

    def test_candidates_deduped(self):
        self.store.add_memory("fact", "用户住在杭州", weight=1.0)
        rows = retrieval._candidates(self.store)
        ids = [r["id"] for r in rows]
        self.assertEqual(len(ids), len(set(ids)))


class TokenEstimateCase(unittest.TestCase):
    def test_english_cheaper_than_chinese(self):
        zh = forgetting.estimate_tokens("这" * 40)
        en = forgetting.estimate_tokens("a" * 40)
        self.assertGreater(zh, en)
        self.assertGreaterEqual(zh, 24)
        self.assertLessEqual(en, 12)

    def test_empty(self):
        self.assertEqual(forgetting.estimate_tokens(""), 1)


class MinSimCase(unittest.TestCase):
    def setUp(self):
        config.reset()
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(pathlib.Path(self.tmp.name) / "t.db")
        self.store.add_memory("fact", "用户养了一只橘猫叫豆豆")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()
        vector.set_embedder(vector.NullEmbedder())
        config.reset()

    def test_low_similarity_is_filtered(self):
        # 两段完全不相关的文本：哈希向量相似度接近 0
        vector.set_embedder(vector.HashEmbedder(64))
        self.store.backfill_embeddings()
        config.configure({"vector_enabled": True, "vector_min_sim": 0.9,
                          "fallback_top": 0, "vector_weight": 1.0})
        got = self.store.search_memories("量子力学导论", dry_run=True)
        self.assertEqual(got, [])


if __name__ == "__main__":
    unittest.main()
