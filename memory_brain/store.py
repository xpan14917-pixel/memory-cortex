"""记忆存储：消息、记忆、档案、状态、日记、主动记录。

设计：每个线程一个连接（sqlite3 连接不跨线程共享），WAL 模式。
"""
import json
import pathlib
import sqlite3
import threading
import time

from . import brainmap
from . import forgetting
from .text import tokenize as _tokenize

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  mood TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(ts);

CREATE TABLE IF NOT EXISTS memories(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  kind TEXT NOT NULL,
  content TEXT NOT NULL,
  keywords TEXT NOT NULL,
  weight REAL DEFAULT 1.0,
  hits INTEGER DEFAULT 0,
  last_used REAL DEFAULT 0,
  stability REAL,
  archived INTEGER DEFAULT 0,
  last_review REAL,
  region TEXT,
  source TEXT,
  superseded_by INTEGER,
  embedding BLOB,
  embed_model TEXT
);

CREATE TABLE IF NOT EXISTS profile(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  confidence REAL DEFAULT 0.6,
  updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS state(
  k TEXT PRIMARY KEY,
  v TEXT NOT NULL,
  updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS diary(
  date TEXT PRIMARY KEY,
  mood TEXT,
  summary TEXT,
  highlights TEXT,
  next_day TEXT,
  created_at REAL
);

CREATE TABLE IF NOT EXISTS proactive_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  trigger TEXT,
  content TEXT,
  replied INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS thoughts(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  kind TEXT NOT NULL,
  content TEXT NOT NULL,
  weight REAL DEFAULT 1.0,
  used INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_thoughts_ts ON thoughts(ts);
"""


def tokenize(text):
    """兼容旧调用：实现已移到 memory_brain.text。"""
    return _tokenize(text)


class Store:
    def __init__(self, path):
        self.path = str(path)
        pathlib.Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_lock = threading.Lock()
        self._init()

    # ---------- 基础设施 ----------
    def conn(self):
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=15)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = c
        return c

    def close(self):
        """关掉当前线程的连接（测试/脚本里用完记得调）。"""
        c = getattr(self._local, "conn", None)
        if c is not None:
            try:
                c.close()
            finally:
                self._local.conn = None

    def _init(self):
        with self._init_lock:
            self.conn().executescript(SCHEMA)
            self.conn().commit()
            self._migrate()

    # 老库升级：补上遗忘曲线 / 分区 / 溯源需要的列，并回填已有记忆
    _MEM_COLUMNS = (
        ("stability", "ALTER TABLE memories ADD COLUMN stability REAL"),
        ("archived", "ALTER TABLE memories ADD COLUMN archived INTEGER DEFAULT 0"),
        ("last_review", "ALTER TABLE memories ADD COLUMN last_review REAL"),
        ("region", "ALTER TABLE memories ADD COLUMN region TEXT"),
        ("source", "ALTER TABLE memories ADD COLUMN source TEXT"),
        ("superseded_by", "ALTER TABLE memories ADD COLUMN superseded_by INTEGER"),
        ("embedding", "ALTER TABLE memories ADD COLUMN embedding BLOB"),
        ("embed_model", "ALTER TABLE memories ADD COLUMN embed_model TEXT"),
    )

    def _migrate(self):
        c = self.conn()
        try:
            cols = {r["name"] for r in c.execute("PRAGMA table_info(memories)")}
        except sqlite3.DatabaseError:
            return
        added = False
        for name, sql in self._MEM_COLUMNS:
            if name not in cols:
                c.execute(sql)
                added = True
        if added:
            c.commit()
        rows = c.execute(
            "SELECT id, kind, weight, hits FROM memories WHERE stability IS NULL"
        ).fetchall()
        for r in rows:
            c.execute(
                "UPDATE memories SET stability=? WHERE id=?",
                (forgetting.stability(r["kind"], r["weight"], r["hits"]), r["id"]),
            )
        if rows:
            c.commit()
        # 回填分区
        need_region = c.execute(
            "SELECT id, kind, content, keywords FROM memories WHERE region IS NULL OR region=''"
        ).fetchall()
        for r in need_region:
            c.execute(
                "UPDATE memories SET region=? WHERE id=?",
                (brainmap.classify(r["kind"], r["content"], r["keywords"]), r["id"]),
            )
        if need_region:
            c.commit()

    def _exec(self, sql, args=()):
        c = self.conn()
        cur = c.execute(sql, args)
        c.commit()
        return cur

    # ---------- 消息 ----------
    def add_message(self, role, content, mood=None):
        cur = self._exec(
            "INSERT INTO messages(ts, role, content, mood) VALUES(?,?,?,?)",
            (time.time(), role, content, mood),
        )
        return cur.lastrowid

    def recent_messages(self, limit=20):
        rows = self.conn().execute(
            "SELECT ts, role, content FROM messages ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def last_user_message(self):
        r = self.conn().execute(
            "SELECT ts, content FROM messages WHERE role='user' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(r) if r else None

    def last_bot_message(self):
        r = self.conn().execute(
            "SELECT ts, content FROM messages WHERE role='bot' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(r) if r else None

    def bot_count_after_last_user(self):
        r = self.conn().execute(
            "SELECT COUNT(*) c FROM messages WHERE role='bot' AND ts > "
            "(SELECT COALESCE(MAX(ts),0) FROM messages WHERE role='user')"
        ).fetchone()
        return r["c"]

    def last_message(self):
        r = self.conn().execute(
            "SELECT ts, role, content FROM messages ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(r) if r else None

    def unanswered_user(self, max_age=900):
        """最后一条是用户消息、且之后没有 bot 回复时返回它（用于重启补答）。"""
        last = self.last_message()
        if last and last["role"] == "user" and time.time() - last["ts"] <= max_age:
            return last
        return None

    def count_since(self, role, since_ts):
        r = self.conn().execute(
            "SELECT COUNT(*) c FROM messages WHERE role=? AND ts>=?", (role, since_ts)
        ).fetchone()
        return r["c"]

    # ---------- 记忆 ----------
    def _embed(self, text):
        """按需生成向量；未启用或出错时返回 (None, None)，绝不影响写入。"""
        try:
            from . import vector
            emb = vector.get_embedder()
            if not emb.enabled:
                return None, None
            vecs = emb.embed([text])
            if not vecs or not vecs[0]:
                return None, None
            return vector.pack(vecs[0]), getattr(emb, "name", "")
        except Exception:  # noqa: BLE001
            return None, None

    def add_memory(self, kind, content, keywords=None, weight=1.0, source=None):
        """写一条记忆。source 用来溯源，例如 "msg:1234" / "manual" / "diary"。"""
        content = (content or "").strip()
        if not content:
            return None
        kws = keywords or sorted(tokenize(content))[:12]
        if isinstance(kws, (list, tuple, set)):
            kws = " ".join(str(k) for k in kws)
        blob, model = self._embed(content)

        # 去重：已有记忆和这条高度重合时，合并而不是新增
        tok = tokenize(content)
        if tok:
            rows = self.conn().execute(
                "SELECT id, content, weight FROM memories ORDER BY id DESC LIMIT 500"
            ).fetchall()
            for r in rows:
                old = tokenize(r["content"])
                if not old:
                    continue
                jac = len(tok & old) / len(tok | old)
                if jac >= 0.8:
                    merged = len(content) > len(r["content"]) and content or r["content"]
                    new_weight = min(3.0, max(float(r["weight"]), float(weight)) + 0.2)
                    new_s = forgetting.stability(kind, new_weight, 0)
                    mtok = tokenize(merged)
                    mblob, mmodel = (blob, model) if merged == content else self._embed(merged)
                    self._exec(
                        "UPDATE memories SET content=?, keywords=?, weight=?, ts=?, "
                        "stability=?, region=?, source=COALESCE(?, source), "
                        "embedding=COALESCE(?, embedding), embed_model=COALESCE(?, embed_model) "
                        "WHERE id=?",
                        (merged, kws, new_weight, time.time(), new_s,
                         brainmap.classify(kind, merged, mtok), source,
                         mblob, mmodel, r["id"]),
                    )
                    return r["id"]

        cur = self._exec(
            "INSERT INTO memories(ts, kind, content, keywords, weight, stability, region, "
            "source, embedding, embed_model) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (time.time(), kind, content, kws, float(weight),
             forgetting.stability(kind, weight, 0),
             brainmap.classify(kind, content, kws), source, blob, model),
        )
        return cur.lastrowid

    def backfill_embeddings(self, limit=5000):
        """给还没有向量的旧记忆补向量（启用向量召回后跑一次）。"""
        rows = self.conn().execute(
            "SELECT id, content FROM memories WHERE embedding IS NULL LIMIT ?",
            (int(limit),)).fetchall()
        n = 0
        for r in rows:
            blob, model = self._embed(r["content"])
            if blob is None:
                continue
            self._exec("UPDATE memories SET embedding=?, embed_model=? WHERE id=?",
                       (blob, model, r["id"]))
            n += 1
        return n

    def supersede(self, old_id, new_id=None):
        """标记旧记忆已被更正：不再召回，但保留可查。"""
        self._exec("UPDATE memories SET superseded_by=? WHERE id=?", (0 if new_id is None else int(new_id), int(old_id)))
        return True

    def forget(self, mem_id):
        """手动遗忘（归档）。"""
        self._exec("UPDATE memories SET archived=1 WHERE id=?", (int(mem_id),))
        return True

    def restore(self, mem_id):
        """把归档/更正的记忆恢复回来。"""
        self._exec(
            "UPDATE memories SET archived=0, superseded_by=NULL WHERE id=?", (int(mem_id),))
        return True

    def get_memory(self, mem_id):
        r = self.conn().execute("SELECT * FROM memories WHERE id=?", (int(mem_id),)).fetchone()
        return dict(r) if r else None

    def search_memories(self, query, limit=6, budget_tokens=320, min_retention=0.06,
                        now=None, dry_run=False, regions=None):
        """按「相关度 × 保持度 × 权重」召回，并受 token 预算约束。

        实现在 memory_brain/retrieval.py；这里只是把 store 自己交给它。
        返回的每条多两个键：retention（保持度）、tier（full/short）。
        """
        from . import retrieval
        return retrieval.search(
            self, query, limit=limit, budget_tokens=budget_tokens,
            min_retention=min_retention, now=now, dry_run=dry_run, regions=regions,
        )

    def region_counts(self):
        """每个分区有多少条、其中多少已归档。"""
        rows = self.conn().execute(
            "SELECT COALESCE(region, '') AS r, COUNT(*) AS n, "
            "SUM(COALESCE(archived,0)) AS a FROM memories GROUP BY r"
        ).fetchall()
        counts, archived = {}, 0
        for r in rows:
            counts[r["r"] or brainmap.DEFAULT_REGION] = counts.get(
                r["r"] or brainmap.DEFAULT_REGION, 0
            ) + r["n"]
            archived += r["a"] or 0
        return counts, archived

    def reinforce(self, ids, now=None, boost=0.25):
        """复习一次：hits+1、last_used 更新、稳定度变大（曲线变平）。"""
        now = time.time() if now is None else now
        ids = [int(i) for i in (ids or [])]
        if not ids:
            return 0
        rows = self.conn().execute(
            "SELECT * FROM memories WHERE id IN (%s)" % ",".join("?" * len(ids)), ids
        ).fetchall()
        for r in rows:
            m = dict(r)
            self._exec(
                "UPDATE memories SET hits=COALESCE(hits,0)+1, last_used=?, "
                "stability=?, last_review=? WHERE id=?",
                (now, forgetting.reinforced(m, boost), now, m["id"]),
            )
        return len(rows)

    def decay_pass(self, now=None, min_retention=0.05, min_days=90, dry_run=False):
        """每日一次：补算稳定度，把"确实淡忘了"的记忆归档（不删，只是不进 prompt）。"""
        now = time.time() if now is None else now
        rows = self.conn().execute(
            "SELECT * FROM memories WHERE COALESCE(archived,0)=0"
        ).fetchall()
        to_archive = []
        for r in rows:
            m = dict(r)
            if not m.get("stability"):
                m["stability"] = forgetting.stability(
                    m.get("kind"), m.get("weight"), m.get("hits")
                )
                if not dry_run:
                    self._exec(
                        "UPDATE memories SET stability=? WHERE id=?",
                        (m["stability"], m["id"]),
                    )
            if forgetting.should_archive(m, now, min_retention, min_days):
                to_archive.append(m)
        if to_archive and not dry_run:
            ids = [m["id"] for m in to_archive]
            self._exec(
                "UPDATE memories SET archived=1 WHERE id IN (%s)"
                % ",".join("?" * len(ids)),
                ids,
            )
        return {
            "checked": len(rows),
            "archived": len(to_archive),
            "ids": [m["id"] for m in to_archive],
        }

    def memory_stats(self, now=None):
        now = time.time() if now is None else now
        rows = self.conn().execute("SELECT * FROM memories").fetchall()
        total = len(rows)
        archived = superseded = 0
        rs = []
        for r in rows:
            m = dict(r)
            if m.get("archived"):
                archived += 1
            if m.get("superseded_by") is not None:
                superseded += 1
            rs.append(forgetting.retention(m, now))
        return {
            "total": total,
            "archived": archived,
            "superseded": superseded,
            "active": total - archived - superseded,
            "avg_retention": round(sum(rs) / len(rs), 3) if rs else 0.0,
            "fading": sum(1 for x in rs if x < 0.3),
        }

    def all_memories(self, limit=300):
        rows = self.conn().execute(
            "SELECT * FROM memories ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ---------- 档案 ----------
    def upsert_profile(self, key, value, confidence=0.6):
        self._exec(
            "INSERT INTO profile(key, value, confidence, updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
            "confidence=excluded.confidence, updated_at=excluded.updated_at",
            (str(key), str(value), float(confidence), time.time()),
        )

    def profile_dict(self):
        rows = self.conn().execute("SELECT key, value FROM profile").fetchall()
        return {r["key"]: r["value"] for r in rows}

    def profile_ranked(self, limit=10):
        """按置信度取前 N 条画像，用于塞进 prompt（避免 20 条全灌）。"""
        rows = self.conn().execute(
            "SELECT key, value FROM profile ORDER BY confidence DESC, updated_at DESC "
            "LIMIT ?", (int(limit),)
        ).fetchall()
        return {r["key"]: r["value"] for r in rows}

    # ---------- 状态 ----------
    def get_state(self, key, default=None):
        r = self.conn().execute("SELECT v FROM state WHERE k=?", (key,)).fetchone()
        if not r:
            return default
        try:
            return json.loads(r["v"])
        except Exception:  # noqa: BLE001
            return r["v"]

    def set_state(self, key, value):
        self._exec(
            "INSERT INTO state(k, v, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(k) DO UPDATE SET v=excluded.v, updated_at=excluded.updated_at",
            (key, json.dumps(value, ensure_ascii=False), time.time()),
        )

    def get_float(self, key, default=0.0):
        v = self.get_state(key, default)
        try:
            return float(v)
        except (TypeError, ValueError):
            return float(default)

    # ---------- 日记 ----------
    def save_diary(self, date, mood, summary, highlights, next_day):
        self._exec(
            "INSERT INTO diary(date, mood, summary, highlights, next_day, created_at) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(date) DO UPDATE SET mood=excluded.mood, "
            "summary=excluded.summary, highlights=excluded.highlights, next_day=excluded.next_day",
            (date, mood, summary, highlights, next_day, time.time()),
        )

    def get_diary(self, date):
        r = self.conn().execute("SELECT * FROM diary WHERE date=?", (date,)).fetchone()
        return dict(r) if r else None

    def latest_diary(self):
        r = self.conn().execute("SELECT * FROM diary ORDER BY date DESC LIMIT 1").fetchone()
        return dict(r) if r else None

    # ---------- 主动记录 ----------
    def log_proactive(self, trigger, content):
        cur = self._exec(
            "INSERT INTO proactive_log(ts, trigger, content) VALUES(?,?,?)",
            (time.time(), trigger, content),
        )
        return cur.lastrowid

    def mark_proactive_replied(self):
        self._exec("UPDATE proactive_log SET replied=1 WHERE id IN "
                   "(SELECT id FROM proactive_log ORDER BY id DESC LIMIT 1)")

    def count_proactive_today(self, day_start_ts):
        r = self.conn().execute(
            "SELECT COUNT(*) c FROM proactive_log WHERE ts>=?", (day_start_ts,)
        ).fetchone()
        return r["c"]

    def last_proactive(self):
        r = self.conn().execute(
            "SELECT ts, content FROM proactive_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(r) if r else None

    # ---------- 想法（内在生活） ----------
    def add_thought(self, kind, content, weight=1.0):
        content = (content or "").strip()
        if not content:
            return None
        cur = self._exec(
            "INSERT INTO thoughts(ts, kind, content, weight) VALUES(?,?,?,?)",
            (time.time(), kind, content, float(weight)),
        )
        return cur.lastrowid

    def recent_thoughts(self, limit=10, unused_only=False, days=7):
        since = time.time() - days * 86400
        sql = "SELECT * FROM thoughts WHERE ts>=?"
        if unused_only:
            sql += " AND used=0"
        sql += " ORDER BY ts DESC LIMIT ?"
        rows = self.conn().execute(sql, (since, limit)).fetchall()
        return [dict(r) for r in rows]

    def mark_thought_used(self, tid):
        self._exec("UPDATE thoughts SET used=1 WHERE id=?", (tid,))

    def count_thoughts_today(self, day_start_ts, kind=None):
        if kind:
            r = self.conn().execute(
                "SELECT COUNT(*) c FROM thoughts WHERE ts>=? AND kind=?",
                (day_start_ts, kind),
            ).fetchone()
        else:
            r = self.conn().execute(
                "SELECT COUNT(*) c FROM thoughts WHERE ts>=?", (day_start_ts,)
            ).fetchone()
        return r["c"]

    def latest_thought(self):
        r = self.conn().execute(
            "SELECT * FROM thoughts ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(r) if r else None

