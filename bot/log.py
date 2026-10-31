"""日志：同时写控制台与 logs/bot.log，UTF-8。"""
import logging
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOG_DIR = pathlib.Path(os.environ.get("QQSOUL_LOG_DIR") or (ROOT / "logs"))
_configured = False


def setup(level=logging.INFO):
    global _configured
    if _configured:
        return
    _configured = True
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s")

    root = logging.getLogger()
    root.setLevel(level)

    fh = logging.FileHandler(LOG_DIR / "bot.log", encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get(name="bot"):
    setup()
    return logging.getLogger(name)
