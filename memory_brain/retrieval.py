"""召回：相关度 × 保持度 × 权重，受 token 预算约束。

设计取舍：
- 分区/遗忘判错时只影响排序，不做硬过滤，避免把该想起的挡掉；
- 前 3 条给全文，之后截断，总预算封顶，避免长记忆顶掉对话历史；
- 没命中关键词时（fallback_top > 0）兜底塞几条高权重记忆，解决"换说法就失忆"；
- 召回时合并近似重复（同一件事说两遍），只留分高的那条。
"""
import time

from . import config, forgetting
from .text import tokenize

REGION_BONUS = 0.6
MIN_SCORE = 0.25
FULL_ROWS = 3
CANDIDATE_LIMIT = 400
SHORT_CHARS = 14
MAX_TOKENS = 999999


def _relevance(m, q):
    """关键词命中为主，字面子串为辅。"""
    kws = set((m.get("keywords") or "").split())
    overlap = len(q & kws)
    substr = sum(1 for t in q if t in (m.get("content") or "")) if not overlap else 0
    if overlap == 0 and substr == 0:
        return 0.0
    return overlap * 2.0 + substr * 0.3


def score_rows(rows, query, now=None, regions=None, min_retention=None):
    """给候选记忆打分并按分排序。"""
    now = time.time() if now is None else now
    mr = config.get("min_retention", 0.06) if min_retention is None else min_retention
    q = tokenize(query)
    regions = set(regions or ())
    scored = []
    for r in rows:
        m = dict(r)
        rel = _relevance(m, q)
        if rel <= 0:
            continue
        score, ret = forgetting.recall_score(m, rel, now)
        m["retention"] = round(ret, 4)
        m["relevance"] = round(rel, 2)
        m["region_hit"] = bool(regions) and (m.get("region") in regions)
        if m["region_hit"]:
            score += REGION_BONUS
        if ret < mr and not forgetting.is_pinned(m):
            continue
        if score <= MIN_SCORE:
            continue
        m["_score"] = score
        scored.append(m)
    scored.sort(key=lambda x: x["_score"], reverse=True)
    return scored


def dedupe(scored, ratio=None):
    """内容高度重复的只留分数最高的那条。"""
    ratio = config.get("dedupe_ratio", 0.6) if ratio is None else ratio
    kept, kept_tokens = [], []
    for m in scored:
        tk = tokenize(m.get("content"))
        dup = False
        for other in kept_tokens:
            if not tk or not other:
                continue
            jac = len(tk & other) / len(tk | other)
            if jac >= ratio:
                dup = True
                break
        if not dup:
            kept.append(m)
            kept_tokens.append(tk)
    return kept


def fallback_rows(store, now=None, top=None):
    """没命中关键词时，挑几条最新/最重的记忆兜底。"""
    top = config.get("fallback_top", 2) if top is None else top
    if not top:
        return []
    now = time.time() if now is None else now
    rows = store.conn().execute(
        "SELECT * FROM memories WHERE COALESCE(archived,0)=0 "
        "AND superseded_by IS NULL ORDER BY weight DESC, ts DESC LIMIT 50"
    ).fetchall()
    cand = []
    for r in rows:
        m = dict(r)
        ret = forgetting.retention(m, now)
        m["retention"] = round(ret, 4)
        m["relevance"] = 0.0
        m["region_hit"] = False
        m["fallback"] = True
        m["_score"] = max(0.3, float(m.get("weight") or 1.0)) * (0.4 + 0.6 * ret)
        cand.append(m)
    cand.sort(key=lambda x: x["_score"], reverse=True)
    return cand[: int(top)]


def pick_budget(scored, limit=6, budget_tokens=320):
    """按预算取前若干条；返回 (picked, used_tokens)。"""
    picked, used = [], 0
    for i, m in enumerate(scored):
        if len(picked) >= limit:
            break
        tier = "full" if (i < FULL_ROWS and not m.get("fallback")) else "short"
        body = (m.get("content") or "") if tier == "full" else (m.get("content") or "")[:SHORT_CHARS]
        cost = forgetting.estimate_tokens(body) + 6   # 类型标签与分隔
        if picked and used + cost > budget_tokens:
            break
        m["tier"] = tier
        picked.append(m)
        used += cost
    return picked, used


def search(store, query, limit=6, budget_tokens=320, min_retention=None,
           now=None, dry_run=False, regions=None):
    """从 store 取候选，打分、去重、截预算、复习，并把统计写回 store.last_recall。"""
    now = time.time() if now is None else now
    rows = store.conn().execute(
        "SELECT * FROM memories WHERE COALESCE(archived,0)=0 "
        "AND superseded_by IS NULL "
        "ORDER BY weight DESC, ts DESC LIMIT ?", (CANDIDATE_LIMIT,)
    ).fetchall()
    scored = dedupe(score_rows(rows, query, now=now, regions=regions,
                               min_retention=min_retention))
    used_fallback = False
    if not scored:
        scored = fallback_rows(store, now=now)
        used_fallback = bool(scored)

    picked, used = pick_budget(scored, limit=limit, budget_tokens=budget_tokens)
    store.last_recall = {
        "picked": len(picked),
        "candidates": len(scored),
        "tokens": used,
        "budget": budget_tokens,
        "regions": sorted(set(regions or ())),
        "region_hits": sum(1 for m in picked if m.get("region_hit")),
        "fallback": used_fallback,
    }
    if picked and not dry_run:
        store.reinforce([m["id"] for m in picked], now)
    return picked
