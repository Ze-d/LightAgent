"""Cooperative cancellation primitives for long-running agent work."""
from __future__ import annotations

from threading import Event, Lock


DEFAULT_CANCEL_REASON = "Task canceled by client."


class RunnerCancelledError(RuntimeError):
    def __init__(self, reason: str = DEFAULT_CANCEL_REASON) -> None:
        super().__init__(reason)
        self.reason = reason


class CancellationToken:
    """Thread-safe cooperative cancellation token.

    The token does not forcibly stop a running LLM or tool call. Callers check
    it at safe boundaries and stop before starting more work.
    """

    def __init__(self) -> None:
        self._event = Event()
        self._lock = Lock()
        self._reason = DEFAULT_CANCEL_REASON

    @property
    def reason(self) -> str:
        with self._lock:
            return self._reason

    def cancel(self, reason: str = DEFAULT_CANCEL_REASON) -> None:
        with self._lock:
            self._reason = reason or DEFAULT_CANCEL_REASON
            self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled():
            raise RunnerCancelledError(self.reason)
