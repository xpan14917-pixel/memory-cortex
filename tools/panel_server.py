# -*- coding: utf-8 -*-
"""实时面板：静态托管 panel/，同时提供 /api/state 给前端轮询。

    python tools/panel_server.py            # http://127.0.0.1:8090
    python tools/panel_server.py --port 8091 --db data/bot.db

然后用浏览器打开 http://127.0.0.1:8090/?live=1
（必须走 http，file:// 下 fetch 会被浏览器拦掉）
"""
import argparse
import datetime
import json
import pathlib
import sqlite3
import sys
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve()
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))

from memory_brain import brainmap, forgetting      # noqa: E402

PANEL = REPO / "panel"
CACHE = {"ts": 0.0, "body": b""}


def snapshot(db_path, cache_seconds=1.5):
    """返回面板需要的最小快照；1.5 秒内的重复请求走缓存。"""
    now = time.time()
    if now - CACHE["ts"] < cache_seconds and CACHE["body"]:
        return CACHE["body"]

    con = sqlite3.connect("file:%s?mode=ro" % pathlib.Path(db_path).as_posix(), uri=True)
    con.row_factory = sqlite3.Row

    def rows(sql, args=()):
        return [dict(r) for r in con.execute(sql, args).fetchall()]

    memories = []
    for m in rows("SELECT * FROM memories ORDER BY ts"):
        memories.append({
            "id": m["id"],
            "ts": round(m["ts"], 3),
            "kind": m["kind"],
            "content": m["content"],
            "weight": m["weight"],
            "hits": m["hits"],
            "lastUsed": round(m.get("last_used") or 0, 3),
            "stability": round(float(m.get("stability") or 0), 2),
            "archived": int(m.get("archived") or 0),
            "superseded": m.get("superseded_by") is not None,
            "region": m.get("region") or brainmap.classify(m["kind"], m["content"]),
            "retention": round(forgetting.retention(m), 4),
        })

    state = {s["k"]: s["v"] for s in rows("SELECT * FROM state")}
    mood = json.loads(state.get("mood", "{}"))
    traits = json.loads(state.get("traits", "{}"))
    payload = {
        "serverTime": datetime.datetime.now().isoformat(timespec="seconds"),
        "counts": {
            "memories": len(memories),
            "archived": sum(1 for m in memories if m["archived"]),
            "superseded": sum(1 for m in memories if m["superseded"]),
            "messages": con.execute("SELECT COUNT(*) c FROM messages").fetchone()["c"],
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
        "messages": rows("SELECT ts, role, content FROM messages ORDER BY id DESC LIMIT 20"),
        "recall": getattr(snapshot, "last_recall", None),
    }
    con.close()
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    CACHE.update({"ts": now, "body": body})
    return body


def make_handler(db_path):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(PANEL), **kw)

        def _send(self, body, ctype):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/api/state", "/api/state.json"):
                try:
                    self._send(snapshot(db_path), "application/json; charset=utf-8")
                except Exception as e:  # noqa: BLE001
                    self._send(json.dumps({"error": str(e)}).encode(),
                               "application/json; charset=utf-8")
                return
            if path == "/api/health":
                self._send(b'{"ok":true}', "application/json; charset=utf-8")
                return
            if path == "/":
                self.path = "/index.html"
            super().do_GET()

        def log_message(self, fmt, *args):
            pass

    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--db", default=str(REPO / "data" / "bot.db"))
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    handler = make_handler(args.db)
    srv = ThreadingHTTPServer((args.host, args.port), handler)
    print("panel:  http://%s:%d/?live=1" % (args.host, args.port))
    print("api:    http://%s:%d/api/state" % (args.host, args.port))
    print("db:     %s" % args.db)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
