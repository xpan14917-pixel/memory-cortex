"""日记导出：把 diary 表渲染成 Markdown，写日记后自动同步一份可读文件。"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "日记.md"


def render(rows):
    lines = ["# 知夏的日记", ""]
    if not rows:
        lines.append("（还没写过日记，晚上 11 点后会自动写。）")
    for r in rows:
        lines += [
            f"## {r['date']}",
            "",
            f"**心情**：{r['mood'] or '—'}",
            "",
            f"{r['summary'] or ''}",
            "",
        ]
        if r["highlights"]:
            lines += [f"> 记住的细节：{r['highlights']}", ""]
        if r["next_day"]:
            lines += [f"> 明天打算：{r['next_day']}", ""]
        lines += ["---", ""]
    return "\n".join(lines)


def write(store, out=None):
    # 默认导出到「该数据库同目录」的 日记.md，
    # 避免测试用临时库时把真实日记覆盖掉。
    if out is None:
        out = pathlib.Path(store.path).parent / "日记.md"
    rows = store.conn().execute("SELECT * FROM diary ORDER BY date").fetchall()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(rows), encoding="utf-8")
    return out
