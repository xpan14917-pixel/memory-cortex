# -*- coding: utf-8 -*-
"""老库升级：没有 stability/archived/region 的库能被自动补齐。"""
import pathlib
import sqlite3
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from memory_brain.store import Store

OLD_SCHEMA = """
CREATE TABLE memories(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  kind TEXT NOT NULL,
  content TEXT NOT NULL,
  keywords TEXT NOT NULL,
  weight REAL DEFAULT 1.0,
  hits INTEGER DEFAULT 0,
  last_used REAL DEFAULT 0
);
"""


class MigrationCase(unittest.TestCase):
    def setUp(self):
        self.store = None
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "old.db"
        con = sqlite3.connect(self.db)
        con.executescript(OLD_SCHEMA)
        con.execute(
            "INSERT INTO memories(ts, kind, content, keywords, weight, hits)"
            " VALUES(?,?,?,?,?,?)",
            (time.time() - 86400, "preference", "用户喜欢冰美式", "冰美式 喜欢", 1.2, 3),
        )
        con.commit()
        con.close()

    def tearDown(self):
        if self.store is not None:
            self.store.close()
        self.tmp.cleanup()

    def test_adds_columns_and_backfills(self):
        store = self.store = Store(self.db)
        cols = {r["name"] for r in store.conn().execute("PRAGMA table_info(memories)")}
        for c in ("stability", "archived", "last_review", "region"):
            self.assertIn(c, cols)

        row = store.conn().execute("SELECT * FROM memories").fetchone()
        self.assertIsNotNone(row["stability"])
        self.assertGreater(row["stability"], 0)
        self.assertIn(row["region"], ("routine", "limbic", "persona", "neural", "memory"))
        self.assertEqual(row["archived"], 0)

    def test_idempotent(self):
        Store(self.db).close()
        store = self.store = Store(self.db)
        n = store.conn().execute("SELECT COUNT(*) c FROM memories").fetchone()["c"]
        self.assertEqual(n, 1)


if __name__ == "__main__":
    unittest.main()
