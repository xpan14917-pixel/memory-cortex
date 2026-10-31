# -*- coding: utf-8 -*-
"""遗忘曲线预演：在数据库副本上跑 90 天，不改真实数据。

用法：
    python tools/sim_forget.py            # 只做体检 + 召回对比
    python tools/sim_forget.py --sim 90   # 再模拟 90 天，看会归档哪些记忆
"""
import argparse
import pathlib
import random
import shutil
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from memory_brain import forgetting
from bot import persona          # noqa: E402
from memory_brain.store import Store
from memory_brain.text import tokenize                  # noqa: E402


def tok(s):
    return forgetting.estimate_tokens(s)


def old_recall(store, query, limit=6):
    """旧逻辑（没有遗忘曲线），只用来对比 token。"""
    q = tokenize(query)
    rows = store.conn().execute(
        "SELECT * FROM memories ORDER BY weight DESC, ts DESC LIMIT 300"
    ).fetchall()
    now = time.time()
    scored = []
    for r in rows:
        m = dict(r)
        kws = set((m["keywords"] or "").split())
        overlap = len(q & kws)
        substr = sum(1 for t in q if t in m["content"]) if not overlap else 0
        if overlap == 0 and substr == 0:
            continue
        recency = max(0.0, 1.0 - (now - m["ts"]) / (90 * 86400))
        score = overlap * 2.0 + substr * 0.3 + m["weight"] * 0.5 + recency
        if score > 0.4:
            scored.append((score, m))
    scored.sort(key=lambda x: x[0], reverse=True)
    picked = [m for _, m in scored[:limit]]
    for m in picked:
        m["tier"] = "full"
    return picked


def block_tokens(mems):
    return tok(persona._memory_lines(mems))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", type=int, default=0, help="模拟天数")
    args = ap.parse_args()

    src = ROOT / "data" / "bot.db"
    tmp = pathlib.Path(tempfile.gettempdir()) / ("sim_forget_%d.db" % int(time.time()))
    shutil.copy2(src, tmp)
    store = Store(tmp)

    print("=" * 62)
    print("数据库副本：", tmp)
    stats = store.memory_stats()
    print("记忆 %d 条｜归档 %d｜平均保持度 %.2f｜快淡忘(<0.3) %d"
          % (stats["total"], stats["archived"], stats["avg_retention"], stats["fading"]))

    print("\n-- 当前每条记忆的保持度 --")
    mems = store.all_memories(400)
    for m in sorted(mems, key=lambda x: forgetting.retention(x)):
        print("  #%-3d %-10s %-28s %s"
              % (m["id"], m["kind"], (m["content"] or "")[:26], forgetting.describe(m)))

    # ---- 召回对比：用真实用户消息当查询 ----
    rows = store.conn().execute(
        "SELECT content FROM messages WHERE role='user' ORDER BY id DESC LIMIT 40"
    ).fetchall()
    queries = []
    for r in rows:
        c = (r["content"] or "").strip()
        if 2 <= len(c) <= 40 and c not in queries:
            queries.append(c)
    queries = queries[:10]

    print("\n-- 召回对比（同一句用户消息） --")
    print("%-22s %-14s %-14s" % ("查询", "旧：条/字", "新：条/字(预算320)"))
    old_total = new_total = 0
    for q in queries:
        old = old_recall(store, q)
        new = store.search_memories(q, limit=6, budget_tokens=320, dry_run=True)
        old_total += block_tokens(old)
        new_total += block_tokens(new)
        print("%-22s %-14s %-14s"
              % (q[:20], "%d / %d" % (len(old), block_tokens(old)),
                 "%d / %d" % (len(new), block_tokens(new))))
    if queries:
        print("合计字元：旧 %d → 新 %d（省 %.0f%%）"
              % (old_total, new_total, 100 * (1 - new_total / max(1, old_total))))

    dry = store.decay_pass(dry_run=True)
    print("\n今天的归档预演：检查 %d 条，会归档 %d 条 %s"
          % (dry["checked"], dry["archived"], dry["ids"] or ""))

    # ---- 90 天模拟 ----
    if args.sim > 0:
        print("\n-- 模拟 %d 天 --" % args.sim)
        sim_now = time.time()
        rnd = random.Random(20261031)
        archived_total = 0
        for day in range(1, args.sim + 1):
            sim_now += 86400
            for _ in range(4):
                q = rnd.choice(queries) if queries else "聊天"
                store.search_memories(q, limit=6, budget_tokens=320, now=sim_now)
            stats = store.decay_pass(now=sim_now)
            archived_total = stats["archived"]
            if day % 15 == 0 or day == 1:
                ms = store.memory_stats(now=sim_now)
                print("  day %-3d 活跃 %-3d 归档 %-3d 平均保持度 %.2f"
                      % (day, ms["active"], ms["archived"], ms["avg_retention"]))
        print("\n  本次归档 %d 条：" % archived_total)
        for m in store.all_memories(400):
            if m.get("archived"):
                print("    #%-3d %-10s %s" % (m["id"], m["kind"], (m["content"] or "")[:40]))
        left = [m for m in store.all_memories(400) if not m.get("archived")]
        promises = [m for m in left if m["kind"] == "promise"]
        print("  仍记得的约定 %d 条（一条没丢）" % len(promises))

    print("=" * 62)


if __name__ == "__main__":
    main()
