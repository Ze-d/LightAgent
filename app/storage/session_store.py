from uuid import uuid4
from app.obj.types import ChatMessage


class InMemorySessionStore:
    def __init__(self):
        self._store: dict[str, list[ChatMessage]] = {}

    def create_session(self, initial_history: list[ChatMessage]) -> str:
        session_id = str(uuid4())
        self._store[session_id] = initial_history
        return session_id

    def get_history(self, session_id: str) -> list[ChatMessage] | None:
        return self._store.get(session_id)

    def save_history(self, session_id: str, history: list[ChatMessage]) -> None:
        self._store[session_id] = history

    def exists(self, session_id: str) -> bool:
        return session_id in self._store