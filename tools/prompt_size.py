# -*- coding: utf-8 -*-
"""对比改前/改后的 system prompt 体积（不发请求）。"""
import pathlib
import shutil
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from memory_brain import forgetting
from bot import persona, state as state_mod   # noqa: E402
from memory_brain.store import Store                                # noqa: E402
from sim_forget import old_recall                          # noqa: E402

QUERIES = ["我今天加班到很晚", "你还记得我喜欢什么吗", "我想给你做一个大脑记忆", "晚安"]


def tok(s):
    return forgetting.estimate_tokens(s)


def main():
    src = ROOT / "data" / "bot.db"
    tmp = pathlib.Path(tempfile.gettempdir()) / ("prompt_%d.db" % int(time.time()))
    shutil.copy2(src, tmp)
    store = Store(tmp)
    card = persona.load(ROOT / "persona.json")
    st = state_mod.load(store)
    diary = store.latest_diary()
    life = diary.get("next_day") if diary else None
    recent = store.recent_messages(16)
    profile_all = store.profile_dict()
    profile_10 = store.profile_ranked(10)

    static = persona._static_block(card)
    print("静态块（人格 + 13 条规则，可被前缀缓存）：%d 字 ≈ %d tok" % (len(static), tok(static)))
    print("完整档案 %d 条 / 精简 %d 条" % (len(profile_all), len(profile_10)))

    print("\n%-26s %-22s %-22s %s" % ("查询", "改前 字/估tok", "改后 字/估tok", "变化"))
    tot_old = tot_new = 0
    for q in QUERIES:
        old_mems = old_recall(store, q, 6)
        new_mems = store.search_memories(q, limit=6, budget_tokens=320, dry_run=True)
        old_sys = persona.build_system(card, st, old_mems, profile_all, diary, life, "刚刚聊过",
                                       profile_limit=20)
        new_sys = persona.build_system(card, st, new_mems, profile_10, diary, life, "刚刚聊过",
                                       profile_limit=10)
        # 历史部分两边一样
        hist = "\n".join(persona._history_lines(recent, 10))
        old_full = old_sys + "\n\n【最近的对话】\n" + hist
        new_full = new_sys + "\n\n【最近的对话】\n" + hist
        tot_old += tok(old_full)
        tot_new += tok(new_full)
        print("%-26s %-22s %-22s %s"
              % (q[:24],
                 "%d / %d" % (len(old_full), tok(old_full)),
                 "%d / %d" % (len(new_full), tok(new_full)),
                 "%+d tok" % (tok(new_full) - tok(old_full))))

    print("\n合计：%d → %d tok，省 %.1f%%"
          % (tot_old, tot_new, 100 * (1 - tot_new / max(1, tot_old))))
    print("其中可缓存前缀 %d tok，按 DeepSeek 缓存价相当于再省 ~%d tok 的钱"
          % (tok(static), int(tok(static) * 0.9)))


if __name__ == "__main__":
    main()
