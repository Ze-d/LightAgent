from types import SimpleNamespace
from app.agents.chat_agent import ChatAgent
from app.core.runner import AgentRunner
from app.core.tool_registry import ToolRegistry


def test_runner_returns_direct_text(monkeypatch):
    fake_client = SimpleNamespace()
    fake_client.responses = SimpleNamespace()
    fake_client.responses.create = SimpleNamespace()


    runner = AgentRunner(client=fake_client, max_steps=3)
    agent = ChatAgent(
        name="chat-agent",
        model="test-model",
        system_prompt="You are a test agent."
    )

    fake_response = SimpleNamespace(
        output=[],
        output_text="这是最终答案"
    )

    def fake_create(*args, **kwargs):
        return fake_response

    monkeypatch.setattr(fake_client.responses, "create", fake_create)

    result = runner.run(agent=agent, history=[{"role": "user", "content": "你好"}])
    assert result == "这是最终答案"