from app.agents.chat_agent import ChatAgent


def test_chat_agent_basic_properties():
    agent = ChatAgent(
        name="test-agent",
        model="test-model",
        system_prompt="You are a test agent."
    )

    assert agent.name == "test-agent"
    assert agent.model == "test-model"
    assert agent.get_system_prompt() == "You are a test agent."
    assert agent.supports_tools() is True