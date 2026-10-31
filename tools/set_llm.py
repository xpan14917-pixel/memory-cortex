"""把 bot 切到任意 OpenAI 兼容的大模型接口。

用法示例：
  python tools\\set_llm.py --show
  python tools\\set_llm.py --base http://127.0.0.1:11434/v1 --model qwen2.5:3b --key ollama
  python tools\\set_llm.py --base https://api.deepseek.com --model deepseek-chat --key sk-xxx
  python tools\\set_llm.py --small-context          # 小模型：历史 4 条、记忆 3 条、prompt 3000 字
  python tools\\set_llm.py --test                   # 用当前配置发一次请求自测

改完需要重启 bot 生效（watchdog 一分钟内会自动拉起，或手动 run.bat）。
"""
import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CFG = ROOT / "config.json"


def load():
    with open(CFG, "r", encoding="utf-8") as f:
        return json.load(f)


def save(cfg):
    with open(CFG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def show(cfg):
    lc = cfg["llm"]
    b = cfg.get("bot", {})
    print("base_url   :", lc["base_url"])
    print("model      :", lc["model"])
    print("api_key    :", ("已设置(len=%d)" % len(lc["api_key"])) if lc.get("api_key") else "(空)")
    print("temperature:", lc.get("temperature"))
    print("history    :", b.get("history_messages", 10), "条 / prompt 上限",
          b.get("max_prompt_chars", 6000), "字")


def test(cfg):
    sys.path.insert(0, str(ROOT))
    from bot.llm import LLM

    lc = cfg["llm"]
    llm = LLM(lc["base_url"], lc["api_key"], lc["model"], timeout=30, max_tokens=150)
    try:
        data = llm.chat_json(
            [
                {"role": "system", "content": '你只输出 JSON：{"ok": true, "who": "小模型"}'},
                {"role": "user", "content": "自测一下"},
            ],
            temperature=0.2,
        )
        print("自测通过：", json.dumps(data, ensure_ascii=False))
        return True
    except Exception as e:  # noqa: BLE001
        print("自测失败：", e)
        print("排查：服务是否在跑？base_url 是否带 /v1？模型名是否正确？")
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", help="如 http://127.0.0.1:11434/v1")
    ap.add_argument("--model", help="模型名，如 qwen2.5:3b")
    ap.add_argument("--key", help="API key；本地模型随便填")
    ap.add_argument("--temperature", type=float)
    ap.add_argument("--history", type=int, help="带多少条历史对话")
    ap.add_argument("--max-prompt", type=int, help="prompt 字符上限")
    ap.add_argument("--small-context", action="store_true",
                    help="小上下文预设：历史 4、记忆 3、prompt 3000")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--test", action="store_true")
    args = ap.parse_args()

    cfg = load()
    changed = False

    if args.show:
        show(cfg)
        return 0

    if args.base:
        cfg["llm"]["base_url"] = args.base.rstrip("/")
        changed = True
    if args.model:
        cfg["llm"]["model"] = args.model
        changed = True
    if args.key is not None:
        cfg["llm"]["api_key"] = args.key
        changed = True
    if args.temperature is not None:
        cfg["llm"]["temperature"] = args.temperature
        changed = True
    if args.history is not None:
        cfg["bot"]["history_messages"] = args.history
        changed = True
    if args.max_prompt is not None:
        cfg["bot"]["max_prompt_chars"] = args.max_prompt
        changed = True
    if args.small_context:
        cfg["bot"]["history_messages"] = 4
        cfg["bot"]["memory_top_k"] = 3
        cfg["bot"]["max_prompt_chars"] = 3000
        changed = True

    if changed:
        save(cfg)
        print("配置已更新：")
        show(cfg)
        print("\n重启 bot 后生效：结束 python 进程，watchdog 会在 1 分钟内拉起；"
              "或直接运行 run.bat。")

    if args.test or changed:
        print("\n--- 自测 ---")
        test(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
