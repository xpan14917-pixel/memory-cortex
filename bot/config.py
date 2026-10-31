"""配置读取。"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load(path=None):
    p = pathlib.Path(path) if path else ROOT / "config.json"
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save(cfg, path=None):
    p = pathlib.Path(path) if path else ROOT / "config.json"
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    tmp.replace(p)
