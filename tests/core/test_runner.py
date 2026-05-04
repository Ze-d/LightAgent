from types import SimpleNamespace

import pytest

from app.agents.chat_agent import ChatAgent
from app.core.cancellation import CancellationToken
from app.core.checkpoint import Checkpoint, CheckpointManager, CheckpointOrchestrator, ToolExecutionRecord
from app.core.context_builder import ProviderContextState
from app.core.hooks import BaseRunnerHooks
from app.core.runner import AgentRunner
from app.core.tool_registry import ToolRegistry
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


def _count_tool_call(counter: dict[str, int]) -> str:
    counter["count"] += 1
    return f"called-{counter['count']}"


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

    checkpoint_manager = CheckpointManager()
    orchestrator = CheckpointOrchestrator(checkpoint_manager)
    runner = AgentRunner(client=fake_client, max_steps=3, checkpoint=orchestrator)
    agent = ChatAgent(
        name="chat-agent",
        model="test-model",
        system_prompt="You are a test agent."
    )
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
    )

    assert result["success"] is True
    assert checkpoint_manager.load(session_id) is None


def test_runner_clears_checkpoint_when_llm_returns_no_tool_calls():
    fake_client = SimpleNamespace()
    fake_client.responses = SimpleNamespace()
    fake_client.responses.create = lambda *args, **kwargs: SimpleNamespace(
        output=[],
        output_text="final without tools",
    )

    checkpoint_manager = CheckpointManager()
    orchestrator = CheckpointOrchestrator(checkpoint_manager)
    runner = AgentRunner(
        client=fake_client, max_steps=3, enable_tracing=False,
        checkpoint=orchestrator,
    )
    agent = ChatAgent(
        name="chat-agent",
        model="test-model",
        system_prompt="You are a test agent.",
    )
    session_id = "no-tool-final"

    result = runner.run(
        agent=agent,
        history=[{"role": "user", "content": "hello"}],
        tool_registry=None,
        session_id=session_id,
    )

    assert result["success"] is True
    assert result["answer"] == "final without tools"
    assert result["tool_events"] == []
    assert checkpoint_manager.load(session_id) is None


def test_runner_uses_openai_previous_response_id_for_incremental_turn():
    calls = []
    fake_client = SimpleNamespace()
    fake_client.responses = SimpleNamespace()

    def fake_create(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(id="resp_2", output=[], output_text="done")

    fake_client.responses.create = fake_create
    runner = AgentRunner(client=fake_client, max_steps=3, enable_tracing=False)
    agent = ChatAgent(
        name="chat-agent",
        model="test-model",
        system_prompt="You are a test agent.",
    )

    result = runner.run(
        agent=agent,
        history=[
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "old question"},
            {"role": "assistant", "content": "old answer"},
            {"role": "user", "content": "new question"},
        ],
        provider_state=ProviderContextState(
            provider="openai",
            provider_mode="openai_previous_response",
            last_response_id="resp_1",
        ),
    )

    assert result["response_id"] == "resp_2"
    assert calls == [{
        "model": "test-model",
        "input": [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "new question"},
        ],
        "tools": None,
        "previous_response_id": "resp_1",
        "store": True,
    }]


def test_runner_keeps_manual_provider_history_without_previous_response_id():
    calls = []
    fake_client = SimpleNamespace()
    fake_client.responses = SimpleNamespace()

    def fake_create(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(id="resp_2", output=[], output_text="done")

    fake_client.responses.create = fake_create
    runner = AgentRunner(client=fake_client, max_steps=3, enable_tracing=False)
    agent = ChatAgent(
        name="chat-agent",
        model="test-model",
        system_prompt="You are a test agent.",
    )
    history = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "old question"},
        {"role": "assistant", "content": "old answer"},
        {"role": "user", "content": "new question"},
    ]

    result = runner.run(
        agent=agent,
        history=history,
        provider_state=ProviderContextState(
            provider="openai_compatible",
            provider_mode="manual",
        ),
    )

    assert result["response_id"] == "resp_2"
    assert calls == [{
        "model": "test-model",
        "input": history,
        "tools": None,
    }]


