"""记忆分区：把记忆归到脑图的五个检索区，供「先分区、再召回」使用。

分区只做**加权**，不做硬过滤 —— 分错了顶多排序略偏，不会把该想起的记忆挡在外面。
"""
REGION_LABEL = {
    "routine": "生活",
    "limbic": "情绪",
    "persona": "关系",
    "neural": "认知",
    "memory": "约定",
}
DEFAULT_REGION = "memory"

# 每个区的关键词（2 字以上，避免「想」这类单字误伤）
KEYWORDS = {
    "routine": [
        "上班", "下班", "加班", "吃饭", "早睡", "睡觉", "睡着", "起床", "早起", "周末",
        "很累", "好累", "困", "忙", "公司", "通勤", "午饭", "晚饭", "早饭", "作息",
        "熬夜", "晚睡", "休息", "下班后", "工作",
    ],
    "limbic": [
        "难过", "开心", "高兴", "生气", "委屈", "担心", "想念",
        "害怕", "情绪", "不安", "撒娇", "害羞", "舍不得", "失落", "心跳", "心疼",
        "烦躁", "低落", "介意", "吃醋", "安慰", "心跳乱",
    ],
    "persona": [
        "关系", "称呼", "名字", "意识", "离开", "陪伴", "亲密", "身份", "边界",
        "程序", "真人", "一生", "创造", "信任", "隐私", "日记", "存在", "归属",
        "创造出来", "面板",
    ],
    "neural": [
        "学习", "技能", "知识", "记住", "记忆", "方法", "项目", "代码", "可视化",
        "计划", "目标", "习惯", "喜好", "偏好", "好奇", "成长", "AI", "思考", "看书",
    ],
    "memory": [
        "约定", "答应", "承诺", "保证", "生日", "纪念", "发工资", "一起吃", "约好",
    ],
}

# 记忆类型的先验（score, region）
KIND_PRIOR = {
    "promise": ("memory", 2.4),
    "date": ("memory", 2.4),
    "preference": ("neural", 1.0),
    "fact": ("neural", 0.4),
    "event": ("routine", 0.3),
}


def classify(kind, content, keywords=""):
    """给一条记忆定一个分区。"""
    text = f"{content or ''} {keywords or ''}"
    scores = {r: 0.0 for r in KEYWORDS}
    for region, words in KEYWORDS.items():
        for w in words:
            if w in text:
                scores[region] += 1.0
    prior = KIND_PRIOR.get((kind or "").strip())
    if prior:
        scores[prior[0]] += prior[1]
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else DEFAULT_REGION


def query_regions(text):
    """查询里提到哪些区（可能多个）。"""
    text = text or ""
    hit = set()
    for region, words in KEYWORDS.items():
        if any(w in text for w in words):
            hit.add(region)
    return hit


def label(region):
    return REGION_LABEL.get(region, REGION_LABEL[DEFAULT_REGION])


def summary(counts, archived=0, total=None, max_regions=5):
    """一行分区摘要，给 prompt 用。

    counts: {"routine": 9, "limbic": 7, ...}
    """
    if not counts:
        return ""
    items = [(r, n) for r, n in counts.items() if n > 0]
    items.sort(key=lambda x: -x[1])
    items = items[:max_regions]
    body = "｜".join(f"{label(r)} {n}" for r, n in items)
    t = total if total is not None else sum(counts.values())
    tail = f"（共 {t} 条"
    if archived:
        tail += f"，{archived} 条已淡忘"
    tail += "）"
    return body + tail
