"""Context state model and in-memory store.

This layer separates the app-level session id from provider conversation
state. It is intentionally storage-agnostic so a SQLite or Redis store can
replace the in-memory implementation without changing API orchestration.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import threading
from typing import Any, Literal
from uuid import uuid4

from app.core.sqlite_state import SQLiteStateBackend, dumps_json, loads_json


ContextChannel = Literal["chat", "a2a"]
ProviderMode = Literal[
    "manual",
    "openai_previous_response",
    "openai_conversation",
]


@dataclass
class ContextState:
    session_id: str
    channel: ContextChannel
    provider: str = "openai_compatible"
    provider_mode: ProviderMode = "manual"
    external_context_id: str | None = None
    openai_conversation_id: str | None = None
    last_response_id: str | None = None
    history_version: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


class ContextStateNotFoundError(KeyError):
    pass


class BaseContextStore(ABC):
    @abstractmethod
    def create(
        self,
        *,
        channel: ContextChannel,
        session_id: str | None = None,
        external_context_id: str | None = None,
        provider: str = "openai_compatible",
        provider_mode: ProviderMode = "manual",
        metadata: dict[str, Any] | None = None,
    ) -> ContextState:
        pass

    @abstractmethod
    def get(self, session_id: str) -> ContextState | None:
        pass

    @abstractmethod
    def require(self, session_id: str) -> ContextState:
        pass

    @abstractmethod
    def get_by_external_context(
        self,
        *,
        channel: ContextChannel,
        external_context_id: str,
    ) -> ContextState | None:
        pass

    @abstractmethod
    def get_or_create_for_external_context(
        self,
        *,
        channel: ContextChannel,
        external_context_id: str,
        provider: str = "openai_compatible",
        provider_mode: ProviderMode = "manual",
        metadata: dict[str, Any] | None = None,
    ) -> ContextState:
        pass

    @abstractmethod
    def bump_history_version(self, session_id: str) -> ContextState:
        pass

    @abstractmethod
    def update_provider_state(
        self,
        session_id: str,
        *,
        provider: str | None = None,
        provider_mode: ProviderMode | None = None,
        openai_conversation_id: str | None = None,
        last_response_id: str | None = None,
    ) -> ContextState:
        pass

    @abstractmethod
    def delete(self, session_id: str) -> None:
        pass


class InMemoryContextStore(BaseContextStore):
    def __init__(self) -> None:
        self._states: dict[str, ContextState] = {}
        self._external_index: dict[tuple[ContextChannel, str], str] = {}
        self._lock = threading.Lock()

    def create(
        self,
        *,
        channel: ContextChannel,
        session_id: str | None = None,
        external_context_id: str | None = None,
        provider: str = "openai_compatible",
        provider_mode: ProviderMode = "manual",
        metadata: dict[str, Any] | None = None,
    ) -> ContextState:
        resolved_session_id = session_id or self._new_session_id(
            channel=channel,
            external_context_id=external_context_id,
        )
        now = datetime.now()
        state = ContextState(
            session_id=resolved_session_id,
            channel=channel,
            provider=provider,
            provider_mode=provider_mode,
            external_context_id=external_context_id,
            metadata=dict(metadata or {}),
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._states[resolved_session_id] = deepcopy(state)
            if external_context_id is not None:
                self._external_index[
                    (channel, external_context_id)
                ] = resolved_session_id
        return deepcopy(state)

    def get(self, session_id: str) -> ContextState | None:
        with self._lock:
            state = self._states.get(session_id)
            return deepcopy(state) if state is not None else None

    def require(self, session_id: str) -> ContextState:
        state = self.get(session_id)
        if state is None:
            raise ContextStateNotFoundError(session_id)
        return state

    def get_by_external_context(
        self,
        *,
        channel: ContextChannel,
        external_context_id: str,
    ) -> ContextState | None:
        with self._lock:
            session_id = self._external_index.get((channel, external_context_id))
            if session_id is None:
                return None
            state = self._states.get(session_id)
            return deepcopy(state) if state is not None else None

    def get_or_create_for_external_context(
        self,
        *,
        channel: ContextChannel,
        external_context_id: str,
        provider: str = "openai_compatible",
        provider_mode: ProviderMode = "manual",
        metadata: dict[str, Any] | None = None,
    ) -> ContextState:
        existing = self.get_by_external_context(
            channel=channel,
            external_context_id=external_context_id,
        )
        if existing is not None:
            return existing
        return self.create(
            channel=channel,
            external_context_id=external_context_id,
            provider=provider,
            provider_mode=provider_mode,
            metadata=metadata,
        )

    def bump_history_version(self, session_id: str) -> ContextState:
        with self._lock:
            state = self._states.get(session_id)
            if state is None:
                raise ContextStateNotFoundError(session_id)
            state.history_version += 1
            state.updated_at = datetime.now()
            return deepcopy(state)

    def update_provider_state(
        self,
        session_id: str,
        *,
        provider: str | None = None,
        provider_mode: ProviderMode | None = None,
        openai_conversation_id: str | None = None,
        last_response_id: str | None = None,
    ) -> ContextState:
        with self._lock:
            state = self._states.get(session_id)
            if state is None:
                raise ContextStateNotFoundError(session_id)
            if provider is not None:
                state.provider = provider
            if provider_mode is not None:
                state.provider_mode = provider_mode
            if openai_conversation_id is not None:
                state.openai_conversation_id = openai_conversation_id
            if last_response_id is not None:
                state.last_response_id = last_response_id
            state.updated_at = datetime.now()
            return deepcopy(state)

    def delete(self, session_id: str) -> None:
        with self._lock:
            state = self._states.pop(session_id, None)
            if state and state.external_context_id is not None:
                self._external_index.pop(
                    (state.channel, state.external_context_id),
                    None,
                )

    def _new_session_id(
        self,
        *,
        channel: ContextChannel,
        external_context_id: str | None,
    ) -> str:
        if external_context_id is None:
            return str(uuid4())
        return f"{channel}:{external_context_id}"


class SQLiteContextStore(BaseContextStore):
    def __init__(self, db_path: str | Path) -> None:
        self._backend = SQLiteStateBackend(db_path)
        self._lock = threading.RLock()

    def create(
        self,
        *,
        channel: ContextChannel,
        session_id: str | None = None,
        external_context_id: str | None = None,
        provider: str = "openai_compatible",
        provider_mode: ProviderMode = "manual",
        metadata: dict[str, Any] | None = None,
    ) -> ContextState:
        resolved_session_id = session_id or self._new_session_id(
            channel=channel,
            external_context_id=external_context_id,
        )
        now = datetime.now()
        state = ContextState(
            session_id=resolved_session_id,
            channel=channel,
            provider=provider,
            provider_mode=provider_mode,
            external_context_id=external_context_id,
            metadata=dict(metadata or {}),
            created_at=now,
            updated_at=now,
        )
        with self._lock, self._backend.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO context_states (
                    session_id,
                    channel,
                    provider,
                    provider_mode,
                    external_context_id,
                    openai_conversation_id,
                    last_response_id,
                    history_version,
                    metadata_json,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._state_to_row(state),
            )
        return deepcopy(state)

    def get(self, session_id: str) -> ContextState | None:
        with self._lock, self._backend.connect() as conn:
            row = conn.execute(
                "SELECT * FROM context_states WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            return self._row_to_state(row) if row else None

    def require(self, session_id: str) -> ContextState:
        state = self.get(session_id)
        if state is None:
            raise ContextStateNotFoundError(session_id)
        return state

    def get_by_external_context(
        self,
        *,
        channel: ContextChannel,
        external_context_id: str,
    ) -> ContextState | None:
        with self._lock, self._backend.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM context_states
                WHERE channel = ? AND external_context_id = ?
                """,
                (channel, external_context_id),
            ).fetchone()
            return self._row_to_state(row) if row else None

    def get_or_create_for_external_context(
        self,
        *,
        channel: ContextChannel,
        external_context_id: str,
        provider: str = "openai_compatible",
        provider_mode: ProviderMode = "manual",
        metadata: dict[str, Any] | None = None,
    ) -> ContextState:
        existing = self.get_by_external_context(
            channel=channel,
            external_context_id=external_context_id,
        )
        if existing is not None:
            return existing
        return self.create(
            channel=channel,
            external_context_id=external_context_id,
            provider=provider,
            provider_mode=provider_mode,
            metadata=metadata,
        )

    def bump_history_version(self, session_id: str) -> ContextState:
        now = datetime.now().isoformat(timespec="seconds")
        with self._lock, self._backend.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE context_states
                SET history_version = history_version + 1,
                    updated_at = ?
                WHERE session_id = ?
                """,
                (now, session_id),
            )
            if cursor.rowcount == 0:
                raise ContextStateNotFoundError(session_id)
        return self.require(session_id)

    def update_provider_state(
        self,
        session_id: str,
        *,
        provider: str | None = None,
        provider_mode: ProviderMode | None = None,
        openai_conversation_id: str | None = None,
        last_response_id: str | None = None,
    ) -> ContextState:
        state = self.require(session_id)
        if provider is not None:
            state.provider = provider
        if provider_mode is not None:
            state.provider_mode = provider_mode
        if openai_conversation_id is not None:
            state.openai_conversation_id = openai_conversation_id
        if last_response_id is not None:
            state.last_response_id = last_response_id
        state.updated_at = datetime.now()
        with self._lock, self._backend.connect() as conn:
            conn.execute(
                """
                UPDATE context_states
                SET provider = ?,
                    provider_mode = ?,
                    openai_conversation_id = ?,
                    last_response_id = ?,
                    updated_at = ?
                WHERE session_id = ?
                """,
                (
                    state.provider,
                    state.provider_mode,
                    state.openai_conversation_id,
                    state.last_response_id,
                    state.updated_at.isoformat(timespec="seconds"),
                    session_id,
                ),
            )
        return deepcopy(state)

    def delete(self, session_id: str) -> None:
        with self._lock, self._backend.connect() as conn:
            conn.execute(
                "DELETE FROM context_states WHERE session_id = ?",
                (session_id,),
            )

    def _new_session_id(
        self,
        *,
        channel: ContextChannel,
        external_context_id: str | None,
    ) -> str:
        if external_context_id is None:
            return str(uuid4())
        return f"{channel}:{external_context_id}"

    def _state_to_row(self, state: ContextState) -> tuple[Any, ...]:
        return (
            state.session_id,
            state.channel,
            state.provider,
            state.provider_mode,
            state.external_context_id,
            state.openai_conversation_id,
            state.last_response_id,
            state.history_version,
            dumps_json(state.metadata),
            state.created_at.isoformat(timespec="seconds"),
            state.updated_at.isoformat(timespec="seconds"),
        )

    def _row_to_state(self, row: Any) -> ContextState:
        return ContextState(
            session_id=row["session_id"],
            channel=row["channel"],
            provider=row["provider"],
            provider_mode=row["provider_mode"],
            external_context_id=row["external_context_id"],
            openai_conversation_id=row["openai_conversation_id"],
            last_response_id=row["last_response_id"],
            history_version=row["history_version"],
            metadata=loads_json(row["metadata_json"], default={}),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
