import pytest

from app.a2a.adapter import A2AAdapterError, A2AProtocolAdapter
from app.a2a.schemas import A2ARole, Message, Part, TaskState


def test_adapter_converts_user_message_to_chat_message():
    adapter = A2AProtocolAdapter()
    message = Message(
        role=A2ARole.user,
        messageId="msg-1",
        parts=[Part(text="hello"), Part(text="world")],
    )

    chat_message = adapter.to_chat_message(message)

    assert chat_message == {
        "role": "user",
        "content": "hello\nworld",
    }


def test_adapter_rejects_non_text_parts_in_p0():
    adapter = A2AProtocolAdapter()
    message = Message(
        role=A2ARole.user,
        messageId="msg-1",
        parts=[Part(data={"key": "value"})],
    )

    with pytest.raises(A2AAdapterError):
        adapter.to_chat_message(message)


def test_adapter_maps_agent_run_result_to_task():
    adapter = A2AProtocolAdapter()

    task = adapter.result_to_task(
        {
            "answer": "done",
            "success": True,
            "steps": 2,
            "tool_events": [],
            "error": None,
        },
        task_id="task-1",
        context_id="ctx-1",
    )

    assert task.id == "task-1"
    assert task.context_id == "ctx-1"
    assert task.status.state == TaskState.completed
    assert task.artifacts[0].parts[0].text == "done"
    assert task.metadata == {
        "steps": 2,
        "error": None,
    }
