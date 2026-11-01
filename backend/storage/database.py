"""SQLite (WAL + FTS5) Storage Engine for EchoMind.

Includes:
- 6 core memory tables (utterances, episodes, action_items, clues_and_wishlists, semantic_facts, daily_memos)
- FTS5 virtual table (`episodes_fts`)
- `plugin_kv` isolated namespace key-value table for Narrow PluginContext
- `effects` durable side-effect queue table with key coalescing and backoff retry support
"""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional
from backend.config import settings
from backend.storage.models import (
    ActionItem,
    ClueAndWishlist,
    DailyMemo,
    DurableEffect,
    Episode,
    SemanticFact,
    Utterance,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class StorageEngine:
    """Thread-safe SQLite WAL + FTS5 storage layer supporting core memory, plugin KV, and durable effects."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or settings.db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS utterances (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    speaker_role TEXT NOT NULL,
                    speaker_score REAL DEFAULT 0.0,
                    emotion_tag TEXT DEFAULT 'NEUTRAL',
                    acoustic_event TEXT DEFAULT 'NONE',
                    text_content TEXT NOT NULL,
                    is_context_prefix INTEGER DEFAULT 0,
                    episode_id TEXT,
                    device_id TEXT DEFAULT 'default_mic',
                    metadata_json TEXT DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_utterances_episode ON utterances(episode_id);
                CREATE INDEX IF NOT EXISTS idx_utterances_timestamp ON utterances(timestamp);

                CREATE TABLE IF NOT EXISTS episodes (
                    id TEXT PRIMARY KEY,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    category TEXT NOT NULL,
                    importance_score INTEGER DEFAULT 3,
                    host_word_ratio REAL DEFAULT 0.0,
                    is_vectorized INTEGER DEFAULT 0,
                    metadata_json TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS action_items (
                    id TEXT PRIMARY KEY,
                    episode_id TEXT,
                    content TEXT NOT NULL,
                    assignee TEXT DEFAULT 'HOST',
                    priority TEXT DEFAULT 'MEDIUM',
                    due_date TEXT,
                    status TEXT DEFAULT 'PENDING',
                    source_quote TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS clues_and_wishlists (
                    id TEXT PRIMARY KEY,
                    episode_id TEXT,
                    clue_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_quote TEXT DEFAULT '',
                    status TEXT DEFAULT 'ACTIVE',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS semantic_facts (
                    id TEXT PRIMARY KEY,
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object_value TEXT NOT NULL,
                    previous_value TEXT,
                    confidence REAL DEFAULT 0.9,
                    status TEXT DEFAULT 'ACTIVE',
                    last_updated TEXT NOT NULL,
                    source_episode_id TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_facts_subject ON semantic_facts(subject);

                CREATE TABLE IF NOT EXISTS daily_memos (
                    id TEXT PRIMARY KEY,
                    memo_date TEXT NOT NULL,
                    memo_type TEXT NOT NULL,
                    content_markdown TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(
                    episode_id UNINDEXED,
                    title,
                    summary,
                    utterances_concat
                );

                CREATE TABLE IF NOT EXISTS plugin_kv (
                    plugin_name TEXT NOT NULL,
                    kv_key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (plugin_name, kv_key)
                );

                CREATE TABLE IF NOT EXISTS effects (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    effect_key TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_run_at TEXT NOT NULL,
                    last_error TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_effects_status_due ON effects(status, next_run_at);
                CREATE INDEX IF NOT EXISTS idx_effects_kind_key ON effects(kind, effect_key);
                """
            )

    # --- 1. Utterances ---
    def insert_utterance(self, u: Utterance) -> Utterance:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO utterances (
                    id, timestamp, duration_ms, speaker_role, speaker_score,
                    emotion_tag, acoustic_event, text_content, is_context_prefix,
                    episode_id, device_id, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    u.id,
                    u.timestamp,
                    u.duration_ms,
                    u.speaker_role,
                    u.speaker_score,
                    u.emotion_tag,
                    u.acoustic_event,
                    u.text_content,
                    int(u.is_context_prefix),
                    u.episode_id,
                    u.device_id,
                    json.dumps(u.metadata_json, ensure_ascii=False),
                ),
            )
        return u

    def get_unassigned_utterances(self) -> List[Utterance]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM utterances WHERE episode_id IS NULL ORDER BY timestamp ASC"
            ).fetchall()
        return [self._row_to_utterance(r) for r in rows]

    def get_utterances_by_episode(self, episode_id: str) -> List[Utterance]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM utterances WHERE episode_id = ? ORDER BY timestamp ASC",
                (episode_id,),
            ).fetchall()
        return [self._row_to_utterance(r) for r in rows]

    def assign_utterances_to_episode(self, utterance_ids: List[str], episode_id: str) -> None:
        if not utterance_ids:
            return
        placeholders = ",".join("?" for _ in utterance_ids)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE utterances SET episode_id = ? WHERE id IN ({placeholders})",
                [episode_id, *utterance_ids],
            )

    def _row_to_utterance(self, r: sqlite3.Row) -> Utterance:
        return Utterance(
            id=r["id"],
            timestamp=r["timestamp"],
            duration_ms=r["duration_ms"],
            speaker_role=r["speaker_role"],
            speaker_score=r["speaker_score"],
            emotion_tag=r["emotion_tag"],
            acoustic_event=r["acoustic_event"],
            text_content=r["text_content"],
            is_context_prefix=bool(r["is_context_prefix"]),
            episode_id=r["episode_id"],
            device_id=r["device_id"],
            metadata_json=json.loads(r["metadata_json"] or "{}"),
        )

    # --- 2. Episodes & FTS5 ---
    def insert_episode(self, ep: Episode, utterances_concat: str = "") -> Episode:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO episodes (
                    id, start_time, end_time, title, summary, category,
                    importance_score, host_word_ratio, is_vectorized, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ep.id,
                    ep.start_time,
                    ep.end_time,
                    ep.title,
                    ep.summary,
                    ep.category,
                    ep.importance_score,
                    ep.host_word_ratio,
                    int(ep.is_vectorized),
                    json.dumps(ep.metadata_json, ensure_ascii=False),
                    ep.created_at,
                ),
            )
            if ep.category != "DISCARDED":
                conn.execute(
                    "INSERT INTO episodes_fts (episode_id, title, summary, utterances_concat) VALUES (?, ?, ?, ?)",
                    (ep.id, ep.title, ep.summary, utterances_concat),
                )
        return ep

    def list_episodes(
        self,
        category: Optional[str] = None,
        include_discarded: bool = False,
        limit: int = 50,
    ) -> List[Episode]:
        query = "SELECT * FROM episodes WHERE 1=1"
        params: List[Any] = []
        if not include_discarded:
            query += " AND category != 'DISCARDED'"
        if category:
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY start_time DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_episode(r) for r in rows]

    def get_episode(self, episode_id: str) -> Optional[Episode]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM episodes WHERE id = ?", (episode_id,)).fetchone()
        return self._row_to_episode(row) if row else None

    def search_episodes_fts(self, query_str: str, limit: int = 10) -> List[Episode]:
        """Full-text search using SQLite FTS5 + LIKE fallback for Chinese substrings."""
        clean_q = query_str.strip()
        if not clean_q:
            return self.list_episodes(limit=limit)

        results_map: Dict[str, Episode] = {}
        with self._connect() as conn:
            try:
                fts_rows = conn.execute(
                    """
                    SELECT e.* FROM episodes_fts f
                    JOIN episodes e ON e.id = f.episode_id
                    WHERE episodes_fts MATCH ?
                    ORDER BY rank LIMIT ?
                    """,
                    (f'"{clean_q}"', limit),
                ).fetchall()
                for r in fts_rows:
                    ep = self._row_to_episode(r)
                    results_map[ep.id] = ep
            except sqlite3.OperationalError:
                pass

            like_pat = f"%{clean_q}%"
            like_rows = conn.execute(
                """
                SELECT DISTINCT e.* FROM episodes e
                LEFT JOIN utterances u ON u.episode_id = e.id
                WHERE e.category != 'DISCARDED'
                  AND (e.title LIKE ? OR e.summary LIKE ? OR u.text_content LIKE ?)
                ORDER BY e.start_time DESC LIMIT ?
                """,
                (like_pat, like_pat, like_pat, limit),
            ).fetchall()
            for r in like_rows:
                ep = self._row_to_episode(r)
                if ep.id not in results_map:
                    results_map[ep.id] = ep

        return list(results_map.values())[:limit]

    def _row_to_episode(self, r: sqlite3.Row) -> Episode:
        return Episode(
            id=r["id"],
            start_time=r["start_time"],
            end_time=r["end_time"],
            title=r["title"],
            summary=r["summary"],
            category=r["category"],
            importance_score=r["importance_score"],
            host_word_ratio=r["host_word_ratio"],
            is_vectorized=bool(r["is_vectorized"]),
            metadata_json=json.loads(r["metadata_json"] or "{}"),
            created_at=r["created_at"],
        )

    # --- 3. Action Items (To-Do) ---
    def insert_action_item(self, item: ActionItem) -> ActionItem:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO action_items (
                    id, episode_id, content, assignee, priority, due_date, status, source_quote, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.id,
                    item.episode_id,
                    item.content,
                    item.assignee,
                    item.priority,
                    item.due_date,
                    item.status,
                    item.source_quote,
                    item.created_at,
                ),
            )
        return item

    def list_action_items(
        self,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        episode_id: Optional[str] = None,
    ) -> List[ActionItem]:
        query = "SELECT * FROM action_items WHERE 1=1"
        params: List[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if assignee:
            query += " AND assignee = ?"
            params.append(assignee)
        if episode_id:
            query += " AND episode_id = ?"
            params.append(episode_id)
        query += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [ActionItem(**dict(r)) for r in rows]

    def update_action_item_status(self, item_id: str, status: str) -> Optional[ActionItem]:
        with self._connect() as conn:
            conn.execute("UPDATE action_items SET status = ? WHERE id = ?", (status, item_id))
            row = conn.execute("SELECT * FROM action_items WHERE id = ?", (item_id,)).fetchone()
        return ActionItem(**dict(row)) if row else None

    # --- 4. Clues & Wishlists (MemoMind Feature) ---
    def insert_clue(self, clue: ClueAndWishlist) -> ClueAndWishlist:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO clues_and_wishlists (
                    id, episode_id, clue_type, content, source_quote, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    clue.id,
                    clue.episode_id,
                    clue.clue_type,
                    clue.content,
                    clue.source_quote,
                    clue.status,
                    clue.created_at,
                ),
            )
        return clue

    def list_clues(self, clue_type: Optional[str] = None, status: Optional[str] = "ACTIVE") -> List[ClueAndWishlist]:
        query = "SELECT * FROM clues_and_wishlists WHERE 1=1"
        params: List[Any] = []
        if clue_type:
            query += " AND clue_type = ?"
            params.append(clue_type)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [ClueAndWishlist(**dict(r)) for r in rows]

    def update_clue_status(self, clue_id: str, status: str) -> Optional[ClueAndWishlist]:
        with self._connect() as conn:
            conn.execute("UPDATE clues_and_wishlists SET status = ? WHERE id = ?", (status, clue_id))
            row = conn.execute("SELECT * FROM clues_and_wishlists WHERE id = ?", (clue_id,)).fetchone()
        return ClueAndWishlist(**dict(row)) if row else None

    # --- 5. Semantic Facts (Mem0-style Entity Graph) ---
    def upsert_semantic_fact(
        self,
        subject: str,
        predicate: str,
        object_value: str,
        confidence: float = 0.9,
        source_episode_id: Optional[str] = None,
        existing_fact_id: Optional[str] = None,
    ) -> SemanticFact:
        """Insert or update an entity fact, preserving `previous_value` when updated."""
        with self._connect() as conn:
            row = None
            if existing_fact_id:
                row = conn.execute(
                    "SELECT * FROM semantic_facts WHERE id = ?", (existing_fact_id,)
                ).fetchone()
            if not row:
                row = conn.execute(
                    "SELECT * FROM semantic_facts WHERE subject = ? AND predicate = ? AND status = 'ACTIVE'",
                    (subject, predicate),
                ).fetchone()

            now_iso = SemanticFact(subject=subject, predicate=predicate, object_value=object_value).last_updated
            if row:
                prev_val = row["object_value"]
                fact_id = row["id"]
                if prev_val != object_value:
                    conn.execute(
                        """
                        UPDATE semantic_facts
                        SET object_value = ?, previous_value = ?, confidence = ?,
                            last_updated = ?, source_episode_id = ?
                        WHERE id = ?
                        """,
                        (object_value, prev_val, confidence, now_iso, source_episode_id, fact_id),
                    )
                updated_row = conn.execute(
                    "SELECT * FROM semantic_facts WHERE id = ?", (fact_id,)
                ).fetchone()
                return SemanticFact(**dict(updated_row))
            else:
                new_fact = SemanticFact(
                    subject=subject,
                    predicate=predicate,
                    object_value=object_value,
                    confidence=confidence,
                    source_episode_id=source_episode_id,
                )
                conn.execute(
                    """
                    INSERT INTO semantic_facts (
                        id, subject, predicate, object_value, previous_value,
                        confidence, status, last_updated, source_episode_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_fact.id,
                        new_fact.subject,
                        new_fact.predicate,
                        new_fact.object_value,
                        new_fact.previous_value,
                        new_fact.confidence,
                        new_fact.status,
                        new_fact.last_updated,
                        new_fact.source_episode_id,
                    ),
                )
                return new_fact

    def list_semantic_facts(self, subject: Optional[str] = None) -> List[SemanticFact]:
        query = "SELECT * FROM semantic_facts WHERE status = 'ACTIVE'"
        params: List[Any] = []
        if subject:
            query += " AND (subject LIKE ? OR object_value LIKE ?)"
            params.extend([f"%{subject}%", f"%{subject}%"])
        query += " ORDER BY last_updated DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [SemanticFact(**dict(r)) for r in rows]

    # --- 6. Daily Memos (Morning Brief / Evening Review) ---
    def insert_daily_memo(self, memo: DailyMemo) -> DailyMemo:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO daily_memos (id, memo_date, memo_type, content_markdown, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (memo.id, memo.memo_date, memo.memo_type, memo.content_markdown, memo.created_at),
            )
        return memo

    def list_daily_memos(self, memo_type: Optional[str] = None, limit: int = 14) -> List[DailyMemo]:
        query = "SELECT * FROM daily_memos WHERE 1=1"
        params: List[Any] = []
        if memo_type:
            query += " AND memo_type = ?"
            params.append(memo_type)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [DailyMemo(**dict(r)) for r in rows]

    # --- 7. Plugin Scoped Key-Value Store (Narrow Context) ---
    def get_plugin_kv(self, plugin_name: str, key: str, default: Any = None) -> Any:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value_json FROM plugin_kv WHERE plugin_name = ? AND kv_key = ?",
                (plugin_name, key),
            ).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value_json"])
        except Exception:
            return default

    def set_plugin_kv(self, plugin_name: str, key: str, value: Any) -> None:
        now = _utc_now_iso()
        val_str = json.dumps(value, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO plugin_kv (plugin_name, kv_key, value_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(plugin_name, kv_key)
                DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at
                """,
                (plugin_name, key, val_str, now),
            )

    def delete_plugin_kv(self, plugin_name: str, key: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM plugin_kv WHERE plugin_name = ? AND kv_key = ?",
                (plugin_name, key),
            )

    def list_plugin_kv_keys(self, plugin_name: str) -> List[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT kv_key FROM plugin_kv WHERE plugin_name = ? ORDER BY kv_key ASC",
                (plugin_name,),
            ).fetchall()
        return [r["kv_key"] for r in rows]

    # --- 8. Durable Effects Queue (dsh-superagent Coalescing & Backoff) ---
    def enqueue_effect(self, kind: str, effect_key: str, payload: Dict[str, Any]) -> DurableEffect:
        """Enqueue a side-effect. If a PENDING row for `(kind, effect_key)` exists, coalesce its payload."""
        now = _utc_now_iso()
        payload_str = json.dumps(payload, ensure_ascii=False)
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM effects WHERE kind = ? AND effect_key = ? AND status = 'PENDING'",
                (kind, effect_key),
            ).fetchone()
            if existing:
                eff_id = existing["id"]
                conn.execute(
                    """
                    UPDATE effects
                    SET payload_json = ?, next_run_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (payload_str, now, now, eff_id),
                )
                row = conn.execute("SELECT * FROM effects WHERE id = ?", (eff_id,)).fetchone()
                return self._row_to_effect(row)

            eff = DurableEffect(
                kind=kind,
                effect_key=effect_key,
                payload_json=payload,
                next_run_at=now,
                updated_at=now,
            )
            conn.execute(
                """
                INSERT INTO effects (
                    id, kind, effect_key, payload_json, status, attempts, next_run_at, last_error, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    eff.id,
                    eff.kind,
                    eff.effect_key,
                    payload_str,
                    eff.status,
                    eff.attempts,
                    eff.next_run_at,
                    eff.last_error,
                    eff.updated_at,
                ),
            )
            return eff

    def list_due_effects(self, now_iso: Optional[str] = None, limit: int = 20) -> List[DurableEffect]:
        now = now_iso or _utc_now_iso()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM effects
                WHERE status = 'PENDING' AND next_run_at <= ?
                ORDER BY next_run_at ASC, updated_at ASC LIMIT ?
                """,
                (now, limit),
            ).fetchall()
        return [self._row_to_effect(r) for r in rows]

    def mark_effect_done(self, effect_id: str) -> None:
        now = _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                "UPDATE effects SET status = 'DONE', updated_at = ? WHERE id = ?",
                (now, effect_id),
            )

    def record_effect_failure(
        self,
        effect_id: str,
        error_msg: str,
        max_attempts: int = 3,
    ) -> Optional[DurableEffect]:
        """Increment attempts and apply exponential backoff (2^attempts sec up to 60s), or mark FAILED."""
        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM effects WHERE id = ?", (effect_id,)).fetchone()
            if not row:
                return None
            attempts = int(row["attempts"]) + 1
            if attempts >= max_attempts:
                status = "FAILED"
                next_run_iso = row["next_run_at"]
            else:
                status = "PENDING"
                backoff_sec = min(60, 2 ** attempts)
                next_run_iso = (now_dt + timedelta(seconds=backoff_sec)).isoformat()

            conn.execute(
                """
                UPDATE effects
                SET status = ?, attempts = ?, next_run_at = ?, last_error = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, attempts, next_run_iso, error_msg, now_iso, effect_id),
            )
            updated = conn.execute("SELECT * FROM effects WHERE id = ?", (effect_id,)).fetchone()
            return self._row_to_effect(updated) if updated else None

    def list_effects(self, status: Optional[str] = None, limit: int = 50) -> List[DurableEffect]:
        query = "SELECT * FROM effects WHERE 1=1"
        params: List[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_effect(r) for r in rows]

    def _row_to_effect(self, r: sqlite3.Row) -> DurableEffect:
        return DurableEffect(
            id=r["id"],
            kind=r["kind"],
            effect_key=r["effect_key"],
            payload_json=json.loads(r["payload_json"] or "{}"),
            status=r["status"],
            attempts=int(r["attempts"]),
            next_run_at=r["next_run_at"],
            last_error=r["last_error"],
            updated_at=r["updated_at"],
        )


_default_storage: Optional[StorageEngine] = None


def get_storage() -> StorageEngine:
    global _default_storage
    if _default_storage is None:
        _default_storage = StorageEngine()
    return _default_storage
