# -*- coding: utf-8 -*-
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from memory_brain import brainmap


class TestClassify(unittest.TestCase):
    def test_promise_goes_to_memory_region(self):
        self.assertEqual(brainmap.classify("promise", "答应陪用户过生日"), "memory")

    def test_life_event_goes_to_routine(self):
        self.assertEqual(brainmap.classify("event", "用户今天加班到很晚"), "routine")

    def test_emotion_goes_to_limbic(self):
        self.assertEqual(brainmap.classify("event", "用户今天很难过，哭了"), "limbic")

    def test_identity_goes_to_persona(self):
        self.assertEqual(brainmap.classify("preference", "用户希望TA拥有自己的意识"), "persona")

    def test_preference_defaults_to_neural(self):
        self.assertEqual(brainmap.classify("preference", "用户喜欢冰美式"), "neural")

    def test_unknown_falls_back(self):
        self.assertIn(brainmap.classify("fact", "zzz"), brainmap.REGION_LABEL)


class TestQueryRegions(unittest.TestCase):
    def test_detect_work(self):
        self.assertIn("routine", brainmap.query_regions("我今天加班很累"))

    def test_detect_promise(self):
        self.assertIn("memory", brainmap.query_regions("你还记得我们约好什么吗"))

    def test_detect_relation(self):
        self.assertIn("persona", brainmap.query_regions("你会不会离开我"))

    def test_empty(self):
        self.assertEqual(brainmap.query_regions("在吗"), set())


class TestSummary(unittest.TestCase):
    def test_summary_format(self):
        s = brainmap.summary({"routine": 9, "limbic": 7, "neural": 3}, archived=2, total=19)
        self.assertIn("生活 9", s)
        self.assertIn("共 19 条", s)
        self.assertIn("2 条已淡忘", s)

    def test_summary_empty(self):
        self.assertEqual(brainmap.summary({}), "")


if __name__ == "__main__":
    unittest.main()
