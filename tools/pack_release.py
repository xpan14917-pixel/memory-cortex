# -*- coding: utf-8 -*-
"""打包「可公开」的仓库快照，并扫描敏感信息。

    python tools/pack_release.py
    → dist/memory-cortex.zip（含 README/LICENSE/代码/示例，不含任何私人数据）
"""
import fnmatch
import pathlib
import re
import sys
import zipfile

REPO = pathlib.Path(__file__).resolve().parents[1]
OUT = REPO / "dist" / "memory-cortex.zip"

EXCLUDE_DIRS = {".runtime", "data", "logs", "backups", "dist", ".git",
                "__pycache__", ".venv", "venv"}
EXCLUDE_FILES = ["config.json", "persona.json", "*.pyc", "*.db", "*.db-wal", "*.db-shm",
                 "data.real.js", "小小记忆脑图.html", "preview.png", "preview-live.png", "*.log", "*.pid"]
EXCLUDE_ANY = ["tmp*"]

# 这些字符串一旦出现在要发布的文件里就报警
SECRET_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "疑似 API Key"),
    (re.compile(r"\b26\d{8}\b"), "疑似 QQ 号"),
    (re.compile(r"\b[0-9a-f]{24}\b"), "疑似 OneBot token"),
]


def ignored(rel: pathlib.PurePath) -> bool:
    parts = rel.parts
    if any(p in EXCLUDE_DIRS for p in parts):
        return True
    if any(fnmatch.fnmatch(parts[-1], pat) for pat in EXCLUDE_FILES):
        return True
    if any(fnmatch.fnmatch(p, "tmp*") for p in parts):
        return True
    return False


def main():
    files = []
    for p in REPO.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(REPO)
        if ignored(rel):
            continue
        files.append((rel, p))
    files.sort(key=lambda x: str(x[0]).lower())

    warnings = []
    for rel, p in files:
        if p.suffix.lower() in {".png", ".jpg", ".zip"}:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pat, label in SECRET_PATTERNS:
            for m in pat.finditer(text):
                warnings.append("%s: %s（%s）" % (rel, label, m.group(0)[:8] + "…"))
                break

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for rel, p in files:
            z.write(p, "memory-cortex/" + str(rel).replace("\\", "/"))

    size = OUT.stat().st_size / 1024
    print("打包 %d 个文件 → %s（%.0f KB）" % (len(files), OUT, size))
    for rel, _ in files:
        print("  ", rel)
    print()
    if warnings:
        print("!! 发现 %d 处可疑内容：" % len(warnings))
        for w in warnings[:20]:
            print("   -", w)
        return 1
    print("未发现 API Key / QQ 号 / token。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
