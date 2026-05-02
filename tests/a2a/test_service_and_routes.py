from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.a2a.agent_card import build_agent_card
from app.a2a.routes import build_a2a_router
from app.a2a.schemas import A2ARole, Message, Part, TaskState
from app.a2a.service import A2AService
from app.a2a.task_store import InMemoryA2ATaskStore


def _run_turn(message: Message, context_id: str):
    text = "\n".join(part.text or "" for part in message.parts)
    return {
        "answer": f"echo: {text} in {context_id}",
        "success": True,
        "steps": 1,
        "tool_events": [],
        "error": None,
    }


def _client() -> TestClient:
    client, _ = _client_with_store()
    return client


def _client_with_store(run_turn=_run_turn) -> tuple[TestClient, InMemoryA2ATaskStore]:
    store = InMemoryA2ATaskStore()
    service = A2AService(
        task_store=store,
        run_turn=run_turn,
    )
    app = FastAPI()
    app.include_router(
        build_a2a_router(
            agent_card_provider=lambda: build_agent_card(
                public_base_url="http://testserver",
                agent_name="chat-agent",
                version="0.1.0",
            ),
            service=service,
        )
    )
    return TestClient(app), store


def test_message_send_completes_task_and_gets_task():
    client = _client()

    response = client.post(
        "/a2a/v1/message:send",
        json={
            "message": {
                "role": "ROLE_USER",
                "parts": [{"text": "hello"}],
                "contextId": "ctx-1",
            }
        },
    )

    assert response.status_code == 200
    payload = response.json()
    task = payload["task"]
    assert task["contextId"] == "ctx-1"
    assert task["status"]["state"] == TaskState.completed
    assert task["artifacts"][0]["parts"][0]["text"] == "echo: hello in ctx-1"

    task_response = client.get(f"/a2a/v1/tasks/{task['id']}")
    assert task_response.status_code == 200
    assert task_response.json()["id"] == task["id"]


def test_list_tasks_filters_by_context_id():
    client = _client()
    client.post(
        "/a2a/v1/message:send",
        json={
            "message": {
                "role": "ROLE_USER",
                "parts": [{"text": "first"}],
                "contextId": "ctx-a",
            }
        },
    )
    client.post(
        "/a2a/v1/message:send",
        json={
            "message": {
                "role": "ROLE_USER",
                "parts": [{"text": "second"}],
                "contextId": "ctx-b",
            }
        },
    )

    response = client.get("/a2a/v1/tasks", params={"contextId": "ctx-a"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["totalSize"] == 1
    assert payload["tasks"][0]["contextId"] == "ctx-a"


def test_message_stream_emits_task_artifact_and_final_status():
    client = _client()

    with client.stream(
        "POST",
        "/a2a/v1/message:stream",
        json={
            "message": {
                "role": "ROLE_USER",
                "parts": [{"text": "stream"}],
                "contextId": "ctx-stream",
            }
        },
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert '"task"' in body
    assert '"artifactUpdate"' in body
    assert '"statusUpdate"' in body
    assert "TASK_STATE_COMPLETED" in body


def test_message_send_rejects_unsupported_data_part():
    client = _client()

    response = client.post(
        "/a2a/v1/message:send",
        json={
            "message": {
                "role": "ROLE_USER",
                "parts": [{"data": {"x": 1}}],
            }
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_request"


def test_cancel_task_marks_task_canceled():
    client, store = _client_with_store()
    task, _ = store.prepare_task_for_message(
        Message(
            role=A2ARole.user,
            parts=[Part(text="cancel")],
            contextId="ctx-cancel",
        )
    )

    response = client.post(f"/a2a/v1/tasks/{task.id}:cancel", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"]["state"] == TaskState.canceled
    assert payload["status"]["message"]["parts"][0]["text"] == (
        "Task canceled by client."
    )


def test_cancel_completed_task_returns_not_cancelable():
    client, store = _client_with_store()
    task, _ = store.prepare_task_for_message(
        Message(role=A2ARole.user, parts=[Part(text="done")])
    )
    store.complete(task.id, answer="already done")

    response = client.post(f"/a2a/v1/tasks/{task.id}:cancel", json={})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "task_not_cancelable"


def test_service_skips_runner_when_task_was_canceled_before_background_run():
    calls = {"count": 0}

    def run_turn(message: Message, context_id: str):
        calls["count"] += 1
        return _run_turn(message, context_id)

    store = InMemoryA2ATaskStore()
    service = A2AService(task_store=store, run_turn=run_turn)
    task, message = store.prepare_task_for_message(
        Message(role=A2ARole.user, parts=[Part(text="late")])
    )
    store.cancel(task.id)

    result = service._run_task(
        task_id=task.id,
        message=message,
        context_id=task.context_id,
    )

    assert result.status.state == TaskState.canceled
    assert calls["count"] == 0
