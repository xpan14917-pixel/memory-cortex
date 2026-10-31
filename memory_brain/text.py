"""文本工具：中文二元组 + 英文/数字词。"""
import re


def tokenize(text):
    """中文二元组 + 英文/数字词，用于记忆召回。"""
    text = (text or "").lower()
    words = set(re.findall(r"[a-z0-9]{2,}", text))
    grams = set()
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(run) == 1:
            grams.add(run)
        else:
            grams.update(run[i : i + 2] for i in range(len(run) - 1))
    return words | grams
