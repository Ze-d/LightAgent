import pytest

from app.a2a.schemas import A2ARole, Message, Part, TaskState
from app.a2a.task_store import (
    InMemoryA2ATaskStore,
    TaskNotCancelableError,
    TaskNotFoundError,
)


def test_task_store_prepares_new_task_for_message():
    store = InMemoryA2ATaskStore()
    message = Message(
        role=A2ARole.user,
        parts=[Part(text="hello")],
        contextId="ctx-1",
    )

    task, bound_message = store.prepare_task_for_message(message)

    assert task.id
    assert task.context_id == "ctx-1"
    assert task.status.state == TaskState.submitted
    assert bound_message.task_id == task.id
    assert bound_message.context_id == "ctx-1"
    assert store.require(task.id).history[0].parts[0].text == "hello"


def test_task_store_completes_task_and_limits_history():
    store = InMemoryA2ATaskStore()
    task, _ = store.prepare_task_for_message(
        Message(role=A2ARole.user, parts=[Part(text="hello")])
    )

    completed = store.complete(
        task.id,
        answer="done",
        metadata={"steps": 1},
    )
    truncated = store.require(task.id, history_length=1)

    assert completed.status.state == TaskState.completed
    assert completed.status.message.parts[0].text == "done"
    assert completed.metadata["steps"] == 1
    assert len(truncated.history) == 1
    assert truncated.history[0].role == A2ARole.agent


def test_task_store_raises_for_missing_task():
    store = InMemoryA2ATaskStore()

    with pytest.raises(TaskNotFoundError):
        store.require("missing")


def test_task_store_cancels_submitted_task():
    store = InMemoryA2ATaskStore()
    task, _ = store.prepare_task_for_message(
        Message(role=A2ARole.user, parts=[Part(text="cancel me")])
    )

    canceled = store.cancel(task.id)

    assert canceled.status.state == TaskState.canceled
    assert canceled.status.message.parts[0].text == "Task canceled by client."
    assert store.require(task.id).status.state == TaskState.canceled


def test_task_store_does_not_overwrite_canceled_task_with_completion():
    store = InMemoryA2ATaskStore()
    task, _ = store.prepare_task_for_message(
        Message(role=A2ARole.user, parts=[Part(text="cancel me")])
    )

    store.cancel(task.id)
    completed = store.complete(task.id, answer="late result")

    assert completed.status.state == TaskState.canceled
    assert completed.artifacts == []


def test_task_store_rejects_cancel_for_completed_task():
    store = InMemoryA2ATaskStore()
    task, _ = store.prepare_task_for_message(
        Message(role=A2ARole.user, parts=[Part(text="finish")])
    )
    store.complete(task.id, answer="done")

    with pytest.raises(TaskNotCancelableError):
        store.cancel(task.id)
