"""Deterministic benchmark for expected tool selection coverage."""
import json
import os
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
from openai import OpenAI

from app.agents.tool_aware_agent import ToolAwareAgent
from app.configs.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_ID, LLM_TIMEOUT
from app.core.runner import AgentRunner
from app.tools.register import build_default_registry


@dataclass(frozen=True)
class ToolSelectionScenario:
    prompt: str
    expected_tool: str
    arguments: dict[str, Any]


SCENARIOS = [
    ToolSelectionScenario(
        prompt="Calculate 18 * 7.",
        expected_tool="calculator",
        arguments={"expression": "18 * 7"},
    ),
    ToolSelectionScenario(
        prompt="What time is it in Tokyo?",
        expected_tool="get_current_time",
        arguments={"city": "tokyo"},
    ),
    ToolSelectionScenario(
        prompt="Convert 2.5 kilometers to meters.",
        expected_tool="convert_units",
        arguments={"value": 2.5, "from_unit": "kilometer", "to_unit": "meter"},
    ),
    ToolSelectionScenario(
        prompt="Count the words and lines in this text: hello world second line.",
        expected_tool="analyze_text",
        arguments={"text": "hello world\nsecond line"},
    ),
    ToolSelectionScenario(
        prompt="Get the weather for Beijing.",
        expected_tool="get_weather",
        arguments={"city": "beijing"},
    ),
    ToolSelectionScenario(
        prompt="Search the local knowledge base for ToolRegistry schema.",
        expected_tool="search_knowledge",
        arguments={"query": "ToolRegistry schema", "top_k": 2},
    ),
    ToolSelectionScenario(
        prompt="Read all memory for this session.",
        expected_tool="memory_read",
        arguments={"scope": "all", "session_id": "tool-selection-benchmark"},
    ),
    ToolSelectionScenario(
        prompt="Remember that this benchmark covered memory append.",
        expected_tool="memory_append_session_summary",
        arguments={
            "session_id": "tool-selection-benchmark",
            "summary": "- Benchmark covered memory append.",
        },
    ),
]


def test_expected_tool_selection_accuracy_is_covered_by_benchmark():
    registry = build_default_registry()
    selected_correctly = 0
    executed_successfully = 0

    for index, scenario in enumerate(SCENARIOS):
        fake_client = SimpleNamespace()
        fake_client.responses = SimpleNamespace()

        function_call_item = SimpleNamespace(
            type="function_call",
            name=scenario.expected_tool,
            arguments=json.dumps(scenario.arguments),
            call_id=f"call_{index}",
        )
        responses = [
            SimpleNamespace(output=[function_call_item], output_text=""),
            SimpleNamespace(output=[], output_text="done"),
        ]

        def fake_create(*args, **kwargs):
            return responses.pop(0)

        fake_client.responses.create = fake_create

        runner = AgentRunner(client=fake_client, max_steps=3)
        agent = ToolAwareAgent(
            name="tool-selection-agent",
            model="test-model",
            system_prompt="You are a test agent.",
        )

        result = runner.run(
            agent=agent,
            history=[{"role": "user", "content": scenario.prompt}],
            tool_registry=registry,
        )

        tool_events = result["tool_events"]
        assert len(tool_events) == 1
        if tool_events[0]["tool_name"] == scenario.expected_tool:
            selected_correctly += 1
        if tool_events[0]["status"] == "success":
            executed_successfully += 1

    selection_accuracy = selected_correctly / len(SCENARIOS)
    execution_success_rate = executed_successfully / len(SCENARIOS)

    assert selection_accuracy == 1.0
    assert execution_success_rate == 1.0


@pytest.mark.skipif(
    os.getenv("RUN_REAL_TOOL_SELECTION_BENCHMARK") != "1",
    reason="Set RUN_REAL_TOOL_SELECTION_BENCHMARK=1 to run against the real model.",
)
def test_real_model_tool_selection_accuracy():
    if not LLM_API_KEY:
        pytest.skip("LLM_API_KEY is not configured.")

    registry = build_default_registry()
    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, timeout=LLM_TIMEOUT)
    tools = registry.get_openai_tools()
    selected_correctly = 0
    rows: list[tuple[str, str, str | None, bool]] = []

    system_prompt = (
        "You are testing tool selection. For each user request, choose exactly "
        "one function tool when a tool can answer it. Do not answer directly "
        "when a relevant tool is available."
    )

    for scenario in SCENARIOS:
        response = client.responses.create(
            model=LLM_MODEL_ID,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": scenario.prompt},
            ],
            tools=tools,
        )
        function_calls = [
            item for item in response.output
            if getattr(item, "type", None) == "function_call"
        ]
        actual_tool = function_calls[0].name if function_calls else None
        is_correct = actual_tool == scenario.expected_tool
        if is_correct:
            selected_correctly += 1
        rows.append((scenario.prompt, scenario.expected_tool, actual_tool, is_correct))

    accuracy = selected_correctly / len(SCENARIOS)

    print("\n=== Real Model Tool Selection Benchmark ===")
    print(f"Model: {LLM_MODEL_ID}")
    print(f"Base URL: {LLM_BASE_URL}")
    print(f"Scenarios: {len(SCENARIOS)}")
    print(f"Correct selections: {selected_correctly}")
    print(f"Tool selection accuracy: {accuracy:.1%}")
    for prompt, expected_tool, actual_tool, is_correct in rows:
        status = "PASS" if is_correct else "FAIL"
        print(
            f"[{status}] expected={expected_tool} actual={actual_tool} "
            f"prompt={prompt}"
        )
    print("==========================================")

    assert accuracy >= float(os.getenv("REAL_TOOL_SELECTION_MIN_ACCURACY", "0.75"))
