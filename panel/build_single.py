# -*- coding: utf-8 -*-
"""把面板打成一个自包含 HTML（CSS/JS 全部内联，拷走就能开）。

    python panel/build_single.py
    → panel/小小记忆脑图.html
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent
html = (ROOT / "index.html").read_text(encoding="utf-8")

# 内联样式
css = (ROOT / "style.css").read_text(encoding="utf-8").lstrip("\ufeff")
html = html.replace('<link rel="stylesheet" href="style.css" />', "<style>\n" + css + "\n</style>")

# 内联每个 <script src="js/xxx.js"></script>
inlined = []


def inline_script(m):
    src = m.group(1)
    path = ROOT / src
    if not path.exists():          # 例如 data.real.js 不存在时跳过，保留 demo 回退
        return m.group(0)
    code = path.read_text(encoding="utf-8").lstrip("\ufeff").replace("</script", "<\\/script")
    inlined.append(src)
    return f"<script>\n/* {src} */\n{code}\n</script>"


html, n = re.subn(r'<script src="(js/[^"]+)"></script>', inline_script, html)
print("inlined scripts:", n)

html = html.replace(
    "<body>",
    "<body>\n<noscript><div style=\"position:fixed;inset:0;display:grid;place-items:center;"
    "background:#04060c;color:#9fb6d4;font-family:sans-serif;z-index:999\">"
    "这个面板需要 JavaScript 才能运行，请用 Chrome / Edge 打开。</div></noscript>",
)

out = ROOT / "小小记忆脑图.html"
out.write_text(html, encoding="utf-8")
print("wrote", out, len(html), "chars")
