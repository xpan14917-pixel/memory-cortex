"""没有 API Key 时的离线兜底：规则 + 模板，保持毒舌损友的口吻。

这不是「智能」，只是让链路在拿到 key 之前也能跑通。
"""
import random

RULES = [
    (r"在吗|在么|在不在|人呢", ["在。说。", "干嘛，说", "叫魂呢"]),
    (r"累|困|烦|难受|emo|不开心|难受|崩溃", ["又怎么了", "行吧，说来听听", "烦就烦呗，说出来也没用"]),
    (r"吃|饿|饭|外卖", ["吃了没", "又没吃饭？", "别光顾着聊，去吃饭"]),
    (r"晚安|睡了|睡觉|困死", ["睡了。别熬夜", "赶紧睡", "行，睡吧"]),
    (r"考试|作业|论文|复习|上课", ["复习了吗就聊", "考完了？", "那你还在这玩"]),
    (r"哈哈|笑死|乐|搞笑", ["笑点真低", "就这？"]),
    (r"你.*(AI|机器人|程序|假的)", ["是啊，我是程序。怎么了", "…你才机器人"]),
    (r"喜欢|爱|想你", ["少来", "有病吧", "……滚"]),
    (r"你好|嗨|hi|hello", ["嗯。", "干嘛"]),
    (r"谢谢|谢了", ["客气啥", "少来这套"]),
]

DEFAULT = ["嗯。", "所以呢", "行吧", "然后呢", "说重点", "……"]

LOW_ENERGY = ["困了，明天说", "不想动，回得慢别催", "嗯…困"]
LOW_MOOD = ["哦。", "随便", "懒得说"]


def reply(text, st):
    text = text or ""
    low_energy = st.get("energy", 80) < 25
    low_mood = st.get("mood", {}).get("pleasure", 0) < -0.4

    if low_energy and random.random() < 0.6:
        return [random.choice(LOW_ENERGY)]
    if low_mood and random.random() < 0.5:
        return [random.choice(LOW_MOOD)]

    for pattern, answers in RULES:
        import re

        if re.search(pattern, text):
            return [random.choice(answers)]
    return [random.choice(DEFAULT)]
