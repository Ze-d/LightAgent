import json
from types import SimpleNamespace

from app.agents.tool_aware_agent import ToolAwareAgent
from app.core.runner import AgentRunner
from app.core.tool_registry import ToolRegistry
from app.core.tool_selection import HeuristicToolSelector


def _register_tool(registry: ToolRegistry, name: str, description: str, result: str) -> None:
    registry.register({
        "name": name,
        "description": description,
        "parameters": {"type": "object", "properties": {}},
        "handler": lambda: result,
    })


def test_runner_passes_only_selected_tools_to_llm():
    registry = ToolRegistry()
    _register_tool(registry, "calculator", "Evaluate arithmetic expressions.", "4")
    _register_tool(registry, "weather", "Get weather forecasts.", "sunny")
    captured_tool_names: list[list[str]] = []

    fake_client = SimpleNamespace()
    fake_client.responses = SimpleNamespace()

    def fake_create(*args, **kwargs):
        captured_tool_names.append([
            tool["name"] for tool in kwargs.get("tools") or []
        ])
        return SimpleNamespace(output=[], output_text="done")

    fake_client.responses.create = fake_create
    runner = AgentRunner(
        client=fake_client,
        max_steps=1,
        tool_selector=HeuristicToolSelector(max_tools=1),
    )
    agent = ToolAwareAgent(
        name="selector-agent",
        model="test-model",
        system_prompt="You are a test agent.",
    )

    result = runner.run(
        agent=agent,
        history=[{"role": "user", "content": "calculate 2 + 2"}],
        tool_registry=registry,
    )

    assert result["success"] is True
    assert captured_tool_names == [["calculator"]]


def test_runner_blocks_tool_calls_outside_selected_scope():
    registry = ToolRegistry()
    _register_tool(registry, "calculator", "Evaluate arithmetic expressions.", "4")
    _register_tool(registry, "weather", "Get weather forecasts.", "sunny")

    fake_client = SimpleNamespace()
    fake_client.responses = SimpleNamespace()
    fake_client.responses.create = lambda *args, **kwargs: SimpleNamespace(
        output=[
            SimpleNamespace(
                type="function_call",
                name="weather",
                arguments=json.dumps({}),
                call_id="call_hidden",
            )
        ],
        output_text="",
    )
    runner = AgentRunner(
        client=fake_client,
        max_steps=1,
        tool_selector=HeuristicToolSelector(max_tools=1),
    )
    agent = ToolAwareAgent(
        name="selector-agent",
        model="test-model",
        system_prompt="You are a test agent.",
    )

    result = runner.run(
        agent=agent,
        history=[{"role": "user", "content": "calculate 2 + 2"}],
        tool_registry=registry,
    )

    assert result["tool_events"][0]["tool_name"] == "weather"
    assert result["tool_events"][0]["status"] == "error"
    assert "not selected" in result["tool_events"][0]["error"]
