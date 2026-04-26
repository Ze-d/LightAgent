"""Checkpoint mechanism for agent run recovery."""
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import threading

from app.obj.types import ChatMessage


@dataclass
class Checkpoint:
    step: int
    history: list[ChatMessage]
    agent_state: dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)


class CheckpointManager:
    _checkpoints: dict[str, list[Checkpoint]]
    _lock: threading.Lock

    def __init__(self) -> None:
        self._checkpoints = {}
        self._lock = threading.Lock()

    def save(
        self,
        session_id: str,
        step: int,
        history: list[ChatMessage],
        agent_state: dict[str, Any],
    ) -> None:
        checkpoint = Checkpoint(
            step=step,
            history=deepcopy(history),
            agent_state=deepcopy(agent_state),
            timestamp=datetime.now(),
        )
        with self._lock:
            if session_id not in self._checkpoints:
                self._checkpoints[session_id] = []
            self._checkpoints[session_id].append(checkpoint)

    def load(self, session_id: str) -> Checkpoint | None:
        with self._lock:
            checkpoints = self._checkpoints.get(session_id, [])
            if not checkpoints:
                return None
            return deepcopy(checkpoints[-1])

    def get_latest_step(self, session_id: str) -> int:
        checkpoint = self.load(session_id)
        return checkpoint.step if checkpoint else 0

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._checkpoints.pop(session_id, None)

    def has_checkpoint(self, session_id: str) -> bool:
        with self._lock:
            return bool(self._checkpoints.get(session_id))
