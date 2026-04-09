from uuid import uuid4
from app.obj.types import ChatMessage


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