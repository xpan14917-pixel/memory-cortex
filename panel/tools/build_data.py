# -*- coding: utf-8 -*-
"""从 SQLite 导出记忆脑图需要的数据（只读）。

    python panel/tools/build_data.py
    python panel/tools/build_data.py --db examples/demo.db --out panel/js/data.real.js
"""
import argparse
import datetime
import json
import pathlib
import sqlite3
import sys

HERE = pathlib.Path(__file__).resolve()
REPO = HERE.parents[2]                     # 仓库根目录
sys.path.insert(0, str(REPO))

from memory_brain import brainmap, forgetting      # noqa: E402


def export(db_path, out_path, persona_file=None):
    con = sqlite3.connect("file:%s?mode=ro" % pathlib.Path(db_path).as_posix(), uri=True)
    con.row_factory = sqlite3.Row

    def rows(sql, args=()):
        return [dict(r) for r in con.execute(sql, args).fetchall()]

    memories = []
    for m in rows("SELECT * FROM memories ORDER BY ts"):
        kw = [k for k in (m.get("keywords") or "").replace("，", " ").split() if k]
        memories.append({
            "id": m["id"],
            "ts": round(m["ts"], 3),
            "kind": m["kind"],
            "content": m["content"],
            "keywords": kw,
            "weight": m["weight"],
            "hits": m["hits"],
            "lastUsed": round(m.get("last_used") or 0, 3),
            "stability": round(float(m.get("stability") or 0), 2),
            "archived": int(m.get("archived") or 0),
            "region": m.get("region") or brainmap.classify(
                m["kind"], m["content"], m.get("keywords")),
            "retention": round(forgetting.retention(m), 4),
        })

    msgs = [{"id": m["id"], "ts": round(m["ts"], 3), "role": m["role"],
             "content": m["content"]} for m in rows("SELECT * FROM messages ORDER BY ts")]
    profile = [{"key": p["key"], "value": p["value"], "confidence": p["confidence"]}
               for p in rows("SELECT * FROM profile")]
    state = {s["k"]: s["v"] for s in rows("SELECT * FROM state")}
    mood = json.loads(state.get("mood", "{}"))
    traits = json.loads(state.get("traits", "{}"))

    persona_file = pathlib.Path(persona_file or (REPO / "persona.json"))
    persona = json.loads(persona_file.read_text(encoding="utf-8")) if persona_file.exists() else {}

    data = {
        "generatedAt": datetime.datetime.now().isoformat(timespec="seconds"),
        "persona": {
            "name": persona.get("name", "小小"),
            "archive": persona.get("name", "小小"),
            "age": persona.get("age", 20),
            "identity": persona.get("identity", ""),
            "speech": persona.get("speech", []),
            "taboos": persona.get("taboos", []),
        },
        "state": {
            "pleasure": mood.get("pleasure", 0),
            "arousal": mood.get("arousal", 0),
            "dominance": mood.get("dominance", 0),
            "energy": float(state.get("energy", 0)),
            "intimacy": float(state.get("intimacy", 0)),
            "traits": traits,
        },
        "memories": memories,
        "messages": msgs,
        "profile": profile,
        "proactive": rows("SELECT ts, trigger, content FROM proactive_log"),
        "counts": {
            "messages": len(msgs),
            "memories": len(memories),
            "archived": sum(1 for m in memories if m["archived"]),
            "profile": len(profile),
        },
    }

    js = "/* AUTO-GENERATED — do not edit by hand. */\n"
    js += "window.__REAL = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n"
    out = pathlib.Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(js, encoding="utf-8")
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(REPO / "data" / "bot.db"))
    ap.add_argument("--out", default=str(REPO / "panel" / "js" / "data.real.js"))
    ap.add_argument("--persona", default=None)
    args = ap.parse_args()
    if not pathlib.Path(args.db).exists():
        print("找不到数据库：", args.db)
        return 1
    data = export(args.db, args.out, args.persona)
    print("wrote", args.out)
    print("memories", len(data["memories"]), "archived", data["counts"]["archived"],
          "messages", len(data["messages"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
