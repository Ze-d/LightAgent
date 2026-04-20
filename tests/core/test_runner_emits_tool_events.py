from types import SimpleNamespace

from app.agents.tool_aware_agent import ToolAwareAgent
from app.core.runner import AgentRunner
from app.tools.register import build_default_registry


def test_runner_emits_tool_events(monkeypatch):
    events = []

    def listener(event):
        events.append(event)

    agent = ToolAwareAgent(
        name="tool-aware-agent",
        model="test-model",
        system_prompt="You are a test agent.",
        tool_call_listener=listener,
    )

    fake_client = SimpleNamespace()
    fake_client.responses = SimpleNamespace()
    fake_client.responses.create = SimpleNamespace()

    function_call_item = SimpleNamespace(
        type="function_call",
        name="calculator",
        arguments='{"expression": "2 + 3"}',
        call_id="call_1"
    )

    first_response = SimpleNamespace(
        output=[function_call_item],
        output_text=""
    )

    second_response = SimpleNamespace(
        output=[],
        output_text="结果是 5"
    )

    responses = [first_response, second_response]

    def fake_create(*args, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(fake_client.responses, "create", fake_create)

    runner = AgentRunner(client=fake_client, max_steps=3)
    registry = build_default_registry()

    result = runner.run(
        agent=agent,
        history=[{"role": "user", "content": "帮我算 2 + 3"}],
        tool_registry=registry,
    )

    assert result["answer"] == "结果是 5"
    assert len(events) == 1
    assert events[0]["status"] == "success"
    assert events[0]["tool_name"] == "calculator"
