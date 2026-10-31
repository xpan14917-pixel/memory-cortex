"""把日记导出成 Markdown（写日记时也会自动导出，这里用于手动刷新）。"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot import diary_export  # noqa: E402
from memory_brain.store import Store  # noqa: E402


def main():
    store = Store(ROOT / "data" / "bot.db")
    out = diary_export.write(store)
    print("已导出 ->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