def test_runner_cancellation_token_stops_before_llm_call():
    calls = []
    fake_client = SimpleNamespace()
    fake_client.responses = SimpleNamespace()

    def fake_create(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(output=[], output_text="should not run")

    fake_client.responses.create = fake_create
    runner = AgentRunner(client=fake_client, max_steps=3, enable_tracing=False)
    agent = ChatAgent(
        name="chat-agent",
        model="test-model",
        system_prompt="You are a test agent.",
    )
    cancellation_token = CancellationToken()
    cancellation_token.cancel("user canceled")

    result = runner.run(
        agent=agent,
        history=[{"role": "user", "content": "hello"}],
        cancellation_token=cancellation_token,
    )

    assert result["success"] is False
    assert result["error"] == "cancelled"
    assert "user canceled" in result["answer"]
    assert calls == []


def test_runner_chains_current_response_id_for_tool_outputs():
    calls = []
    tool_calls = {"count": 0}
    registry = ToolRegistry()
    registry.register({
        "name": "lookup",
        "description": "Lookup once.",
        "parameters": {"type": "object", "properties": {}},
        "handler": lambda: _count_tool_call(tool_calls),
    })
    function_call_item = SimpleNamespace(
        type="function_call",
        name="lookup",
        arguments="{}",
        call_id="call_1",
    )
    responses = [
        SimpleNamespace(id="resp_tool", output=[function_call_item], output_text=""),
        SimpleNamespace(id="resp_final", output=[], output_text="done"),
    ]
    fake_client = SimpleNamespace()
    fake_client.responses = SimpleNamespace()

    def fake_create(*args, **kwargs):
        calls.append(kwargs)
        return responses.pop(0)

    fake_client.responses.create = fake_create
    runner = AgentRunner(client=fake_client, max_steps=3, enable_tracing=False)
    agent = ChatAgent(
        name="chat-agent",
        model="test-model",
        system_prompt="You are a test agent.",
    )

    result = runner.run(
        agent=agent,
        history=[{"role": "user", "content": "lookup"}],
        tool_registry=registry,
        provider_state=ProviderContextState(
            provider="openai",
            provider_mode="openai_previous_response",
            last_response_id="resp_prev",
        ),
    )

    assert result["answer"] == "done"
    assert result["response_id"] == "resp_final"
    assert tool_calls["count"] == 1
    assert calls[0]["previous_response_id"] == "resp_prev"
    assert calls[1]["previous_response_id"] == "resp_tool"
    assert calls[1]["input"] == [
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": "called-1",
        }
    ]


def test_runner_cancellation_token_stops_before_next_tool_call():
    calls = {"first": 0, "second": 0}
    cancellation_token = CancellationToken()
    registry = ToolRegistry()

    def first_tool() -> str:
        calls["first"] += 1
        cancellation_token.cancel("stop after first tool")
        return "first-result"

    def second_tool() -> str:
        calls["second"] += 1
        return "second-result"

    registry.register({
        "name": "first_tool",
        "description": "First tool.",
        "parameters": {"type": "object", "properties": {}},
        "handler": first_tool,
    })
    registry.register({
        "name": "second_tool",
        "description": "Second tool.",
        "parameters": {"type": "object", "properties": {}},
        "handler": second_tool,
    })
    first_call = SimpleNamespace(
        type="function_call",
        name="first_tool",
        arguments="{}",
        call_id="call_1",
    )
    second_call = SimpleNamespace(
        type="function_call",
        name="second_tool",
        arguments="{}",
        call_id="call_2",
    )
    fake_client = SimpleNamespace()
    fake_client.responses = SimpleNamespace()
    fake_client.responses.create = lambda *args, **kwargs: SimpleNamespace(
        output=[first_call, second_call],
        output_text="",
    )
    runner = AgentRunner(client=fake_client, max_steps=3, enable_tracing=False)
    agent = ChatAgent(
        name="chat-agent",
        model="test-model",
        system_prompt="You are a test agent.",
    )

    result = runner.run(
        agent=agent,
        history=[{"role": "user", "content": "run tools"}],
        tool_registry=registry,
        cancellation_token=cancellation_token,
    )

    assert result["success"] is False
    assert result["error"] == "cancelled"
    assert calls == {"first": 1, "second": 0}
    assert len(result["tool_events"]) == 1
    assert result["tool_events"][0]["tool_name"] == "first_tool"


def test_runner_resumes_tool_output_without_repeating_tool(monkeypatch):
    tool_calls = {"count": 0}
    registry = ToolRegistry()
    registry.register({
        "name": "side_effect_tool",
        "description": "A tool whose result must not be duplicated.",
        "parameters": {"type": "object", "properties": {}},
        "handler": lambda: _count_tool_call(tool_calls),
        "side_effect_policy": "non_idempotent",
    })

    function_call_item = SimpleNamespace(
        type="function_call",
        name="side_effect_tool",
        arguments="{}",
        call_id="call_1",
    )
    first_response = SimpleNamespace(output=[function_call_item], output_text="")
    final_response = SimpleNamespace(output=[], output_text="done after resume")
    llm_calls = {"count": 0}

    fake_client = SimpleNamespace()
    fake_client.responses = SimpleNamespace()

    def fake_create(*args, **kwargs):
        llm_calls["count"] += 1
        if llm_calls["count"] == 1:
            return first_response
        if llm_calls["count"] == 2:
            raise RuntimeError("interrupted before model saw tool output")
        return final_response

    fake_client.responses.create = fake_create
    checkpoint_manager = CheckpointManager()
    orchestrator = CheckpointOrchestrator(checkpoint_manager)
    runner = AgentRunner(
        client=fake_client, max_steps=3, enable_tracing=False,
        checkpoint=orchestrator,
    )
    agent = ChatAgent(
        name="chat-agent",
        model="test-model",
        system_prompt="You are a test agent.",
    )
    session_id = "resume-tool-output"

    with pytest.raises(RuntimeError):
        runner.run(
            agent=agent,
            history=[{"role": "user", "content": "run side effect"}],
            tool_registry=registry,
            session_id=session_id,
        )

    checkpoint = checkpoint_manager.load(session_id)
    assert checkpoint is not None
    assert checkpoint.phase == "before_llm"
    assert tool_calls["count"] == 1

    resumed_result = runner.run(
        agent=agent,
        history=[{"role": "user", "content": "run side effect"}],
        tool_registry=registry,
        session_id=session_id,
        resume_checkpoint=checkpoint,
    )

    assert resumed_result["success"] is True
    assert resumed_result["answer"] == "done after resume"
    assert tool_calls["count"] == 1
    assert checkpoint_manager.load(session_id) is None


