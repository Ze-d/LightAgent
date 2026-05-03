"""Shared SQLite state backend for sessions, context, checkpoints, and A2A."""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any, Iterator


def dumps_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def loads_json(value: str | None, default: Any = None) -> Any:
    if value is None:
        return default
    return json.loads(value)


class SQLiteStateBackend:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._lock = RLock()
        self._ensure_schema()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        with self._lock:
            with self.connect() as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS sessions (
                        session_id TEXT PRIMARY KEY,
                        history_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS context_states (
                        session_id TEXT PRIMARY KEY,
                        channel TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        provider_mode TEXT NOT NULL,
                        external_context_id TEXT,
                        openai_conversation_id TEXT,
                        last_response_id TEXT,
                        history_version INTEGER NOT NULL DEFAULT 0,
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

                    CREATE UNIQUE INDEX IF NOT EXISTS idx_context_external
                        ON context_states(channel, external_context_id)
                        WHERE external_context_id IS NOT NULL;

                    CREATE TABLE IF NOT EXISTS checkpoints (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        step INTEGER NOT NULL,
                        phase TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        checkpoint_json TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_checkpoints_session_id
                        ON checkpoints(session_id, id);

                    CREATE TABLE IF NOT EXISTS a2a_tasks (
                        task_id TEXT PRIMARY KEY,
                        context_id TEXT NOT NULL,
                        state TEXT NOT NULL,
                        task_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_a2a_tasks_context_state
                        ON a2a_tasks(context_id, state);

                    CREATE TABLE IF NOT EXISTS a2a_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_id TEXT NOT NULL,
                        event_json TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_a2a_events_task_id
                        ON a2a_events(task_id, id);
                    """
                )
