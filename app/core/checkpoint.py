"""Checkpoint mechanism for agent run recovery."""
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
import threading

from app.obj.types import FunctionCallOutput, SideEffectPolicy
from app.core.sqlite_state import SQLiteStateBackend, dumps_json, loads_json


CheckpointPhase = Literal[
    "before_llm",
    "tool_requested",
    "tool_partial_done",
    "tool_output_ready",
    "completed",
    "failed",
]
ToolExecutionStatus = Literal[
    "pending",
    "running",
    "succeeded",
    "failed",
    "unknown",
]


@dataclass
class ToolExecutionRecord:
    call_id: str
    tool_name: str
    arguments: dict[str, Any]
    arguments_hash: str
    status: ToolExecutionStatus = "pending"
    output: str | None = None
    error: str | None = None
    side_effect_policy: SideEffectPolicy = "read_only"
    idempotency_key: str | None = None


@dataclass
class Checkpoint:
    step: int
    history: list[dict[str, Any]]
    agent_state: dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    version: int = 2
    session_id: str = ""
    run_id: str = ""
    phase: CheckpointPhase = "tool_output_ready"
    llm_input: list[dict[str, Any]] | str | None = None
    tool_calls: list[ToolExecutionRecord] = field(default_factory=list)
    function_outputs: list[FunctionCallOutput] = field(default_factory=list)
    completed_call_ids: list[str] = field(default_factory=list)
    error: str | None = None

    def __post_init__(self) -> None:
        if self.llm_input is None:
            self.llm_input = deepcopy(self.history)
        if not self.completed_call_ids:
            self.completed_call_ids = [
                record.call_id
                for record in self.tool_calls
                if record.status in {"succeeded", "failed"}
            ]


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
        history: list[dict[str, Any]],
        agent_state: dict[str, Any],
        *,
        phase: CheckpointPhase = "tool_output_ready",
        llm_input: list[dict[str, Any]] | str | None = None,
        tool_calls: list[ToolExecutionRecord] | None = None,
        function_outputs: list[FunctionCallOutput] | None = None,
        run_id: str = "",
        error: str | None = None,
    ) -> None:
        resolved_tool_calls = deepcopy(tool_calls or [])
        resolved_function_outputs = deepcopy(
            function_outputs
            if function_outputs is not None
            else [
                item for item in history
                if isinstance(item, dict)
                and item.get("type") == "function_call_output"
            ]
        )
        checkpoint = Checkpoint(
            step=step,
            history=deepcopy(history),
            agent_state=deepcopy(agent_state),
            timestamp=datetime.now(),
            session_id=session_id,
            run_id=run_id,
            phase=phase,
            llm_input=deepcopy(llm_input if llm_input is not None else history),
            tool_calls=resolved_tool_calls,
            function_outputs=resolved_function_outputs,
            completed_call_ids=[
                record.call_id
                for record in resolved_tool_calls
                if record.status in {"succeeded", "failed"}
            ],
            error=error,
        )
        self.save_checkpoint(session_id, checkpoint)

    def save_checkpoint(self, session_id: str, checkpoint: Checkpoint) -> None:
        with self._lock:
            if session_id not in self._checkpoints:
                self._checkpoints[session_id] = []
            self._checkpoints[session_id].append(deepcopy(checkpoint))

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


