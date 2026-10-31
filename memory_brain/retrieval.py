"""召回：关键词 × 向量（可选）→ RRF 融合 → 相关度 × 保持度 × 权重 → token 预算。

设计取舍：
- 分区/遗忘判错时只影响排序，不做硬过滤，避免把该想起的挡掉；
- 前 3 条给全文，之后截断，总预算封顶，避免长记忆顶掉对话历史；
- 没命中关键词时（fallback_top > 0）兜底塞几条高权重记忆，解决"换说法就失忆"；
- 召回时合并近似重复（同一件事说两遍），只留分高的那条；
- 向量召回默认关闭；开启后用 RRF 只融合"排名"，不混用两路的分数量纲。
"""
import time

from . import config, forgetting, vector
from .text import tokenize

REGION_BONUS = 0.6
MIN_SCORE = 0.25
FULL_ROWS = 3
CANDIDATE_LIMIT = 400
RECENT_LIMIT = 200
SHORT_CHARS = 14
VECTOR_SCALE = 2.0


def _relevance(m, q):
    """关键词命中为主，字面子串为辅。"""
    kws = set((m.get("keywords") or "").split())
    overlap = len(q & kws)
    substr = sum(1 for t in q if t in (m.get("content") or "")) if not overlap else 0
    if overlap == 0 and substr == 0:
        return 0.0
    return overlap * 2.0 + substr * 0.3


def _ranks(scores):
    """把 {id: score} 按分降序转成 {id: rank}（0 起）。"""
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return {mid: i for i, (mid, _) in enumerate(ordered)}


def hybrid_relevance(rows, query, now=None):
    """返回 {memory_id: 有效相关度}。

    - 向量关闭 / 不可用：直接用关键词相关度（与旧版完全一致）。
    - 向量开启：两路各自排名 → RRF 融合 → 归一化到"关键词命中一次"的量级。
    """
    q = tokenize(query)
    kw = {}
    for r in rows:
        m = dict(r)
        rel = _relevance(m, q)
        if rel > 0:
            kw[m["id"]] = rel

    emb = vector.get_embedder()
    if not emb.enabled:
        return kw

    qvec = None
    try:
        vecs = emb.embed([query])
        if vecs:
            qvec = vecs[0]
    except Exception:  # noqa: BLE001  服务不可用时退回关键词
        qvec = None
    if not qvec:
        return kw

    min_sim = float(config.get("vector_min_sim", 0.3) or 0.0)
    sims = {}
    for r in rows:
        m = dict(r)
        mv = vector.unpack(m.get("embedding"))
        if not mv:
            continue
        sim = vector.cosine(qvec, mv)
        if sim >= min_sim:
            sims[m["id"]] = sim
    if not sims:
        return kw

    k = float(config.get("rrf_k", 60) or 60)
    w = float(config.get("vector_weight", 0.5) or 0.0)
    w = max(0.0, min(1.0, w))
    kw_rank = _ranks(kw)
    vec_rank = _ranks(sims)

    fused = {}
    for mid in set(kw_rank) | set(vec_rank):
        s = 0.0
        if mid in kw_rank:
            s += (1.0 - w) / (k + kw_rank[mid])
        if mid in vec_rank:
            s += w / (k + vec_rank[mid])
        fused[mid] = s

    top = max(fused.values()) or 1.0
    # 归一化后放大到 2.0：与"关键词命中一次"同量级，后面的 MIN_SCORE 照旧生效
    return {mid: (v / top) * VECTOR_SCALE for mid, v in fused.items()}


def score_rows(rows, query, now=None, regions=None, min_retention=None):
    """给候选记忆打分并按分排序。"""
    now = time.time() if now is None else now
    mr = config.get("min_retention", 0.06) if min_retention is None else min_retention
    regions = set(regions or ())
    rel_map = hybrid_relevance(rows, query, now=now)

    scored = []
    for r in rows:
        m = dict(r)
        rel = rel_map.get(m["id"], 0.0)
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
    """按预算取前若干条；返回 (picked, used_tokens)。

    第一条也要守预算：单条超长的记忆会被截断，而不是挤掉后面所有内容。
    """
    picked, used = [], 0
    for i, m in enumerate(scored):
        if len(picked) >= limit:
            break
        tier = "full" if (i < FULL_ROWS and not m.get("fallback")) else "short"
        body = (m.get("content") or "") if tier == "full" else (m.get("content") or "")[:SHORT_CHARS]
        cost = forgetting.estimate_tokens(body) + 6   # 类型标签与分隔
        if used + cost > budget_tokens:
            if picked:
                break
            # 第一条就超预算：按剩余预算折算成字数硬截断
            room = max(1, int((budget_tokens - 6) * 1.6))
            if room < 1:
                break
            body = body[:room]
            cost = forgetting.estimate_tokens(body) + 6
        m["tier"] = tier
        m["content_shown"] = body
        picked.append(m)
        used += cost
    return picked, used


def _candidates(store):
    """候选池 = 高权重池 ∪ 最新池。

    只按权重取会漏掉"低权重但很新且精确命中"的记忆，所以补一条按时间取的，
    两个池按 id 去重合并。
    """
    sql = ("SELECT * FROM memories WHERE COALESCE(archived,0)=0 "
           "AND superseded_by IS NULL ")
    by_weight = store.conn().execute(
        sql + "ORDER BY weight DESC, ts DESC LIMIT ?", (CANDIDATE_LIMIT,)).fetchall()
    by_recent = store.conn().execute(
        sql + "ORDER BY ts DESC LIMIT ?", (RECENT_LIMIT,)).fetchall()
    seen, merged = set(), []
    for r in list(by_weight) + list(by_recent):
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        merged.append(r)
    return merged


def search(store, query, limit=6, budget_tokens=320, min_retention=None,
           now=None, dry_run=False, regions=None):
    """从 store 取候选，打分、去重、截预算、复习。

    非 dry_run 时把统计写回 store.last_recall（复习也会落库）。
    """
    now = time.time() if now is None else now
    rows = _candidates(store)
    scored = dedupe(score_rows(rows, query, now=now, regions=regions,
                               min_retention=min_retention))
    used_fallback = False
    if not scored:
        scored = fallback_rows(store, now=now)
        used_fallback = bool(scored)

    picked, used = pick_budget(scored, limit=limit, budget_tokens=budget_tokens)
    if not dry_run:
        store.last_recall = {
            "picked": len(picked),
            "candidates": len(scored),
            "tokens": used,
            "budget": budget_tokens,
            "regions": sorted(set(regions or ())),
            "region_hits": sum(1 for m in picked if m.get("region_hit")),
            "fallback": used_fallback,
            "vector": vector.get_embedder().enabled,
        }
        if picked:
            store.reinforce([m["id"] for m in picked], now)
    return picked
