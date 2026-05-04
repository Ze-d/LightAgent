"""Checkpoint mechanism for agent run recovery."""
import hashlib
import json
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


@dataclass
class ResumeContext:
    """Execution context prepared from a checkpoint for the runner to resume."""
    run_id: str
    start_step: int
    current_input: list[dict[str, Any]] | str
    resume_tool_records: list[ToolExecutionRecord] | None
    collected_events: list[dict[str, Any]]


class CheckpointOrchestrator:
    """Encapsulates checkpoint save, load, clear, and resume logic.

    This is a collaborator for AgentRunner — not middleware. The runner
    maintains control of the execution loop and calls the orchestrator at
    the appropriate phases. The orchestrator is responsible for *what* to
    persist and *how* to interpret a stored checkpoint for resumption.
    """

    def __init__(self, manager: CheckpointManager | SQLiteCheckpointManager) -> None:
        self._manager = manager

    # ── static helpers (moved from AgentRunner) ──────────────────────────

    @staticmethod
    def history_from_input(current_input: list[dict[str, Any]] | str) -> list[dict[str, Any]]:
        if isinstance(current_input, list):
            return deepcopy(current_input)
        return [{"role": "user", "content": current_input}]

    @staticmethod
    def hash_tool_arguments(tool_name: str, arguments: dict[str, Any]) -> str:
        payload = json.dumps(
            {"tool_name": tool_name, "arguments": arguments},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def is_record_complete(record: ToolExecutionRecord) -> bool:
        return record.status in {"succeeded", "failed"} and record.output is not None

    @staticmethod
    def record_to_function_output(record: ToolExecutionRecord) -> FunctionCallOutput:
        output = record.output
        if output is None:
            output = record.error or "工具执行状态未知，未获得可恢复结果。"
        return {
            "type": "function_call_output",
            "call_id": record.call_id,
            "output": output,
        }

    # ── tool record construction ─────────────────────────────────────────

    @staticmethod
    def build_tool_records(
        function_calls: list[Any],
        tool_registry: Any,
        run_id: str,
    ) -> list[ToolExecutionRecord]:
        """Build ToolExecutionRecord list from LLM function_call items."""
        records: list[ToolExecutionRecord] = []
        for fc in function_calls:
            try:
                arguments = json.loads(fc.arguments)
            except json.JSONDecodeError:
                arguments = {}
            if hasattr(tool_registry, "get_side_effect_policy"):
                side_effect_policy = tool_registry.get_side_effect_policy(fc.name)
            else:
                side_effect_policy = "read_only"
            records.append(
                ToolExecutionRecord(
                    call_id=fc.call_id,
                    tool_name=fc.name,
                    arguments=arguments,
                    arguments_hash=CheckpointOrchestrator.hash_tool_arguments(
                        fc.name, arguments
                    ),
                    side_effect_policy=side_effect_policy,
                    idempotency_key=f"{run_id}:{fc.call_id}",
                )
            )
        return records

    # ── save / load / clear ──────────────────────────────────────────────

    def save(
        self,
        session_id: str | None,
        step: int,
        phase: CheckpointPhase,
        current_input: list[dict[str, Any]] | str,
        agent: Any,  # BaseAgent (avoid circular import)
        run_id: str,
        tool_calls: list[ToolExecutionRecord] | None = None,
        function_outputs: list[FunctionCallOutput] | None = None,
        error: str | None = None,
    ) -> None:
        if not session_id:
            return
        history_source: list[dict[str, Any]] | str = (
            function_outputs if function_outputs is not None else current_input
        )
        self._manager.save(
            session_id=session_id,
            step=step,
            history=self.history_from_input(history_source),
            agent_state=agent.get_state(),
            phase=phase,
            llm_input=deepcopy(current_input),
            tool_calls=deepcopy(tool_calls or []),
            function_outputs=deepcopy(function_outputs or []),
            run_id=run_id,
            error=error,
        )

    def load(self, session_id: str) -> Checkpoint | None:
        return self._manager.load(session_id)

    def clear(self, session_id: str | None) -> None:
        if session_id:
            self._manager.clear(session_id)

    def has_checkpoint(self, session_id: str) -> bool:
        return self._manager.has_checkpoint(session_id)

    def get_latest_step(self, session_id: str) -> int:
        return self._manager.get_latest_step(session_id)

    @property
    def manager(self) -> CheckpointManager | SQLiteCheckpointManager:
        return self._manager

    # ── resume ───────────────────────────────────────────────────────────

    def prepare_resume(
        self,
        checkpoint: Checkpoint,
        agent: Any,  # BaseAgent
        max_steps: int,
    ) -> ResumeContext:
        """Parse a checkpoint into the execution context needed to resume.

        The caller (AgentRunner) receives a ResumeContext and uses it to
        configure its main loop: where to start, what input to feed, and
        which tool records still need executing.
        """
        agent.restore_state(checkpoint.agent_state)
        restored_tool_events = agent.get_state().get("tool_event_history", [])
        collected_events: list[dict[str, Any]] = (
            list(restored_tool_events) if isinstance(restored_tool_events, list) else []
        )

        current_input = (
            checkpoint.llm_input
            if checkpoint.llm_input is not None
            else checkpoint.history
        )
        start_step = max(checkpoint.step, 1)
        resume_tool_records: list[ToolExecutionRecord] | None = None

        if checkpoint.phase in {"tool_requested", "tool_partial_done"}:
            resume_tool_records = deepcopy(checkpoint.tool_calls)
        elif checkpoint.phase == "tool_output_ready":
            current_input = (
                list(checkpoint.function_outputs)
                if checkpoint.function_outputs
                else list(checkpoint.history)
            )
            start_step = min(checkpoint.step + 1, max_steps + 1)
        elif checkpoint.phase in {"completed", "failed"}:
            start_step = max_steps + 1

        return ResumeContext(
            run_id=checkpoint.run_id or "",
            start_step=start_step,
            current_input=current_input,
            resume_tool_records=resume_tool_records,
            collected_events=collected_events,
        )
