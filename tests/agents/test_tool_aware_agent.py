from app.agents.tool_aware_agent import ToolAwareAgent


def test_tool_aware_agent_emits_event():
    events = []

    def listener(event):
        events.append(event)

    agent = ToolAwareAgent(
        name="tool-aware-agent",
        model="test-model",
        system_prompt="You are a test agent.",
        tool_call_listener=listener,
    )

    agent.emit_tool_event({
        "agent_name": "tool-aware-agent",
        "step": 1,
        "tool_name": "calculator",
        "status": "start",
    })

    assert len(events) == 1
    assert events[0]["tool_name"] == "calculator"
    assert events[0]["status"] == "start"