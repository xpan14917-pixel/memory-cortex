# -*- coding: utf-8 -*-
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from memory_brain import forgetting

DAY = 86400


def mem(kind="fact", weight=1.0, hits=0, ts=0, last_used=0, stability=None, **kw):
    m = {"kind": kind, "weight": weight, "hits": hits, "ts": ts,
         "last_used": last_used, "content": "x", "keywords": "x"}
    if stability is not None:
        m["stability"] = stability
    m.update(kw)
    return m


class TestStability(unittest.TestCase):
    def test_hits_extend_stability(self):
        self.assertGreater(forgetting.stability("fact", 1.0, 3),
                           forgetting.stability("fact", 1.0, 0))

    def test_weight_extends_stability(self):
        self.assertGreater(forgetting.stability("fact", 2.0, 0),
                           forgetting.stability("fact", 1.0, 0))

    def test_promise_outlives_event(self):
        self.assertGreater(forgetting.stability("promise", 1.0, 0),
                           forgetting.stability("event", 1.0, 0))

    def test_capped(self):
        self.assertLessEqual(forgetting.stability("date", 3.0, 99), forgetting.MAX_S)


class TestRetention(unittest.TestCase):
    def test_fresh_is_one(self):
        now = 1_000_000
        self.assertAlmostEqual(forgetting.retention(mem(ts=now), now), 1.0, places=6)

    def test_decays_over_time(self):
        now = 1_000_000
        m = mem(ts=now - 10 * DAY, stability=10)
        self.assertLess(forgetting.retention(m, now), 0.5)
        self.assertGreater(forgetting.retention(m, now), 0.2)

    def test_reinforce_slows_decay(self):
        now = 1_000_000
        m = mem(ts=now - 30 * DAY, stability=10)
        before = forgetting.retention(m, now)
        m2 = dict(m, stability=forgetting.reinforced(m))
        self.assertGreater(forgetting.retention(m2, now), before)


class TestArchive(unittest.TestCase):
    def test_promise_never_archived(self):
        now = 1_000_000
        m = mem(kind="promise", ts=now - 400 * DAY, stability=1)
        self.assertFalse(forgetting.should_archive(m, now))

    def test_old_forgotten_is_archived(self):
        now = 1_000_000
        m = mem(kind="event", ts=now - 200 * DAY, stability=5, hits=0)
        self.assertTrue(forgetting.should_archive(m, now))

    def test_recent_not_archived(self):
        now = 1_000_000
        m = mem(kind="event", ts=now - 10 * DAY, stability=1, hits=0)
        self.assertFalse(forgetting.should_archive(m, now))

    def test_recalled_not_archived(self):
        now = 1_000_000
        m = mem(kind="event", ts=now - 300 * DAY, stability=1, hits=2)
        self.assertFalse(forgetting.should_archive(m, now))


class TestTokens(unittest.TestCase):
    def test_estimate(self):
        self.assertGreaterEqual(forgetting.estimate_tokens("中文"), 1)
        self.assertEqual(forgetting.estimate_tokens(""), 1)


if __name__ == "__main__":
    unittest.main()
