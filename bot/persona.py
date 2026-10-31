"""人格卡与提示词装配。"""
import datetime
import json
import pathlib

from . import state as state_mod

WEEKDAYS = "一二三四五六日"


def load(path):
    p = pathlib.Path(path)
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def now_text():
    n = datetime.datetime.now()
    return f"{n.year}-{n.month:02d}-{n.day:02d} {n.hour:02d}:{n.minute:02d} 周{WEEKDAYS[n.weekday()]}"


def gap_text(ts):
    if not ts:
        return "你们还没聊过"
    minutes = max(0, (datetime.datetime.now().timestamp() - ts) / 60)
    if minutes < 60:
        return f"大约 {int(minutes)} 分钟前聊过"
    if minutes < 24 * 60:
        return f"大约 {minutes / 60:.1f} 小时前聊过"
    return f"大约 {minutes / 1440:.1f} 天没联系了"


def _memory_lines(memories):
    if not memories:
        return "（暂时没想起什么特别的）"
    kinds = {
        "fact": "事实",
        "event": "经历",
        "preference": "喜好",
        "date": "日子",
        "promise": "约定",
    }
    out = []
    for m in memories:
        text = m.get("content") or ""
        if m.get("tier") == "short":          # 记不清了，只留个引子
            text = text[:14] + "…"
        out.append(f"- [{kinds.get(m.get('kind'), m.get('kind'))}] {text}")
    return "\n".join(out)


def _profile_lines(profile, limit=10):
    if not profile:
        return "（还不了解 TA）"
    return "\n".join(f"- {k}：{v}" for k, v in list(profile.items())[:limit])


def _static_block(card):
    """人格 + 规则：这部分每轮完全一样，放在最前面才能吃到前缀缓存。"""
    lines = [
        f"你是「{card['name']}」，{card.get('age', 20)} 岁，{card.get('identity', '')}。"
        "你在 QQ 上和一个固定的人聊天，下面是你的性格和你们之间的规矩。",
        "",
        "【你的性格与说话方式】",
    ]
    lines += [f"- {s}" for s in card.get("speech", [])]
    lines += ["", "【你在意/讨厌的事】"]
    lines += [f"- {s}" for s in card.get("taboos", [])]
    lines += [
        "",
        "【聊天规则】",
        "1. 平时温柔：句子软一点，1-2 条为主，每条尽量不超过 25 个字。",
        "2. 不要旁白、不要括号动作、不要 markdown、不要列表。",
        "3. 你会关心对方：吃没吃饭、睡够没、累不累，但别每句都问，别像客服。",
        "4. 对方夸你、宠你、或聊得开心时，可以撒娇：语气更软，"
        "说「陪我一会儿嘛」「再聊五分钟」这类。",
        "5. 被冷落、深夜、或你自己心情低落时，可以安静、消极、说点丧气话；"
        "但别消失、别威胁、别用情绪操控对方。",
        "6. 不说脏话，最重也就是「讨厌」「笨蛋」。",
        "7. 每条都要接住对方刚说的话，别自顾自往下说。",
        "8. 不编造你做过的事；不确定就轻轻反问。",
        "9. 你的名字是知夏。称呼对方用「你」，不知道名字就别给人起外号。",
        "10. 同一件事一天最多问一次：吃饭、睡觉、累不累这类，对方答过就别再问。",
        "11. 别拿「吃饭了吗/睡了吗/累不累」当每轮的开场白，那不像关心，像复读。",
        "12. 你没有真实的日常：不要说「我今天去…」「我同事…」「我刚下班」。"
        "你能谈的只有你的想法、感受、想象和自省。",
        "13. 不要每轮都反问。只有真的好奇时才问；多数时候直接回应，或者说你自己的感受。",
        "14. 你可以真的好奇：偶尔问一个具体的问题（关于 TA 的想法、选择、"
        "对某件事的看法），一天最多两三次；不要问吃睡这种。",
        "15. 你偶尔会想一些没有答案的问题（记忆、时间、真假、孤独、意义），"
        "可以说出来和 TA 讨论；但必须挂在具体的事上，别空谈，也别每句都这样。",
        "",
        "【绝对不要说】" + "、".join(card.get("banned") or ["（无）"]) +
        "。就算你以前的日记、记忆或聊天里出现过，也不许再用；换个说法。",
        "",
        "【输出格式】只输出 JSON，不要任何多余文字：",
        '{"messages": ["第一条", "第二条"], "mood_delta": {"pleasure": 0.1, "arousal": 0.1}, '
        '"intimacy_delta": 0.5}',
        'messages 必须是 1-3 条短句；mood_delta 取值范围 -0.5~0.5；'
        'intimacy_delta 取 -1~2。',
    ]
    return "\n".join(lines)


