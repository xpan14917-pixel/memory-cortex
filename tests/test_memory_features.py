# -*- coding: utf-8 -*-
"""兜底召回 / 去重 / 更正 / 恢复 / 参数覆盖。"""
import pathlib
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from memory_brain import config, forgetting
from memory_brain.store import Store

DAY = 86400


class FeatureCase(unittest.TestCase):
    def setUp(self):
        config.reset()
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(pathlib.Path(self.tmp.name) / "t.db")
        now = time.time()
        for kind, content, weight, days in [
            ("fact", "用户住在杭州", 1.2, 3),
            ("preference", "用户喜欢冰美式", 1.0, 5),
            ("event", "用户上周加班到凌晨", 1.0, 2),
        ]:
            self.store.add_memory(kind, content, weight=weight, source="msg:1")
            self.store.conn().execute(
                "UPDATE memories SET ts=? WHERE content=?", (now - days * DAY, content))
        self.store.conn().commit()

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()
        config.reset()

    # ---- 兜底召回 ----
    def test_fallback_when_no_keyword_hit(self):
        got = self.store.search_memories("在吗", dry_run=True)
        self.assertTrue(got, "没有关键词命中时应兜底")
        self.assertTrue(self.store.last_recall["fallback"])
        self.assertTrue(all(m["tier"] == "short" for m in got))

    def test_fallback_can_be_disabled(self):
        config.configure({"fallback_top": 0})
        got = self.store.search_memories("在吗", dry_run=True)
        self.assertEqual(got, [])

    def test_fallback_respects_top(self):
        config.configure({"fallback_top": 1})
        got = self.store.search_memories("zzz", dry_run=True)
        self.assertEqual(len(got), 1)

    # ---- 去重 ----
    def test_near_duplicates_are_merged_on_recall(self):
        self.store.add_memory("fact", "用户住在杭州西湖区", weight=1.0)
        got = self.store.search_memories("杭州", dry_run=True)
        contents = [m["content"] for m in got]
        self.assertEqual(len(contents), len(set(contents)))
        self.assertLessEqual(len(contents), 1 + 1)

    # ---- 更正 / 遗忘 / 恢复 ----
    def test_supersede_hides_old(self):
        old = self.store.conn().execute(
            "SELECT id FROM memories WHERE content LIKE '%杭州%'").fetchone()["id"]
        new_id = self.store.add_memory("fact", "用户搬到上海了", weight=1.2)
        self.store.supersede(old, new_id)
        got = self.store.search_memories("杭州", dry_run=True)
        self.assertNotIn(old, [m["id"] for m in got])
        self.assertEqual(self.store.get_memory(old)["superseded_by"], new_id)

    def test_restore_after_supersede(self):
        old = self.store.conn().execute(
            "SELECT id FROM memories WHERE content LIKE '%杭州%'").fetchone()["id"]
        self.store.supersede(old, 999)
        self.store.restore(old)
        got = self.store.search_memories("杭州", dry_run=True)
        self.assertIn(old, [m["id"] for m in got])

    def test_forget_and_restore(self):
        mid = self.store.conn().execute(
            "SELECT id FROM memories WHERE content LIKE '%冰美式%'").fetchone()["id"]
        self.store.forget(mid)
        got = self.store.search_memories("冰美式", dry_run=True)
        self.assertNotIn(mid, [m["id"] for m in got])
        self.store.restore(mid)
        got = self.store.search_memories("冰美式", dry_run=True)
        self.assertIn(mid, [m["id"] for m in got])

    def test_stats_counts_superseded(self):
        mid = self.store.conn().execute("SELECT id FROM memories LIMIT 1").fetchone()["id"]
        self.store.supersede(mid, 0)
        stats = self.store.memory_stats()
        self.assertEqual(stats["superseded"], 1)
        self.assertEqual(stats["active"], 2)

    # ---- 参数 / 溯源 ----
    def test_source_is_stored(self):
        mid = self.store.add_memory("fact", "用户养了一只猫", source="msg:42")
        self.assertEqual(self.store.get_memory(mid)["source"], "msg:42")

    def test_review_boost_override(self):
        mem = {"kind": "fact", "weight": 1.0, "hits": 0, "stability": 10.0}
        config.configure({"review_boost": 0.25})
        base = forgetting.reinforced(mem)
        config.configure({"review_boost": 1.0})
        self.assertGreater(forgetting.reinforced(mem), base)

    def test_s0_override(self):
        config.configure({"s0": {"fact": 99.0}})
        self.assertAlmostEqual(forgetting.stability("fact", 1.0, 0), 99.0, places=3)

    def test_gamma_override(self):
        mem = {"kind": "fact", "weight": 1.0, "hits": 1, "stability": 10.0,
               "last_used": time.time() - 5 * DAY}
        config.configure({"gamma": 0.2})
        s_low, _ = forgetting.recall_score(mem, 2.0)
        config.configure({"gamma": 2.0})
        s_high, _ = forgetting.recall_score(mem, 2.0)
        self.assertGreater(s_low, s_high)


if __name__ == "__main__":
    unittest.main()
