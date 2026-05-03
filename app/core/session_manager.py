import threading
from uuid import uuid4
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from app.obj.types import ChatMessage
from app.core.sqlite_state import SQLiteStateBackend, dumps_json, loads_json


class BaseSessionManager(ABC):
    @abstractmethod
    def create(self, initial_history: list[ChatMessage]) -> str:
        pass

    @abstractmethod
    def load(self, session_id: str) -> list[ChatMessage] | None:
        pass

    @abstractmethod
    def save(self, session_id: str, history: list[ChatMessage]) -> None:
        pass

    @abstractmethod
    def append(self, session_id: str, message: ChatMessage) -> None:
        pass

    @abstractmethod
    def exists(self, session_id: str) -> bool:
        pass

    @abstractmethod
    def delete(self, session_id: str) -> None:
        pass


class InMemorySessionManager(BaseSessionManager):
    def __init__(self):
        self._store: dict[str, list[ChatMessage]] = {}
        self._lock = threading.Lock()

    def create(self, initial_history: list[ChatMessage]) -> str:
        session_id = str(uuid4())
        with self._lock:
            self._store[session_id] = list(initial_history)
        return session_id

    def load(self, session_id: str) -> list[ChatMessage] | None:
        with self._lock:
            history = self._store.get(session_id)
            if history is None:
                return None
            return list(history)

    def save(self, session_id: str, history: list[ChatMessage]) -> None:
        with self._lock:
            self._store[session_id] = list(history)

    def append(self, session_id: str, message: ChatMessage) -> None:
        with self._lock:
            if session_id not in self._store:
                raise ValueError(f"Session not found: {session_id}")
            self._store[session_id].append(message)

    def exists(self, session_id: str) -> bool:
        with self._lock:
            return session_id in self._store

    def delete(self, session_id: str) -> None:
        with self._lock:
            if session_id in self._store:
                del self._store[session_id]


class SQLiteSessionManager(BaseSessionManager):
    def __init__(self, db_path: str | Path):
        self._backend = SQLiteStateBackend(db_path)
        self._lock = threading.RLock()

    def create(self, initial_history: list[ChatMessage]) -> str:
        session_id = str(uuid4())
        self.save(session_id, initial_history)
        return session_id

    def load(self, session_id: str) -> list[ChatMessage] | None:
        with self._lock, self._backend.connect() as conn:
            row = conn.execute(
                "SELECT history_json FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            return loads_json(row["history_json"], default=[])

    def save(self, session_id: str, history: list[ChatMessage]) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._lock, self._backend.connect() as conn:
            existing = conn.execute(
                "SELECT created_at FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            created_at = existing["created_at"] if existing else now
            conn.execute(
                """
                INSERT OR REPLACE INTO sessions (
                    session_id, history_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?)
                """,
                (session_id, dumps_json(history), created_at, now),
            )

    def append(self, session_id: str, message: ChatMessage) -> None:
        with self._lock:
            history = self.load(session_id)
            if history is None:
                raise ValueError(f"Session not found: {session_id}")
            history.append(message)
            self.save(session_id, history)

    def exists(self, session_id: str) -> bool:
        with self._lock, self._backend.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            return row is not None

    def delete(self, session_id: str) -> None:
        with self._lock, self._backend.connect() as conn:
            conn.execute(
                "DELETE FROM sessions WHERE session_id = ?",
                (session_id,),
            )
