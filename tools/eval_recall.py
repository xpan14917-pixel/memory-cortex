# -*- coding: utf-8 -*-
"""召回评测：同一批查询，对比「无遗忘曲线」与「Memory Cortex」的排序质量。

    python tools/eval_recall.py            # 合成评测集（examples/eval_set.json）
    python tools/eval_recall.py --db data/bot.db   # 换成自己的库（只读，不发请求）

指标：Recall@3 / MRR@5 / 平均注入 token。
基线 = 旧逻辑：关键词命中 ×2 + 字面子串 ×0.3 + weight×0.5，不看遗忘、不分预算。
"""
import argparse
import json
import pathlib
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve()
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))

from memory_brain import brainmap, config, forgetting          # noqa: E402
from memory_brain.store import Store                           # noqa: E402
from memory_brain.text import tokenize                         # noqa: E402

DAY = 86400


def build_synthetic(db_path):
    """按评测集造一个受控的库：target 新、decoy 老且从未被想起。"""
    store = Store(db_path)
    now = time.time()
    for item in json.loads((REPO / "examples" / "eval_set.json")
                           .read_text(encoding="utf-8"))["items"]:
        if not store.conn().execute(
                "SELECT 1 FROM memories WHERE content=?", (item["target"],)).fetchone():
            store.conn().execute(
                "INSERT INTO memories(ts, kind, content, keywords, weight, hits, last_used,"
                " stability, archived, region) VALUES(?,?,?,?,?,?,?,?,0,?)",
                (now - 2 * DAY, "fact", item["target"],
                 " ".join(sorted(tokenize(item["target"]))[:12]), 1.2, 1,
                 now - DAY, forgetting.stability("fact", 1.2, 1),
                 brainmap.classify("fact", item["target"])))
        if item.get("decoy") and not store.conn().execute(
                "SELECT 1 FROM memories WHERE content=?", (item["decoy"],)).fetchone():
            store.conn().execute(
                "INSERT INTO memories(ts, kind, content, keywords, weight, hits, last_used,"
                " stability, archived, region) VALUES(?,?,?,?,?,?,?,?,0,?)",
                (now - 900 * DAY, "fact", item["decoy"],
                 " ".join(sorted(tokenize(item["decoy"]))[:12]), 1.2, 0, 0,
                 forgetting.stability("fact", 1.2, 0),
                 brainmap.classify("fact", item["decoy"])))
    store.conn().commit()
    return store


def baseline_rank(store, query, limit=5):
    """旧逻辑：没有遗忘曲线、没有预算、没有分区加分。"""
    q = tokenize(query)
    rows = store.conn().execute(
        "SELECT * FROM memories WHERE COALESCE(archived,0)=0 "
        "ORDER BY weight DESC, ts DESC LIMIT 300").fetchall()
    now = time.time()
    scored = []
    for r in rows:
        m = dict(r)
        kws = set((m.get("keywords") or "").split())
        overlap = len(q & kws)
        substr = sum(1 for t in q if t in m["content"]) if not overlap else 0
        if overlap == 0 and substr == 0:
            continue
        recency = max(0.0, 1.0 - (now - m["ts"]) / (90 * DAY))
        scored.append((overlap * 2.0 + substr * 0.3 + m["weight"] * 0.5 + recency, m))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [m["content"] for _, m in scored[:limit]]


def ours_rank(store, query, limit=5):
    got = store.search_memories(query, limit=limit, budget_tokens=100000, dry_run=True)
    return [m["content"] for m in got]


def evaluate(store, items, ranker):
    hits3 = hits1 = 0
    rr = 0.0
    tokens = 0
    ranks = []
    for item in items:
        picked = ranker(store, item["query"])
        tokens += sum(forgetting.estimate_tokens(p) for p in picked)
        try:
            rank = picked.index(item["target"]) + 1
        except ValueError:
            rank = None
        ranks.append(rank)
        if rank:
            hits3 += rank <= 3
            hits1 += rank == 1
            if rank <= 5:
                rr += 1.0 / rank
    n = len(items)
    reachable = [r for r in ranks if r is not None]
    nr = max(1, len(reachable))
    return {
        "recall@3": hits3 / n,
        "recall@1": hits1 / n,
        "mrr@5": rr / n,
        "avg_tokens": tokens / n,
        "reachable": len(reachable),
        "reach_recall@3": sum(1 for r in reachable if r <= 3) / nr,
        "reach_mrr": sum((1.0 / r) for r in reachable if r <= 5) / nr,
        "ranks": ranks,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None, help="用自己的库（只读副本）")
    args = ap.parse_args()

    data = json.loads((REPO / "examples" / "eval_set.json").read_text(encoding="utf-8"))
    items = data["items"]

    tmp = tempfile.TemporaryDirectory()
    if args.db:
        src = pathlib.Path(args.db)
        dst = pathlib.Path(tmp.name) / "eval.db"
        dst.write_bytes(src.read_bytes())
        store = Store(dst)
        items = [it for it in items
                 if store.conn().execute("SELECT 1 FROM memories WHERE content=?",
                                         (it["target"],)).fetchone()]
        print("用自己的库：%s，匹配到 %d/%d 条查询" % (src, len(items), len(data["items"])))
    else:
        store = build_synthetic(pathlib.Path(tmp.name) / "eval.db")
        print("合成评测集：%d 条查询 / %d 条记忆"
              % (len(items), store.conn().execute("SELECT COUNT(*) c FROM memories").fetchone()["c"]))

    if not items:
        print("没有可评测的查询（库里找不到 target）")
        return 1

    base = evaluate(store, items, baseline_rank)
    ours = evaluate(store, items, ours_rank)

    print("\n%-22s %10s %10s %8s" % ("指标", "基线(无遗忘)", "Memory Cortex", "变化"))
    for key, label in [("recall@1", "Recall@1"), ("recall@3", "Recall@3"),
                       ("mrr@5", "MRR@5"), ("avg_tokens", "平均注入 token")]:
        b, o = base[key], ours[key]
        if key == "avg_tokens":
            print("%-22s %10.1f %10.1f %+8.1f" % (label, b, o, o - b))
        else:
            print("%-22s %10.3f %10.3f %+8.3f" % (label, b, o, o - b))

    print("\n可被关键词检索到的查询：基线 %d/%d，Memory Cortex %d/%d"
          % (base["reachable"], len(items), ours["reachable"], len(items)))
    print("在这部分查询上：Recall@3 基线 %.3f → %.3f；MRR@5 %.3f → %.3f"
          % (base["reach_recall@3"], ours["reach_recall@3"], base["reach_mrr"], ours["reach_mrr"]))
    print("\n（Recall@1/3 越高越好；MRR 越接近 1 越好；token 越低越省）")
    print("（关键词完全不重合的查询两边都召不回 —— 这是没有向量召回的已知限制）")
    store.close()
    tmp.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
