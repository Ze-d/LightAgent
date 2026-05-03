from app.a2a.schemas import (
    A2ARole,
    Artifact,
    Message,
    Part,
    SendMessageResponse,
    Task,
    TaskState,
    TaskStatus,
)
from app.a2a.tool_bridge import (
    create_remote_a2a_agent_tool_spec,
    register_remote_a2a_agent_tool,
)
from app.core.tool_registry import ToolRegistry


class FakeA2AClient:
    def __init__(self):
        self.calls = []

    def send_text(self, message: str, *, context_id: str | None = None):
        self.calls.append({"message": message, "context_id": context_id})
        return SendMessageResponse(
            task=Task(
                id="task-1",
                contextId=context_id or "ctx-1",
                status=TaskStatus(
                    state=TaskState.completed,
                    message=Message(
                        role=A2ARole.agent,
                        parts=[Part(text="remote done")],
                    ),
                ),
                artifacts=[
                    Artifact(
                        artifactId="final-answer",
                        parts=[Part(text="remote done")],
                    )
                ],
            )
        )


def test_create_remote_a2a_agent_tool_spec_delegates_to_client():
    fake_client = FakeA2AClient()
    spec = create_remote_a2a_agent_tool_spec(
        name="remote_agent",
        description="Delegate to a remote agent",
        base_url="http://remote.test",
        client=fake_client,
    )

    result = spec["handler"](message="hello", context_id="ctx-1")

    assert result == "remote done"
    assert fake_client.calls == [{"message": "hello", "context_id": "ctx-1"}]
    assert spec["side_effect_policy"] == "idempotent"


def test_register_remote_a2a_agent_tool_registers_openai_schema():
    fake_client = FakeA2AClient()
    registry = ToolRegistry()

    register_remote_a2a_agent_tool(
        registry,
        name="remote_agent",
        description="Delegate to a remote agent",
        base_url="http://remote.test",
        client=fake_client,
    )

    result = registry.call(
        "remote_agent",
        message="hello",
        context_id="ctx-2",
    )
    tool = registry.get_openai_tools()[0]

    assert result == "remote done"
    assert tool["name"] == "remote_agent"
    assert tool["parameters"]["properties"]["message"]["type"] == "string"
