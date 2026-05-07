"""SQLite-backed vector memory store with cosine similarity search."""
from __future__ import annotations

import json
import math
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.configs.logger import logger
from app.memory.models import MemoryEntry, MemorySearchResult


class VectorMemoryStore:
    """Persistent vector store using SQLite for storage and numpy-less cosine similarity.

    Design decisions:
    - Zero extra dependencies beyond stdlib + sqlite3 (numpy is optional for speed).
    - Brute-force O(n) search is fine for < 10k entries (personal agent scale).
    - File-system content (.memory/*.md) remains the source of truth; this is an index.
    """

    def __init__(
        self,
        db_path: str | Path,
        *,
        embedding_dim: int | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.embedding_dim = embedding_dim
        self._lock = threading.RLock()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            conn = sqlite3.connect(str(self.db_path), timeout=30.0)
            try:
                conn.execute("PRAGMA foreign_keys = ON")
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS memory_entries (
                        id TEXT PRIMARY KEY,
                        scope TEXT NOT NULL,
                        session_id TEXT,
                        content TEXT NOT NULL,
                        embedding_json TEXT,
                        importance REAL NOT NULL DEFAULT 0.5,
                        access_count INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        metadata_json TEXT NOT NULL DEFAULT '{}'
                    );

                    CREATE INDEX IF NOT EXISTS idx_mem_scope
                        ON memory_entries(scope);
                    CREATE INDEX IF NOT EXISTS idx_mem_session
                        ON memory_entries(session_id);
                    CREATE INDEX IF NOT EXISTS idx_mem_importance
                        ON memory_entries(importance DESC);
                    """
                )
                conn.commit()
            finally:
                conn.close()

    # -- CRUD ---------------------------------------------------------------

    def add(self, entry: MemoryEntry) -> str:
        """Insert or replace a memory entry. Returns the entry id."""
        now = datetime.now().isoformat(timespec="seconds")
        if not entry.id:
            entry.id = uuid.uuid4().hex
        entry.updated_at = now
        if not entry.created_at:
            entry.created_at = now

        embedding_json = (
            json.dumps(entry.embedding, ensure_ascii=False)
            if entry.embedding
            else None
        )

        with self._lock:
            conn = sqlite3.connect(str(self.db_path), timeout=30.0)
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO memory_entries
                        (id, scope, session_id, content, embedding_json,
                         importance, access_count, created_at, updated_at, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.id, entry.scope, entry.session_id, entry.content,
                        embedding_json, entry.importance, entry.access_count,
                        entry.created_at, entry.updated_at,
                        json.dumps(entry.metadata, ensure_ascii=False, default=str),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

        return entry.id

    def get(self, entry_id: str) -> MemoryEntry | None:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM memory_entries WHERE id = ?", (entry_id,)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_entry(row)
        finally:
            conn.close()

    def delete(self, entry_id: str) -> None:
        with self._lock:
            conn = sqlite3.connect(str(self.db_path), timeout=30.0)
            try:
                conn.execute("DELETE FROM memory_entries WHERE id = ?", (entry_id,))
                conn.commit()
            finally:
                conn.close()

    def update_importance(self, entry_id: str, delta: float) -> None:
        with self._lock:
            conn = sqlite3.connect(str(self.db_path), timeout=30.0)
            try:
                row = conn.execute(
                    "SELECT importance, access_count FROM memory_entries WHERE id = ?",
                    (entry_id,),
                ).fetchone()
                if row is None:
                    return
                new_importance = max(0.0, min(1.0, row[0] + delta))
                new_count = row[1] + 1
                now = datetime.now().isoformat(timespec="seconds")
                conn.execute(
                    "UPDATE memory_entries SET importance = ?, access_count = ?, updated_at = ? WHERE id = ?",
                    (new_importance, new_count, now, entry_id),
                )
                conn.commit()
            finally:
                conn.close()

    # -- Search -------------------------------------------------------------

    def search(
        self,
        query_embedding: list[float],
        *,
        scope: str | None = None,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[MemorySearchResult]:
        """Semantic search by embedding vector using cosine similarity."""
        entries = self._load_entries(scope=scope)
        if not entries:
            return []

        scored: list[MemorySearchResult] = []
        for entry in entries:
            if entry.embedding is None:
                continue
            score = self._cosine_similarity(query_embedding, entry.embedding)
            if score >= min_score:
                scored.append(MemorySearchResult(entry=entry, score=score))
                # Bump importance slightly on hit
                self.update_importance(entry.id, 0.01)

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]

    def search_by_text(
        self,
        query: str,
        *,
        scope: str | None = None,
        top_k: int = 5,
    ) -> list[MemoryEntry]:
        """Fallback: SQL LIKE search when embeddings are unavailable."""
        entries = self._load_entries(scope=scope)
        if not entries:
            return []

        query_lower = query.lower()
        scored: list[tuple[MemoryEntry, int]] = []
        for entry in entries:
            content_lower = entry.content.lower()
            score = content_lower.count(query_lower)
            if score > 0:
                scored.append((entry, score))
        scored.sort(key=lambda r: r[1], reverse=True)
        return [e for e, _ in scored[:top_k]]

    # -- Bulk operations ----------------------------------------------------

    def count(self, scope: str | None = None) -> int:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        try:
            if scope:
                row = conn.execute(
                    "SELECT COUNT(*) FROM memory_entries WHERE scope = ?", (scope,)
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM memory_entries").fetchone()
            return row[0] if row else 0
        finally:
            conn.close()

    def _load_entries(self, scope: str | None = None) -> list[MemoryEntry]:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            if scope:
                rows = conn.execute(
                    "SELECT * FROM memory_entries WHERE scope = ? ORDER BY importance DESC",
                    (scope,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM memory_entries ORDER BY importance DESC"
                ).fetchall()
            return [self._row_to_entry(r) for r in rows]
        finally:
            conn.close()

    def list_entries(
        self,
        scope: str | None = None,
        session_id: str | None = None,
        limit: int = 100,
    ) -> list[MemoryEntry]:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            conditions: list[str] = []
            params: list[str] = []
            if scope:
                conditions.append("scope = ?")
                params.append(scope)
            if session_id:
                conditions.append("session_id = ?")
                params.append(session_id)
            where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
            sql = f"SELECT * FROM memory_entries{where} ORDER BY updated_at DESC LIMIT ?"
            params.append(str(limit))
            rows = conn.execute(sql, tuple(params)).fetchall()
            return [self._row_to_entry(r) for r in rows]
        finally:
            conn.close()

    # -- Consolidation helpers (used by Phase 3) ---------------------------

    def find_duplicates(
        self,
        threshold: float = 0.92,
        scope: str = "session",
    ) -> list[tuple[MemoryEntry, MemoryEntry, float]]:
        """Find pairs of entries with cosine similarity above threshold."""
        entries = self._load_entries(scope=scope)
        pairs: list[tuple[MemoryEntry, MemoryEntry, float]] = []
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                a, b = entries[i], entries[j]
                if a.embedding and b.embedding:
                    sim = self._cosine_similarity(a.embedding, b.embedding)
                    if sim >= threshold:
                        pairs.append((a, b, sim))
        return pairs

    def merge_entries(self, keep_id: str, discard_id: str) -> None:
        keep = self.get(keep_id)
        discard = self.get(discard_id)
        if not keep or not discard:
            return
        # Accumulate access counts
        keep.access_count += discard.access_count
        keep.importance = max(keep.importance, discard.importance)
        keep.updated_at = datetime.now().isoformat(timespec="seconds")
        self.delete(discard_id)
        self.add(keep)

    # -- Internal helpers ---------------------------------------------------

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> MemoryEntry:
        emb_json = row["embedding_json"]
        embedding = json.loads(emb_json) if emb_json else None
        return MemoryEntry(
            id=row["id"],
            scope=row["scope"],
            session_id=row["session_id"],
            content=row["content"],
            embedding=embedding,
            importance=row["importance"],
            access_count=row["access_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=json.loads(row["metadata_json"] or "{}"),
        )

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        if len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)