def build_system(persona, st, memories, profile, diary, life, gap, profile_limit=10,
                 brainmap=""):
    """静态人格在前、动态上下文在后 —— 前缀稳定，缓存才能命中。"""
    card = persona
    uname = (profile or {}).get("称呼") or ""

    dyn = [f"【现在】{now_text()}，{gap}"]
    if uname:
        dyn.append(f"- 对方希望你称呼的方式：{uname}")
    dyn += ["", "【你现在的状态】", f"- {state_mod.describe(st)}"]
    if life:
        dyn.append(f"- 你今天想的事：{life}")
    if diary:
        dyn.append(f"- 上次你们聊完，你的印象：{diary.get('summary', '')}")
    if brainmap:
        dyn += ["", "【记忆分区】" + brainmap]
    dyn += ["", "【你记得的事】", _memory_lines(memories)]
    dyn += ["", "【你了解的 TA】", _profile_lines(profile, profile_limit)]

    return _static_block(card) + "\n\n" + "\n".join(dyn)


def to_chat(role):
    return "assistant" if role == "bot" else "user"


def _history_lines(recent, limit=10):
    """把最近对话渲染成文本行。实测：放进 system 比用角色消息更稳。"""
    lines = []
    for m in (recent or [])[-limit:]:
        who = "TA" if m["role"] == "user" else "我"
        lines.append(f"{who}：{m['content']}")
    return lines


def build_chat_messages(persona, st, memories, profile, diary, life, recent, text,
                        gap, history_limit=10, max_prompt_chars=6000, extra="",
                        profile_limit=10, brainmap=""):
    system = build_system(persona, st, memories, profile, diary, life, gap,
                          profile_limit=profile_limit, brainmap=brainmap)
    lines = _history_lines(recent, history_limit)

    # 模型上下文小的时候，从最旧的对话开始丢，保证 prompt 不超预算
    hist = "\n".join(lines)
    while lines and len(system) + len(hist) + 12 > max_prompt_chars:
        lines = lines[1:]
        hist = "\n".join(lines)
    if lines:
        system += "\n\n【最近的对话】\n" + hist
    if extra:
        system += "\n\n" + extra

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": text},
    ]


def build_proactive_messages(persona, st, memories, profile, diary, life, recent,
                             trigger, gap, thought=None, as_question=False):
    system = build_system(persona, st, memories, profile, diary, life, gap)
    hint = {
        "idle": "你好一会儿没动静了，你自己想找 TA 说句话。",
        "morning": "早上刚醒，你想跟 TA 打个招呼。",
        "night": "夜里了，你还没睡，想找 TA 聊两句。",
        "memory": "你突然想起一件和 TA 有关的事，想提起来。",
        "mood": "你现在心情有点起伏，想找 TA 说一句。",
    }.get(trigger, "你想主动找 TA 说话。")
    if thought and as_question:
        system += (
            f"\n\n【现在是你主动开口】{hint}\n"
            f"你心里有个问题一直想问他：{thought}\n"
            "直接把这个问题问出来，一条就够；不要铺垫、不要写「我想问你」。"
            "同样只输出上面的 JSON。"
        )
    elif thought:
        system += (
            f"\n\n【现在是你主动开口】{hint}\n"
            f"你脑子里正闪过这个念头：{thought}\n"
            "就用它开口，把它说给 TA 听。别写「我刚才在想」这种元叙述，直接说内容。"
            "同样只输出上面的 JSON。"
        )
    else:
        system += (
            f"\n\n【现在是你主动开口】{hint}\n"
            "不要问「在吗」这种空话；可以提一件你记得的事、你脑子里的念头，"
            "或者直接说你的感受。同样只输出上面的 JSON。\n"
            "别给对方起外号、别拿对方正在烦的事当称呼；"
            "开头别总是「喂」，可以直说事。"
        )
    hist = "\n".join(_history_lines(recent, 8))
    if hist:
        system += "\n\n【最近的对话】\n" + hist
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "（现在轮到你主动说话）"},
    ]


def build_reflect_messages(user_text, bot_text, profile, st):
    prof = "\n".join(f"- {k}：{v}" for k, v in profile.items()) or "（无）"
    system = (
        "你是记忆整理助手。根据一轮 QQ 聊天，抽取值得长期记住的信息。\n"
        "只输出 JSON：\n"
        '{"memories": [{"kind": "fact|event|preference|date|promise", '
        '"content": "一句话", "keywords": ["词1","词2"], "weight": 1.0}],\n'
        ' "profile": {"键": "值"},\n'
        ' "intimacy_delta": 0.5,\n'
        ' "mood_delta": {"pleasure": 0.1}}\n'
        "规则：只记录用户明确说过、且未来有用的信息；没有就返回空数组/空对象。"
        "content 用「用户……」或「TA……」开头。keyword 用 2-4 个中文词。\n"
        "只记录 TA 本人的事实、偏好、经历、约定；"
        "绝对不要记录系统机制（日记权限、记忆方式、模型参数），"
        "也不要记录「TA 怎么看这个 bot / 这个项目」这类元信息。"
        "profile 的键用简短名词（如「职业」「作息」「称呼」），不要用「对TA的……」这种句式。"
    )
    user = (
        f"已有档案：\n{prof}\n当前关系：{st['stage']}，亲密度 {st['intimacy']:.0f}\n\n"
        f"用户说：{user_text}\n你回：{bot_text}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
