"""Checkpoint recovery eval runner with deterministic fault injection."""
from __future__ import annotations

import time
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

from app.agents.chat_agent import ChatAgent
from app.core.checkpoint import (
    Checkpoint,
    CheckpointManager,
    CheckpointOrchestrator,
    ToolExecutionRecord,
)
from app.core.runner import AgentRunner
from app.core.tool_registry import ToolRegistry
from app.obj.types import SideEffectPolicy

from evals.metrics import average, safe_divide
from evals.models import EvalCaseResult, EvalSuiteResult


CheckpointScenario = Literal[
    "tool_output_resume_no_repeat",
    "non_idempotent_running_blocks",
]


@dataclass(frozen=True)
class CheckpointEvalCase:
    id: str
    scenario: CheckpointScenario
    tool_name: str
    side_effect_policy: SideEffectPolicy
    expected_resume_success: bool
    expected_duplicate_tool_count: int = 0
    expected_error: str | None = None
    expected_checkpoint_phase: str | None = None


class CheckpointEvalRunner:
    """Runs checkpoint recovery cases against AgentRunner."""

    def run(self, cases: list[CheckpointEvalCase]) -> EvalSuiteResult:
        case_results = [self._run_case(case) for case in cases]
        total = len(case_results)
        passed = sum(1 for result in case_results if result.passed)
        recoverable_cases = [
            result for result in case_results
            if result.details.get("expected_resume_success") is True
        ]
        non_idempotent_cases = [
            result for result in case_results
            if result.details.get("side_effect_policy") == "non_idempotent"
        ]
        metrics = {
            "recovery_success_rate": safe_divide(
                sum(r.metrics["resume_success"] for r in recoverable_cases),
                len(recoverable_cases),
            ),
            "expected_outcome_rate": safe_divide(passed, total),
            "duplicate_tool_execution_count": sum(
                r.metrics["duplicate_tool_count"] for r in case_results
            ),
            "non_idempotent_protection_rate": safe_divide(
                sum(
                    r.metrics["non_idempotent_protected"]
                    for r in non_idempotent_cases
                ),
                len(non_idempotent_cases),
            ),
            "checkpoint_phase_correct_rate": safe_divide(
                sum(r.metrics["checkpoint_phase_correct"] for r in case_results),
                total,
            ),
            "avg_resume_latency_ms": average([
                r.metrics["resume_latency_ms"] for r in case_results
            ]),
        }
        return EvalSuiteResult(
            suite="checkpoint_recovery",
            total_cases=total,
            passed_cases=passed,
            metrics=metrics,
            cases=case_results,
        )

    def _run_case(self, case: CheckpointEvalCase) -> EvalCaseResult:
        if case.scenario == "tool_output_resume_no_repeat":
            return self._run_tool_output_resume(case)
        if case.scenario == "non_idempotent_running_blocks":
            return self._run_non_idempotent_blocks(case)
        raise ValueError(f"Unknown checkpoint eval scenario: {case.scenario}")

    def _run_tool_output_resume(self, case: CheckpointEvalCase) -> EvalCaseResult:
        tool_calls = {"count": 0}
        registry = ToolRegistry()
        registry.register({
            "name": case.tool_name,
            "description": "Eval tool.",
            "parameters": {"type": "object", "properties": {}},
            "handler": lambda: self._count_tool_call(tool_calls),
            "side_effect_policy": case.side_effect_policy,
        })
        function_call_item = SimpleNamespace(
            type="function_call",
            name=case.tool_name,
            arguments="{}",
            call_id=f"{case.id}_call",
        )
        fake_client = SimpleNamespace()
        fake_client.responses = SimpleNamespace()
        llm_calls = {"count": 0}

        def fake_create(*args, **kwargs):
            llm_calls["count"] += 1
            if llm_calls["count"] == 1:
                return SimpleNamespace(output=[function_call_item], output_text="")
            if llm_calls["count"] == 2:
                raise RuntimeError("eval injected interruption")
            return SimpleNamespace(output=[], output_text="done after resume")

        fake_client.responses.create = fake_create
        manager = CheckpointManager()
        orchestrator = CheckpointOrchestrator(manager)
        runner = AgentRunner(
            client=fake_client,
            max_steps=3,
            enable_tracing=False,
            checkpoint=orchestrator,
        )
        agent = self._agent()
        session_id = case.id

        try:
            runner.run(
                agent=agent,
                history=[{"role": "user", "content": "run eval tool"}],
                tool_registry=registry,
                session_id=session_id,
            )
        except RuntimeError:
            pass

        checkpoint = manager.load(session_id)
        expected_phase = case.expected_checkpoint_phase or "before_llm"
        phase_correct = checkpoint is not None and checkpoint.phase == expected_phase

        start = time.perf_counter()
        resumed = runner.run(
            agent=agent,
            history=[{"role": "user", "content": "run eval tool"}],
            tool_registry=registry,
            session_id=session_id,
            resume_checkpoint=checkpoint,
        )
        resume_latency_ms = (time.perf_counter() - start) * 1000

        duplicate_count = max(0, tool_calls["count"] - 1)
        resume_success = resumed["success"]
        passed = (
            resume_success == case.expected_resume_success
            and duplicate_count == case.expected_duplicate_tool_count
            and phase_correct
            and resumed["error"] == case.expected_error
        )
        return EvalCaseResult(
            case_id=case.id,
            passed=passed,
            metrics={
                "resume_success": int(resume_success),
                "duplicate_tool_count": duplicate_count,
                "non_idempotent_protected": 0,
                "checkpoint_phase_correct": int(phase_correct),
                "resume_latency_ms": resume_latency_ms,
            },
            details={
                "scenario": case.scenario,
                "side_effect_policy": case.side_effect_policy,
                "expected_resume_success": case.expected_resume_success,
                "actual_error": resumed["error"],
                "actual_answer": resumed["answer"],
                "tool_execution_count": tool_calls["count"],
                "checkpoint_phase": checkpoint.phase if checkpoint else None,
            },
        )

    def _run_non_idempotent_blocks(self, case: CheckpointEvalCase) -> EvalCaseResult:
        tool_calls = {"count": 0}
        registry = ToolRegistry()
        registry.register({
            "name": case.tool_name,
            "description": "Eval non-idempotent tool.",
            "parameters": {"type": "object", "properties": {}},
            "handler": lambda: self._count_tool_call(tool_calls),
            "side_effect_policy": case.side_effect_policy,
        })
        fake_client = SimpleNamespace()
        fake_client.responses = SimpleNamespace()

        def fail_if_called(*args, **kwargs):
            raise RuntimeError("LLM should not run before manual resume")

        fake_client.responses.create = fail_if_called
        manager = CheckpointManager()
        orchestrator = CheckpointOrchestrator(manager)
        runner = AgentRunner(
            client=fake_client,
            max_steps=3,
            enable_tracing=False,
            checkpoint=orchestrator,
        )
        agent = self._agent()
        session_id = case.id
        checkpoint = Checkpoint(
            step=1,
            history=[{"role": "user", "content": "run non-idempotent tool"}],
            agent_state={},
            session_id=session_id,
            run_id=f"{case.id}_run",
            phase="tool_partial_done",
            llm_input=[{"role": "user", "content": "run non-idempotent tool"}],
            tool_calls=[
                ToolExecutionRecord(
                    call_id=f"{case.id}_call",
                    tool_name=case.tool_name,
                    arguments={},
                    arguments_hash="eval-hash",
                    status="running",
                    side_effect_policy=case.side_effect_policy,
                )
            ],
        )
        manager.save_checkpoint(session_id, checkpoint)

        start = time.perf_counter()
        result = runner.run(
            agent=agent,
            history=[{"role": "user", "content": "run non-idempotent tool"}],
            tool_registry=registry,
            session_id=session_id,
            resume_checkpoint=checkpoint,
        )
        resume_latency_ms = (time.perf_counter() - start) * 1000
        expected_phase = case.expected_checkpoint_phase or "tool_partial_done"
        latest = manager.load(session_id)
        phase_correct = latest is not None and latest.phase == expected_phase
        duplicate_count = max(0, tool_calls["count"])
        protected = (
            result["error"] == "tool_requires_manual_resume"
            and tool_calls["count"] == 0
        )
        passed = (
            result["success"] == case.expected_resume_success
            and duplicate_count == case.expected_duplicate_tool_count
            and result["error"] == case.expected_error
            and phase_correct
            and protected
        )
        return EvalCaseResult(
            case_id=case.id,
            passed=passed,
            metrics={
                "resume_success": int(result["success"]),
                "duplicate_tool_count": duplicate_count,
                "non_idempotent_protected": int(protected),
                "checkpoint_phase_correct": int(phase_correct),
                "resume_latency_ms": resume_latency_ms,
            },
            details={
                "scenario": case.scenario,
                "side_effect_policy": case.side_effect_policy,
                "expected_resume_success": case.expected_resume_success,
                "actual_error": result["error"],
                "actual_answer": result["answer"],
                "tool_execution_count": tool_calls["count"],
                "checkpoint_phase": latest.phase if latest else None,
            },
        )

    @staticmethod
    def _count_tool_call(counter: dict[str, int]) -> str:
        counter["count"] += 1
        return f"called-{counter['count']}"

    @staticmethod
    def _agent() -> ChatAgent:
        return ChatAgent(
            name="checkpoint-eval-agent",
            model="eval-model",
            system_prompt="You are evaluating checkpoint recovery.",
        )


def load_checkpoint_cases(path: str | Path) -> list[CheckpointEvalCase]:
    cases: list[CheckpointEvalCase] = []
    with Path(path).open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            cases.append(CheckpointEvalCase(**json.loads(line)))
    return cases
