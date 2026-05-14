"""Tool calling eval runner for AgentRunner and ToolRegistry."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app.agents.tool_aware_agent import ToolAwareAgent
from app.core.runner import AgentRunner
from app.core.tool_registry import ToolRegistry

from evals.metrics import average, safe_divide
from evals.models import EvalCaseResult, EvalSuiteResult


@dataclass(frozen=True)
class ToolCallingCase:
    id: str
    input: str
    expected_tool: str
    expected_args: dict[str, Any] = field(default_factory=dict)
    expected_result_contains: list[str] = field(default_factory=list)
    expected_answer_contains: list[str] = field(default_factory=list)
    llm_tool_name: str | None = None
    llm_args: dict[str, Any] | None = None
    final_answer: str = "done"


class ToolEvalRunner:
    """Runs deterministic tool-calling cases against the runtime loop."""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        suite_name: str = "tool_calling",
        model: str = "eval-model",
        max_steps: int = 3,
    ) -> None:
        self.registry = registry
        self.suite_name = suite_name
        self.model = model
        self.max_steps = max_steps

    def run(self, cases: list[ToolCallingCase]) -> EvalSuiteResult:
        case_results = [self._run_case(case) for case in cases]
        total = len(case_results)
        passed = sum(1 for result in case_results if result.passed)

        metrics = {
            "tool_selection_accuracy": safe_divide(
                sum(r.metrics["tool_selected_correctly"] for r in case_results),
                total,
            ),
            "argument_accuracy": safe_divide(
                sum(r.metrics["arguments_correct"] for r in case_results),
                total,
            ),
            "schema_valid_rate": safe_divide(
                sum(r.metrics["schema_valid"] for r in case_results),
                total,
            ),
            "tool_success_rate": safe_divide(
                sum(r.metrics["tool_success"] for r in case_results),
                total,
            ),
            "tool_result_contains_rate": safe_divide(
                sum(r.metrics["tool_result_contains_expected"] for r in case_results),
                total,
            ),
            "answer_contains_rate": safe_divide(
                sum(r.metrics["answer_contains_expected"] for r in case_results),
                total,
            ),
            "avg_latency_ms": average([
                r.metrics["latency_ms"] for r in case_results
            ]),
        }
        return EvalSuiteResult(
            suite=self.suite_name,
            total_cases=total,
            passed_cases=passed,
            metrics=metrics,
            cases=case_results,
        )

    def _run_case(self, case: ToolCallingCase) -> EvalCaseResult:
        start = time.perf_counter()
        tool_name = case.llm_tool_name or case.expected_tool
        tool_args = case.llm_args if case.llm_args is not None else case.expected_args

        fake_client = SimpleNamespace()
        fake_client.responses = SimpleNamespace()
        responses = [
            SimpleNamespace(
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name=tool_name,
                        arguments=json.dumps(tool_args, ensure_ascii=False),
                        call_id=f"{case.id}_call",
                    )
                ],
                output_text="",
            ),
            SimpleNamespace(output=[], output_text=case.final_answer),
        ]

        def fake_create(*args: Any, **kwargs: Any) -> Any:
            return responses.pop(0)

        fake_client.responses.create = fake_create
        runner = AgentRunner(
            client=fake_client,
            max_steps=self.max_steps,
            enable_tracing=False,
        )
        agent = ToolAwareAgent(
            name="runtime-eval-agent",
            model=self.model,
            system_prompt="You are evaluating runtime tool calling.",
        )

        result = runner.run(
            agent=agent,
            history=[{"role": "user", "content": case.input}],
            tool_registry=self.registry,
        )
        latency_ms = (time.perf_counter() - start) * 1000

        first_event = result["tool_events"][0] if result["tool_events"] else {}
        actual_tool = first_event.get("tool_name")
        actual_args = first_event.get("arguments", {})
        tool_output = str(first_event.get("result") or first_event.get("error") or "")

        selected = actual_tool == case.expected_tool
        args_correct = actual_args == case.expected_args
        tool_success = first_event.get("status") == "success"
        schema_valid = tool_success and not (
            tool_output.startswith("Parameter validation failed")
            or tool_output.startswith("Tool execution error")
        )
        result_contains = all(
            fragment in tool_output
            for fragment in case.expected_result_contains
        )
        answer_contains = all(
            fragment in result["answer"]
            for fragment in case.expected_answer_contains
        )
        passed = (
            selected
            and args_correct
            and schema_valid
            and tool_success
            and result_contains
            and answer_contains
            and result["success"]
        )

        return EvalCaseResult(
            case_id=case.id,
            passed=passed,
            metrics={
                "tool_selected_correctly": int(selected),
                "arguments_correct": int(args_correct),
                "schema_valid": int(schema_valid),
                "tool_success": int(tool_success),
                "tool_result_contains_expected": int(result_contains),
                "answer_contains_expected": int(answer_contains),
                "latency_ms": latency_ms,
            },
            details={
                "actual_tool": actual_tool,
                "actual_args": actual_args,
                "tool_output": tool_output,
                "answer": result["answer"],
                "runtime_success": result["success"],
                "runtime_error": result["error"],
            },
        )


def load_tool_cases(path: str | Path) -> list[ToolCallingCase]:
    cases: list[ToolCallingCase] = []
    with Path(path).open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            cases.append(ToolCallingCase(**json.loads(line)))
    return cases
