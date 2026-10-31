"""memory-cortex 命令行：不装 QQ 也能单独用这个记忆库。

    memory-cortex add "用户喜欢喝冰美式" --kind preference --weight 1.2
    memory-cortex list
    memory-cortex search "今天点了什么"
    memory-cortex forget --dry-run
    memory-cortex stats
"""
import argparse
import json
import pathlib
import sys

from . import forgetting
from .store import Store


def _open(args):
    path = pathlib.Path(args.db)
    path.parent.mkdir(parents=True, exist_ok=True)
    return Store(path)


def cmd_add(args):
    store = _open(args)
    before = len(store.all_memories(100000))
    mid = store.add_memory(args.content, args.kind, args.keywords, args.weight)
    after = len(store.all_memories(100000))
    if mid is None:
        print("空内容，已忽略")
        return 1
    print("已记住 #%d（%s）：%s" % (mid, "新增" if after > before else "合并", args.content))
    return 0


def cmd_list(args):
    store = _open(args)
    rows = store.all_memories(args.limit)
    if not rows:
        print("（空）")
        return 0
    for m in rows:
        flag = "已淡忘" if m.get("archived") else "R=%.2f" % forgetting.retention(m)
        print("#%-4d %-10s %-8s %s  %s" % (
            m["id"], m["kind"], m.get("region") or "-", flag, m["content"][:60]))
    return 0


def cmd_search(args):
    store = _open(args)
    picked = store.search_memories(args.query, limit=args.k, budget_tokens=args.budget)
    print("查询：%s" % args.query)
    print("统计：%s" % json.dumps(getattr(store, "last_recall", {}), ensure_ascii=False))
    for m in picked:
        print("  [%s] %-34s R=%.2f score=%.2f" % (
            m["kind"], m["content"][:34], m["retention"], m["_score"]))
    if not picked:
        print("  （没有命中：关键词没撞上；可考虑加兜底召回）")
    return 0


def cmd_forget(args):
    store = _open(args)
    res = store.decay_pass(dry_run=args.dry_run)
    print("检查 %d 条，%s %d 条 %s" % (
        res["checked"], "将归档" if args.dry_run else "已归档",
        res["archived"], res["ids"] or ""))
    return 0


def cmd_stats(args):
    store = _open(args)
    s = store.memory_stats()
    counts, archived = store.region_counts()
    print(json.dumps({"stats": s, "regions": counts, "archived": archived},
                     ensure_ascii=False, indent=2))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="memory-cortex", description="会遗忘的记忆引擎")
    ap.add_argument("--db", default="./data/bot.db", help="SQLite 路径")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add", help="写一条记忆")
    p.add_argument("content")
    p.add_argument("--kind", default="fact",
                   choices=["fact", "event", "preference", "promise", "date"])
    p.add_argument("--weight", type=float, default=1.0)
    p.add_argument("--keywords", default=None)
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("list", help="列出记忆")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("search", help="按遗忘曲线召回")
    p.add_argument("query")
    p.add_argument("-k", type=int, default=6)
    p.add_argument("--budget", type=int, default=320)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("forget", help="跑一次遗忘结算（归档）")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_forget)

    p = sub.add_parser("stats", help="记忆库概况")
    p.set_defaults(func=cmd_stats)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
