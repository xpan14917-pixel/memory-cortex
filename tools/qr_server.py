"""本地扫码页：始终展示 NapCat 最新的 qrcode.png，自动刷新。"""
import pathlib
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent.parent
QR = ROOT / ".runtime" / "napcat" / "napcat" / "cache" / "qrcode.png"

HTML = """<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<title>NapCat 扫码登录</title>
<style>
 body{background:#0f1117;color:#e8e8e8;font-family:system-ui,"Microsoft YaHei",sans-serif;
      display:flex;flex-direction:column;align-items:center;justify-content:flex-start;
      min-height:100vh;margin:0;padding:36px 16px 24px;box-sizing:border-box}
 h2{font-weight:600;margin:0 0 4px}
 p{color:#9aa0a6;margin:6px 0 18px;font-size:14px}
 img{width:280px;height:280px;background:#fff;padding:14px;border-radius:12px;
     image-rendering:pixelated;box-shadow:0 0 30px rgba(255,255,255,.08)}
 .st{font-size:12px;color:#6b7280;margin-top:14px}
</style></head>
<body>
 <h2>手机 QQ（小号）扫这张</h2>
 <p>页面会自动换最新二维码 · 扫完在手机上点「允许登录」</p>
 <img id="q" src="/qr" alt="二维码">
 <div class="st" id="st"></div>
<script>
 let last = 0;
 async function tick(){
   const r = await fetch('/meta', {cache:'no-store'});
   const m = await r.json();
   if (m.mtime !== last) { last = m.mtime; document.getElementById('q').src = '/qr?t=' + Date.now(); }
   document.getElementById('st').textContent = m.exists
     ? ('二维码生成于 ' + m.time + ' · 自动刷新中')
     : '等待 NapCat 生成二维码…';
 }
 setInterval(tick, 2000); tick();
</script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            self._send(200, HTML.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path.startswith("/qr"):
            if QR.exists():
                self._send(200, QR.read_bytes(), "image/png")
            else:
                self._send(404, b"no qr", "text/plain")
        elif self.path.startswith("/meta"):
            import json
            import datetime

            info = {"exists": QR.exists(), "mtime": 0, "time": ""}
            if QR.exists():
                st = QR.stat()
                info["mtime"] = st.st_mtime
                info["time"] = datetime.datetime.fromtimestamp(st.st_mtime).strftime("%H:%M:%S")
            self._send(200, json.dumps(info).encode(), "application/json")
        else:
            self._send(404, b"not found", "text/plain")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8790
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"QR page: http://127.0.0.1:{port}")
    srv.serve_forever()
