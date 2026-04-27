from types import SimpleNamespace

from app.agents.chat_agent import ChatAgent
from app.core.checkpoint import CheckpointManager
from app.core.runner import AgentRunner


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
