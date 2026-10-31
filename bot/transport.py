"""OneBot v11 传输层（纯标准库）。

- OneBotAPI：主动调用 NapCat 的 HTTP API（发送消息等）
- EventServer：接收 NapCat 通过 HTTP POST 上报的事件

设计为不阻塞：HTTP 线程只负责收包入队，业务在独立线程处理。
"""
import json
import queue
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .log import get

log = get("transport")


class OneBotAPI:
    def __init__(self, base, token="", timeout=15):
        self.base = base.rstrip("/")
        self.token = token
        self.timeout = timeout

    def call(self, action, payload=None, timeout=None):
        url = f"{self.base}/{action}"
        data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                body = resp.read().decode("utf-8", "replace")
            result = json.loads(body) if body else {}
            if result.get("status") == "failed":
                log.warning("onebot %s failed: %s", action, body[:300])
            return result
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            log.error("onebot %s HTTP %s: %s", action, e.code, detail)
            return {"status": "failed", "http": e.code, "detail": detail}
        except Exception as e:  # noqa: BLE001
            log.error("onebot %s error: %s", action, e)
            return {"status": "error", "error": str(e)}

    # ---- 常用动作 ----
    def get_login_info(self):
        return self.call("get_login_info")

    def send_private(self, user_id, message):
        return self.call(
            "send_private_msg",
            {"user_id": int(user_id), "message": message, "auto_escape": False},
        )

    def send_group(self, group_id, message):
        return self.call(
            "send_group_msg",
            {"group_id": int(group_id), "message": message, "auto_escape": False},
        )


class EventServer:
    """监听 NapCat 的 HTTP POST 上报。"""

    def __init__(self, host, port, path, on_event):
        self.host = host
        self.port = port
        self.path = path
        self.on_event = on_event
        self._httpd = None
        self._thread = None

    def start(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt, *args):  # 静默默认访问日志
                pass

            def _reject(self, code=404):
                self.send_response(code)
                self.send_header("Content-Length", "0")
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True

            def _read_body(self):
                """兼容 Content-Length 与 chunked（NapCat 默认用 chunked）。"""
                te = (self.headers.get("Transfer-Encoding") or "").lower()
                if "chunked" in te:
                    parts = []
                    while True:
                        line = self.rfile.readline(65536).strip()
                        if not line:
                            continue
                        size = int(line.split(b";")[0], 16)
                        if size == 0:
                            self.rfile.readline(65536)
                            break
                        parts.append(self.rfile.read(size))
                        self.rfile.read(2)
                    return b"".join(parts)
                length = int(self.headers.get("Content-Length") or 0)
                return self.rfile.read(length) if length else b""

            def do_GET(self):
                if self.path.rstrip("/") == "/health":
                    body = b'{"ok":true}'
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(body)
                    self.close_connection = True
                else:
                    self._reject()

            def do_POST(self):
                if not self.path.startswith(outer.path):
                    self._reject()
                    return
                try:
                    raw = self._read_body() or b"{}"
                    event = json.loads(raw.decode("utf-8"))
                except Exception as e:  # noqa: BLE001
                    log.warning("bad event payload: %s", e)
                    self._reject(400)
                    return

                # 先回 200，NapCat 不等待业务处理
                body = b"{}"
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)
                self.close_connection = True

                threading.Thread(
                    target=outer._dispatch, args=(event,), daemon=True
                ).start()

        self._httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self._httpd.daemon_threads = True
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        log.info("event server listening on http://%s:%s%s", self.host, self.port, self.path)

    def _dispatch(self, event):
        try:
            self.on_event(event)
        except Exception:  # noqa: BLE001
            log.exception("event handler crashed")

    def stop(self):
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()


class SerialWorker:
    """串行队列：同一时间只处理一条消息，避免并发抢上下文。"""

    def __init__(self, handler):
        self.handler = handler
        self.q = queue.Queue()
        self.t = threading.Thread(target=self._run, daemon=True)
        self.t.start()

    def submit(self, item):
        self.q.put(item)

    def _run(self):
        while True:
            item = self.q.get()
            try:
                self.handler(item)
            except Exception:  # noqa: BLE001
                log.exception("worker crashed")
            finally:
                self.q.task_done()


# ---- 消息段工具 ----

def segments_to_text(message):
    """从 OneBot 消息段中提取纯文本与图片占位。"""
    if isinstance(message, str):
        return message
    parts = []
    for seg in message or []:
        if not isinstance(seg, dict):
            continue
        t = seg.get("type")
        data = seg.get("data") or {}
        if t == "text":
            parts.append(data.get("text", ""))
        elif t == "at":
            parts.append(f"@{data.get('qq', '')}")
        elif t == "image":
            parts.append("[图片]")
        elif t == "face":
            parts.append("[表情]")
        elif t == "record":
            parts.append("[语音]")
        elif t == "video":
            parts.append("[视频]")
        elif t == "file":
            parts.append("[文件]")
        elif t == "reply":
            continue
    return "".join(parts).strip()
