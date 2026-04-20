from types import SimpleNamespace

from app.agents.chat_agent import ChatAgent
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