from types import SimpleNamespace

from app.agents.chat_agent import ChatAgent
from app.core.checkpoint import CheckpointManager
from app.core.hooks import BaseRunnerHooks
from app.core.runner import AgentRunner
from app.tools.register import build_default_registry


class RecordingHooks(BaseRunnerHooks):
    def __init__(self):
        self.events = []

    def on_run_start(self, event):
        self.events.append(("run_start", dict(event)))

    def on_run_end(self, event):
        self.events.append(("run_end", dict(event)))

    def on_llm_start(self, event):
        self.events.append(("llm_start", dict(event)))

    def on_llm_end(self, event):
        self.events.append(("llm_end", dict(event)))

    def on_tool_start(self, event):
        self.events.append(("tool_start", dict(event)))

    def on_tool_end(self, event):
        self.events.append(("tool_end", dict(event)))


def test_runner_returns_structured_result(monkeypatch):
    fake_client = SimpleNamespace()
    fake_client.responses = SimpleNamespace()

    fake_response = SimpleNamespace(
        output=[],
        output_text="这是最终答案"
    )

    def fake_create(*args, **kwargs):
        return fake_response

    fake_client.responses.create = fake_create

    runner = AgentRunner(client=fake_client, max_steps=3)
    agent = ChatAgent(
        name="chat-agent",
        model="test-model",
        system_prompt="You are a test agent."
    )

    result = runner.run(
        agent=agent,
        history=[{"role": "user", "content": "你好"}],
        tool_registry=None,
    )

    assert result["answer"] == "这是最终答案"
    assert result["success"] is True
    assert result["steps"] == 1
    assert result["tool_events"] == []
    assert result["error"] is None


def test_runner_clears_checkpoint_on_success(monkeypatch):
    fake_client = SimpleNamespace()
    fake_client.responses = SimpleNamespace()

    fake_response = SimpleNamespace(
        output=[],
        output_text="done"
    )

    def fake_create(*args, **kwargs):
        return fake_response

    fake_client.responses.create = fake_create

    runner = AgentRunner(client=fake_client, max_steps=3)
    agent = ChatAgent(
        name="chat-agent",
        model="test-model",
        system_prompt="You are a test agent."
    )
    checkpoint_manager = CheckpointManager()
    session_id = "session-with-stale-checkpoint"
    checkpoint_manager.save(
        session_id=session_id,
        step=1,
        history=[{"type": "function_call_output", "call_id": "old", "output": "old"}],
        agent_state={"tool_event_history": []},
    )

    result = runner.run(
        agent=agent,
        history=[{"role": "user", "content": "hello"}],
        tool_registry=None,
        session_id=session_id,
        checkpoint_manager=checkpoint_manager,
    )

    assert result["success"] is True
    assert checkpoint_manager.load(session_id) is None


def test_runner_emits_run_end_on_success(monkeypatch):
    fake_client = SimpleNamespace()
    fake_client.responses = SimpleNamespace()
    fake_client.responses.create = lambda *args, **kwargs: SimpleNamespace(
        output=[],
        output_text="done",
    )

    hooks = RecordingHooks()
    runner = AgentRunner(client=fake_client, max_steps=3, hooks=hooks, enable_tracing=False)
    agent = ChatAgent(
        name="chat-agent",
        model="test-model",
        system_prompt="You are a test agent.",
    )

    result = runner.run(
        agent=agent,
        history=[{"role": "user", "content": "hello"}],
        tool_registry=None,
    )

    run_end_events = [event for name, event in hooks.events if name == "run_end"]
    assert result["success"] is True
    assert run_end_events == [{
        "agent_name": "chat-agent",
        "success": True,
        "steps": 1,
        "error": None,
    }]


def test_runner_emits_tool_start_before_tool_end(monkeypatch):
    fake_client = SimpleNamespace()
    fake_client.responses = SimpleNamespace()

    function_call_item = SimpleNamespace(
        type="function_call",
        name="calculator",
        arguments='{"expression": "2 + 3"}',
        call_id="call_1",
    )
    responses = [
        SimpleNamespace(output=[function_call_item], output_text=""),
        SimpleNamespace(output=[], output_text="结果是 5"),
    ]
    fake_client.responses.create = lambda *args, **kwargs: responses.pop(0)

    hooks = RecordingHooks()
    runner = AgentRunner(client=fake_client, max_steps=3, hooks=hooks, enable_tracing=False)
    agent = ChatAgent(
        name="chat-agent",
        model="test-model",
        system_prompt="You are a test agent.",
    )

    result = runner.run(
        agent=agent,
        history=[{"role": "user", "content": "帮我算 2 + 3"}],
        tool_registry=build_default_registry(),
    )

    event_names = [name for name, _ in hooks.events]
    tool_start = next(event for name, event in hooks.events if name == "tool_start")
    tool_end = next(event for name, event in hooks.events if name == "tool_end")

    assert event_names.index("tool_start") < event_names.index("tool_end")
    assert tool_start["status"] == "start"
    assert tool_start["tool_name"] == "calculator"
    assert tool_start["arguments"] == {"expression": "2 + 3"}
    assert tool_end["status"] == "success"
    assert len(result["tool_events"]) == 1
