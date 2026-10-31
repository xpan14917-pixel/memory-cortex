# -*- coding: utf-8 -*-
"""生成一份合成的示例数据库 + 面板数据（不含任何真实对话）。

    python tools/make_demo_db.py
    → examples/demo.db
    → panel/js/data.demo.js
"""
import pathlib
import random
import sys
import time

HERE = pathlib.Path(__file__).resolve()
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))

from memory_brain import brainmap, forgetting      # noqa: E402
from memory_brain.store import Store                # noqa: E402
from memory_brain.text import tokenize             # noqa: E402

OUT_DB = REPO / "examples" / "demo.db"
OUT_JS = REPO / "panel" / "js" / "data.demo.js"

DAY = 86400

MEMORIES = [
    # (kind, content, weight, 多少天前写入, hits)
    ("fact", "用户在做毕业设计，选题是推荐系统", 1.2, 30, 3),
    ("fact", "用户养了一只橘猫叫豆豆", 1.0, 26, 2),
    ("fact", "用户住在杭州，每天通勤大概四十分钟", 0.8, 24, 1),
    ("fact", "用户在做一份后端实习，主要写 Python", 1.2, 20, 2),
    ("fact", "用户的生日是 6 月 18 日", 1.2, 45, 1),
    ("fact", "用户喝咖啡会心悸，所以只喝半杯", 0.8, 18, 0),
    ("preference", "用户喜欢冰美式，不加糖", 1.0, 22, 3),
    ("preference", "用户讨厌被叫全名，觉得像被点名", 1.2, 28, 2),
    ("preference", "用户喜欢深夜聊天，白天基本不回消息", 1.2, 21, 4),
    ("preference", "用户不喜欢被反复追问「在吗」", 1.0, 16, 2),
    ("preference", "用户对甜食没兴趣，更喜欢吃辣", 0.8, 14, 0),
    ("event", "用户上周加班到凌晨，第二天迟到了", 1.0, 9, 1),
    ("event", "用户昨天去看了牙医，补了两颗牙", 1.0, 3, 0),
    ("event", "用户说周末想去看一个摄影展", 0.9, 6, 0),
    ("event", "用户前天和室友因为打扫卫生吵了一架", 1.1, 5, 0),
    ("event", "用户今天面试了一家小公司，感觉一般", 1.2, 1, 0),
    ("promise", "答应陪用户过今年的生日", 1.4, 40, 2),
    ("promise", "说好下周一起看那部一直没看的电影", 1.2, 8, 1),
    ("promise", "用户让我每天提醒他喝水，我答应了", 1.0, 12, 3),
    ("date", "用户的实习答辩在 12 月 20 日", 1.3, 10, 0),
    ("date", "用户和室友的房租 3 月到期", 0.9, 25, 0),
]

MESSAGES = [
    ("user", "在干嘛呢"), ("bot", "刚醒，正对着窗外发呆呢~"),
    ("user", "我今天面试完有点丧"), ("bot", "面得不好吗，说说看呀"),
    ("user", "就感觉答得一般"), ("bot", "第一份工作嘛，答得一般也很正常"),
    ("bot", "你还记得上次加班到凌晨那次吗，那次你也是这么说的"),
]


def main():
    OUT_DB.parent.mkdir(parents=True, exist_ok=True)
    if OUT_DB.exists():
        OUT_DB.unlink()
    for ext in ("-wal", "-shm"):
        p = pathlib.Path(str(OUT_DB) + ext)
        if p.exists():
            p.unlink()

    store = Store(OUT_DB)
    now = time.time()
    rnd = random.Random(20261031)

    with store.conn() as c:
        for i, (kind, content, weight, days_ago, hits) in enumerate(MEMORIES):
            ts = now - days_ago * DAY
            # 让一部分记忆"很久没被用过"，面板上能看到淡忘
            last_used = ts + rnd.uniform(0, min(days_ago, 20)) * DAY if hits else 0
            stab = forgetting.stability(kind, weight, hits)
            kws = " ".join(sorted(tokenize(content))[:12])
            c.execute(
                "INSERT INTO memories(ts, kind, content, keywords, weight, hits, last_used,"
                " stability, archived, region) VALUES(?,?,?,?,?,?,?,?,0,?)",
                (ts, kind, content, kws,
                 weight, hits, last_used, stab, brainmap.classify(kind, content)),
            )
        for i, (role, text) in enumerate(MESSAGES):
            c.execute("INSERT INTO messages(ts, role, content) VALUES(?,?,?)",
                      (now - (len(MESSAGES) - i) * 300, role, text))
        for k, v, conf in [
            ("作息", "晚睡，凌晨一两点才睡", 0.9),
            ("日常状态", "实习 + 毕业设计，最近很忙", 0.8),
            ("喜好", "冰美式、吃辣、摄影", 0.7),
            ("雷点", "被叫全名、被反复追问在吗", 0.8),
        ]:
            c.execute("INSERT INTO profile(key, value, confidence, updated_at) VALUES(?,?,?,?)",
                      (k, v, conf, now))
        for k, v in [
            ("mood", '{"pleasure": 0.4, "arousal": 0.3, "dominance": 0.5}'),
            ("energy", "62"), ("intimacy", "48"),
            ("traits", '{"活泼": 55, "黏人": 60, "毒舌": 20, "好奇": 70, "温柔": 75}'),
        ]:
            c.execute("INSERT INTO state(k, v, updated_at) VALUES(?,?,?)", (k, v, now))
        c.execute(
            "INSERT INTO diary(date, mood, summary, highlights, next_day, created_at)"
            " VALUES(?,?,?,?,?,?)",
            (time.strftime("%Y-%m-%d", time.localtime(now - DAY)), "还行",
             "今天他面完试有点丧，我陪着说了会儿话。", "他说面试答得一般",
             "想问问他明天还要不要投别家", now - DAY),
        )
        c.commit()

    print("wrote", OUT_DB, "memories", len(MEMORIES), "messages", len(MESSAGES))

    from panel.tools.build_data import export
    data = export(OUT_DB, OUT_JS, persona_file=REPO / "persona.example.json")
    print("wrote", OUT_JS, "memories", len(data["memories"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