def test_runner_resumes_tool_requested_checkpoint_by_calling_tool_once():
    tool_calls = {"count": 0}
    registry = ToolRegistry()
    registry.register({
        "name": "lookup",
        "description": "Lookup once.",
        "parameters": {"type": "object", "properties": {}},
        "handler": lambda: _count_tool_call(tool_calls),
    })

    fake_client = SimpleNamespace()
    fake_client.responses = SimpleNamespace()
    fake_client.responses.create = lambda *args, **kwargs: SimpleNamespace(
        output=[],
        output_text="lookup complete",
    )

    checkpoint_manager = CheckpointManager()
    orchestrator = CheckpointOrchestrator(checkpoint_manager)
    runner = AgentRunner(
        client=fake_client, max_steps=3, enable_tracing=False,
        checkpoint=orchestrator,
    )
    agent = ChatAgent(
        name="chat-agent",
        model="test-model",
        system_prompt="You are a test agent.",
    )
    session_id = "resume-tool-requested"
    checkpoint = Checkpoint(
        step=1,
        history=[{"role": "user", "content": "lookup"}],
        agent_state={},
        session_id=session_id,
        run_id="run-1",
        phase="tool_requested",
        llm_input=[{"role": "user", "content": "lookup"}],
        tool_calls=[
            ToolExecutionRecord(
                call_id="call_1",
                tool_name="lookup",
                arguments={},
                arguments_hash="hash",
            )
        ],
    )
    checkpoint_manager.save_checkpoint(session_id, checkpoint)

    result = runner.run(
        agent=agent,
        history=[{"role": "user", "content": "lookup"}],
        tool_registry=registry,
        session_id=session_id,
        resume_checkpoint=checkpoint,
    )

    assert result["success"] is True
    assert result["answer"] == "lookup complete"
    assert tool_calls["count"] == 1
    assert checkpoint_manager.load(session_id) is None


def test_runner_does_not_retry_running_non_idempotent_tool():
    tool_calls = {"count": 0}
    registry = ToolRegistry()
    registry.register({
        "name": "send_email",
        "description": "Send email.",
        "parameters": {"type": "object", "properties": {}},
        "handler": lambda: _count_tool_call(tool_calls),
        "side_effect_policy": "non_idempotent",
    })

    fake_client = SimpleNamespace()
    fake_client.responses = SimpleNamespace()
    fake_client.responses.create = lambda *args, **kwargs: pytest.fail(
        "LLM should not be called before unresolved non-idempotent tool"
    )

    checkpoint_manager = CheckpointManager()
    orchestrator = CheckpointOrchestrator(checkpoint_manager)
    runner = AgentRunner(
        client=fake_client, max_steps=3, enable_tracing=False,
        checkpoint=orchestrator,
    )
    agent = ChatAgent(
        name="chat-agent",
        model="test-model",
        system_prompt="You are a test agent.",
    )
    session_id = "resume-non-idempotent-running"
    checkpoint = Checkpoint(
        step=1,
        history=[{"role": "user", "content": "send email"}],
        agent_state={},
        session_id=session_id,
        run_id="run-1",
        phase="tool_partial_done",
        llm_input=[{"role": "user", "content": "send email"}],
        tool_calls=[
            ToolExecutionRecord(
                call_id="call_1",
                tool_name="send_email",
                arguments={},
                arguments_hash="hash",
                status="running",
                side_effect_policy="non_idempotent",
            )
        ],
    )
    checkpoint_manager.save_checkpoint(session_id, checkpoint)

    result = runner.run(
        agent=agent,
        history=[{"role": "user", "content": "send email"}],
        tool_registry=registry,
        session_id=session_id,
        resume_checkpoint=checkpoint,
    )

    assert result["success"] is False
    assert result["error"] == "tool_requires_manual_resume"
    assert tool_calls["count"] == 0
    assert checkpoint_manager.load(session_id) is not None


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
