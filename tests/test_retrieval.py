# -*- coding: utf-8 -*-
import pathlib
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from memory_brain.store import Store

DAY = 86400


class RetrievalCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "t.db"
        self.store = Store(self.db)
        now = time.time()
        rows = [
            ("preference", "用户喜欢冰美式，不加糖", 1.0, now - 2 * DAY),
            ("preference", "用户喜欢深夜聊天", 1.0, now - 3 * DAY),
            ("event", "用户今天加班到很晚", 1.0, now - 1 * DAY),
            ("fact", "用户住在杭州", 1.0, now - 5 * DAY),
            ("promise", "答应陪用户过生日", 1.4, now - 120 * DAY),
            ("event", "用户很久以前说过一次旅行", 0.8, now - 400 * DAY),
        ]
        for kind, content, weight, ts in rows:
            cur = self.store.conn().execute(
                "INSERT INTO memories(ts, kind, content, keywords, weight, hits,"
                " stability, region) VALUES(?,?,?,?,?,0,?,?)",
                (ts, kind, content, content[:6], weight,
                 self.store.conn().execute(
                     "SELECT 1").fetchone() and _stab(kind, weight), _region(kind, content)),
            )
            if content.startswith("用户很久以前"):
                self.store.conn().execute(
                    "UPDATE memories SET archived=1 WHERE id=?", (cur.lastrowid,))
        self.store.conn().commit()

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_hits_keyword(self):
        got = self.store.search_memories("我今天加班", dry_run=True)
        self.assertTrue(got)
        self.assertIn("加班", got[0]["content"])

    def test_respects_limit(self):
        got = self.store.search_memories("用户", limit=2, dry_run=True)
        self.assertLessEqual(len(got), 2)

    def test_archived_excluded(self):
        got = self.store.search_memories("旅行", dry_run=True)
        self.assertFalse(any("旅行" in m["content"] for m in got))

    def test_reinforce_updates(self):
        got = self.store.search_memories("冰美式", dry_run=True)
        self.assertTrue(got)
        mid = got[0]["id"]
        before = self.store.conn().execute(
            "SELECT hits, stability FROM memories WHERE id=?", (mid,)).fetchone()
        self.store.search_memories("冰美式")
        after = self.store.conn().execute(
            "SELECT hits, stability FROM memories WHERE id=?", (mid,)).fetchone()
        self.assertEqual(after["hits"], before["hits"] + 1)
        self.assertGreater(after["stability"], before["stability"])

    def test_region_bonus_does_not_drop_results(self):
        base = self.store.search_memories("用户喜欢", limit=6, dry_run=True)
        boosted = self.store.search_memories("用户喜欢", limit=6, dry_run=True,
                                             regions={"neural"})
        self.assertGreaterEqual(len(boosted), min(len(base), 1))

    def test_budget_is_respected(self):
        got = self.store.search_memories("用户", limit=6, budget_tokens=20, dry_run=True)
        used = getattr(self.store, "last_recall", {}).get("tokens", 0)
        self.assertLessEqual(used, 20)
        self.assertLessEqual(len(got), 1)

    def test_region_counts(self):
        counts, archived = self.store.region_counts()
        self.assertEqual(sum(counts.values()), 6)
        self.assertEqual(archived, 1)


def _stab(kind, weight):
    from memory_brain import forgetting
    return forgetting.stability(kind, weight, 0)


def _region(kind, content):
    from memory_brain import brainmap
    return brainmap.classify(kind, content)


if __name__ == "__main__":
    unittest.main()
