"""切换人格后的数据重置：清空对话、保留记忆与档案、重置关系状态。"""
import json
import pathlib
import sqlite3

ROOT = pathlib.Path(__file__).resolve().parent.parent
db = sqlite3.connect(ROOT / "data" / "bot.db")
c = db.cursor()

c.execute("DELETE FROM messages")
print("cleared messages")

c.execute("UPDATE state SET v=? WHERE k='intimacy'", (json.dumps(25.0),))
c.execute("UPDATE state SET v=? WHERE k='mood'",
          (json.dumps({"pleasure": 0.25, "arousal": 0.4, "dominance": 0.45}),))
c.execute("UPDATE state SET v=? WHERE k='traits'",
          (json.dumps({"活泼": 45, "黏人": 65, "毒舌": 15, "好奇": 60, "温柔": 88}),
           ))
c.execute("UPDATE state SET v=? WHERE k='energy'", (json.dumps(80.0),))
if c.rowcount == 0:
    c.execute("INSERT OR REPLACE INTO state(k, v, updated_at) VALUES('energy', ?, strftime('%s','now'))",
              (json.dumps(80.0),))

db.commit()
print("state reset: intimacy=25, traits=温柔学姐, mood=温和")
db.close()
