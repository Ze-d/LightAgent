from uuid import uuid4
from app.obj.types import ChatMessage

from abc import ABC, abstractmethod
from app.obj.types import ChatMessage



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

    def create(self, initial_history: list[ChatMessage]) -> str:
        session_id = str(uuid4())
        self._store[session_id] = list(initial_history)
        return session_id

    def load(self, session_id: str) -> list[ChatMessage] | None:
        history = self._store.get(session_id)
        if history is None:
            return None
        return list(history)

    def save(self, session_id: str, history: list[ChatMessage]) -> None:
        self._store[session_id] = list(history)

    def append(self, session_id: str, message: ChatMessage) -> None:
        if session_id not in self._store:
            raise ValueError(f"Session not found: {session_id}")
        self._store[session_id].append(message)

    def exists(self, session_id: str) -> bool:
        return session_id in self._store

    def delete(self, session_id: str) -> None:
        if session_id in self._store:
            del self._store[session_id]
class SessionManager:
    def __init__(self):
        self._store: dict[str, list[ChatMessage]] = {}
    #  创建新会话
    def create(self, initial_history: list[ChatMessage]) -> str:
        session_id = str(uuid4())
        self._store[session_id] = initial_history
        return session_id
    # 加载会话历史
    def load(self, session_id: str) -> list[ChatMessage] | None:
        return self._store.get(session_id)
    # 保存会话历史
    def save(self, session_id: str, history: list[ChatMessage]) -> None:
        self._store[session_id] = history
    # 添加消息到会话历史
    def append(self, session_id: str, message: ChatMessage) -> None:
        history = self._store.get(session_id)
        if history is None:
            raise ValueError(f"Session not found: {session_id}")
        history.append(message)