class SQLiteCheckpointManager:
    def __init__(self, db_path: str | Path) -> None:
        self._backend = SQLiteStateBackend(db_path)
        self._lock = threading.Lock()

    def save(
        self,
        session_id: str,
        step: int,
        history: list[dict[str, Any]],
        agent_state: dict[str, Any],
        *,
        phase: CheckpointPhase = "tool_output_ready",
        llm_input: list[dict[str, Any]] | str | None = None,
        tool_calls: list[ToolExecutionRecord] | None = None,
        function_outputs: list[FunctionCallOutput] | None = None,
        run_id: str = "",
        error: str | None = None,
    ) -> None:
        resolved_tool_calls = deepcopy(tool_calls or [])
        resolved_function_outputs = deepcopy(
            function_outputs
            if function_outputs is not None
            else [
                item for item in history
                if isinstance(item, dict)
                and item.get("type") == "function_call_output"
            ]
        )
        checkpoint = Checkpoint(
            step=step,
            history=deepcopy(history),
            agent_state=deepcopy(agent_state),
            timestamp=datetime.now(),
            session_id=session_id,
            run_id=run_id,
            phase=phase,
            llm_input=deepcopy(llm_input if llm_input is not None else history),
            tool_calls=resolved_tool_calls,
            function_outputs=resolved_function_outputs,
            completed_call_ids=[
                record.call_id
                for record in resolved_tool_calls
                if record.status in {"succeeded", "failed"}
            ],
            error=error,
        )
        self.save_checkpoint(session_id, checkpoint)

    def save_checkpoint(self, session_id: str, checkpoint: Checkpoint) -> None:
        stored = deepcopy(checkpoint)
        stored.session_id = session_id
        payload = self._checkpoint_to_payload(stored)
        with self._lock, self._backend.connect() as conn:
            conn.execute(
                """
                INSERT INTO checkpoints (
                    session_id, step, phase, timestamp, checkpoint_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    stored.step,
                    stored.phase,
                    stored.timestamp.isoformat(timespec="seconds"),
                    dumps_json(payload),
                ),
            )

    def load(self, session_id: str) -> Checkpoint | None:
        with self._lock, self._backend.connect() as conn:
            row = conn.execute(
                """
                SELECT checkpoint_json FROM checkpoints
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            return self._payload_to_checkpoint(
                loads_json(row["checkpoint_json"], default={})
            )

    def get_latest_step(self, session_id: str) -> int:
        checkpoint = self.load(session_id)
        return checkpoint.step if checkpoint else 0

    def clear(self, session_id: str) -> None:
        with self._lock, self._backend.connect() as conn:
            conn.execute(
                "DELETE FROM checkpoints WHERE session_id = ?",
                (session_id,),
            )

    def has_checkpoint(self, session_id: str) -> bool:
        with self._lock, self._backend.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM checkpoints WHERE session_id = ? LIMIT 1",
                (session_id,),
            ).fetchone()
            return row is not None

    def _checkpoint_to_payload(self, checkpoint: Checkpoint) -> dict[str, Any]:
        return {
            "step": checkpoint.step,
            "history": deepcopy(checkpoint.history),
            "agent_state": deepcopy(checkpoint.agent_state),
            "timestamp": checkpoint.timestamp.isoformat(timespec="seconds"),
            "version": checkpoint.version,
            "session_id": checkpoint.session_id,
            "run_id": checkpoint.run_id,
            "phase": checkpoint.phase,
            "llm_input": deepcopy(checkpoint.llm_input),
            "tool_calls": [asdict(record) for record in checkpoint.tool_calls],
            "function_outputs": deepcopy(checkpoint.function_outputs),
            "completed_call_ids": list(checkpoint.completed_call_ids),
            "error": checkpoint.error,
        }

    def _payload_to_checkpoint(self, payload: dict[str, Any]) -> Checkpoint:
        return Checkpoint(
            step=payload["step"],
            history=payload["history"],
            agent_state=payload["agent_state"],
            timestamp=datetime.fromisoformat(payload["timestamp"]),
            version=payload.get("version", 2),
            session_id=payload.get("session_id", ""),
            run_id=payload.get("run_id", ""),
            phase=payload.get("phase", "tool_output_ready"),
            llm_input=payload.get("llm_input"),
            tool_calls=[
                ToolExecutionRecord(**record)
                for record in payload.get("tool_calls", [])
            ],
            function_outputs=payload.get("function_outputs", []),
            completed_call_ids=payload.get("completed_call_ids", []),
            error=payload.get("error"),
        )
