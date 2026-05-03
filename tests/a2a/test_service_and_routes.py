import threading
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.a2a.agent_card import build_agent_card, build_extended_agent_card
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
    client, store, _ = _client_with_service(run_turn=run_turn)
    return client, store


def _client_with_service(
    run_turn=_run_turn,
) -> tuple[TestClient, InMemoryA2ATaskStore, A2AService]:
    store = InMemoryA2ATaskStore()
    service = A2AService(
        task_store=store,
        run_turn=run_turn,
    )
    app = FastAPI()
    app.include_router(
        build_a2a_router(
            agent_card_provider=lambda base_url: build_agent_card(
                public_base_url="http://testserver",
                agent_name="chat-agent",
                version="0.1.0",
            ),
            service=service,
        )
    )
    return TestClient(app), store, service


def _agent_card_client(
    *,
    token: str | None = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(
        build_a2a_router(
            agent_card_provider=lambda base_url: build_agent_card(
                public_base_url=base_url,
                agent_name="chat-agent",
                version="0.1.0",
                extended_card_enabled=token is not None,
            ),
            extended_agent_card_provider=lambda base_url: build_extended_agent_card(
                public_base_url=base_url,
                agent_name="chat-agent",
                version="0.1.0",
            ),
            extended_agent_card_token=token,
        )
    )
    return TestClient(app)


def test_extended_agent_card_returns_not_found_when_disabled():
    client = _agent_card_client()

    response = client.get("/a2a/v1/extendedAgentCard")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "extended_agent_card_not_available"


def test_agent_card_uses_request_base_url_when_provider_accepts_it():
    client = _agent_card_client(token="secret")

    response = client.get("/.well-known/agent-card.json")

    assert response.status_code == 200
    payload = response.json()
    assert payload["url"] == "http://testserver/a2a/v1"
    assert payload["supportedInterfaces"][0]["url"] == "http://testserver/a2a/v1"
    assert payload["capabilities"]["extendedAgentCard"] is True


def test_extended_agent_card_requires_bearer_token():
    client = _agent_card_client(token="secret")

    missing = client.get("/a2a/v1/extendedAgentCard")
    wrong = client.get(
        "/a2a/v1/extendedAgentCard",
        headers={"Authorization": "Bearer wrong"},
    )
    authorized = client.get(
        "/a2a/v1/extendedAgentCard",
        headers={"Authorization": "Bearer secret"},
    )

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert authorized.status_code == 200
    assert authorized.json()["securitySchemes"]["bearerAuth"]["scheme"] == "bearer"


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


def test_subscribe_task_streams_later_final_event_to_existing_task():
    client, store, service = _client_with_service()
    task, _ = store.prepare_task_for_message(
        Message(
            role=A2ARole.user,
            parts=[Part(text="subscribe")],
            contextId="ctx-subscribe",
        )
    )
    service._mark_working(
        task.id,
        task.status.message,
    )

    def cancel_later() -> None:
        time.sleep(0.02)
        service.cancel_task(task.id)

    thread = threading.Thread(target=cancel_later)
    thread.start()
    try:
        with client.stream(
            "POST",
            f"/a2a/v1/tasks/{task.id}:subscribe",
        ) as response:
            body = "".join(response.iter_text())
    finally:
        thread.join(timeout=1.0)

    assert response.status_code == 200
    assert '"task"' in body
    assert '"statusUpdate"' in body
    assert "TASK_STATE_CANCELED" in body


def test_subscribe_terminal_task_returns_unsupported_operation():
    client, store = _client_with_store()
    task, _ = store.prepare_task_for_message(
        Message(role=A2ARole.user, parts=[Part(text="done")])
    )
    store.complete(task.id, answer="already done")

    response = client.post(f"/a2a/v1/tasks/{task.id}:subscribe")

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "unsupported_operation"


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


def test_service_skips_runner_when_return_immediately_task_was_canceled():
    calls = {"count": 0}

    def run_turn(message: Message, context_id: str):
        calls["count"] += 1
        return _run_turn(message, context_id)

    store = InMemoryA2ATaskStore()
    service = A2AService(task_store=store, run_turn=run_turn)
    task, message = store.prepare_task_for_message(
        Message(role=A2ARole.user, parts=[Part(text="late")])
    )
    service._mark_working(task.id, message)
    service.cancel_task(task.id)

    result = service._run_task(
        task_id=task.id,
        message=message,
        context_id=task.context_id,
        publish_start=False,
    )

    assert result.status.state == TaskState.canceled
    assert calls["count"] == 0
