import json

import httpx

from app.a2a.client import (
    A2AClient,
    extract_text_from_send_response,
    stream_responses_to_text,
)
from app.a2a.schemas import TaskState


def _agent_card_payload() -> dict:
    return {
        "name": "remote-agent",
        "description": "Remote test agent",
        "version": "1.0.0",
        "url": "http://remote.test/a2a/v1",
        "protocolVersion": "1.0",
        "supportedInterfaces": [
            {
                "url": "http://remote.test/a2a/v1",
                "protocolBinding": "HTTP+JSON",
                "protocolVersion": "1.0",
            }
        ],
        "capabilities": {"streaming": True},
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "skills": [],
    }


def _task_payload(
    *,
    task_id: str = "task-1",
    context_id: str = "ctx-1",
    text: str = "remote answer",
    state: str = "TASK_STATE_COMPLETED",
) -> dict:
    return {
        "id": task_id,
        "contextId": context_id,
        "status": {
            "state": state,
            "message": {
                "role": "ROLE_AGENT",
                "parts": [{"text": text}],
                "taskId": task_id,
                "contextId": context_id,
            },
        },
        "artifacts": [
            {
                "artifactId": "final-answer",
                "parts": [{"text": text}],
            }
        ],
        "history": [],
        "metadata": {"steps": 1},
    }


def test_a2a_client_discovers_agent_card_and_sends_text():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/.well-known/agent-card.json":
            return httpx.Response(200, json=_agent_card_payload())
        if request.url.path == "/a2a/v1/message:send":
            seen["request"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"task": _task_payload()})
        return httpx.Response(404)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = A2AClient("http://remote.test", http_client=http_client)

    card = client.get_agent_card()
    response = client.send_text("hello", context_id="ctx-1")

    assert card.name == "remote-agent"
    assert seen["request"]["message"]["parts"][0]["text"] == "hello"
    assert seen["request"]["message"]["contextId"] == "ctx-1"
    assert response.task.status.state == TaskState.completed
    assert extract_text_from_send_response(response) == "remote answer"


def test_a2a_client_stream_text_parses_sse_responses():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/.well-known/agent-card.json":
            return httpx.Response(200, json=_agent_card_payload())
        if request.url.path == "/a2a/v1/message:stream":
            working = {
                "statusUpdate": {
                    "taskId": "task-1",
                    "contextId": "ctx-1",
                    "status": {"state": "TASK_STATE_WORKING"},
                }
            }
            final = {
                "statusUpdate": {
                    "taskId": "task-1",
                    "contextId": "ctx-1",
                    "status": {"state": "TASK_STATE_COMPLETED"},
                    "final": True,
                }
            }
            body = (
                f"event: message\ndata: {json.dumps(working)}\n\n"
                f"event: message\ndata: {json.dumps(final)}\n\n"
            )
            return httpx.Response(
                200,
                content=body.encode("utf-8"),
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(404)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = A2AClient("http://remote.test", http_client=http_client)

    events = list(client.stream_text("hello"))
    debug_text = stream_responses_to_text(iter(events))

    assert len(events) == 2
    assert events[0].status_update.status.state == TaskState.working
    assert events[1].status_update.final is True
    assert "TASK_STATE_COMPLETED" in debug_text


def test_a2a_client_uses_bearer_token_for_extended_card():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/.well-known/agent-card.json":
            return httpx.Response(200, json=_agent_card_payload())
        if request.url.path == "/a2a/v1/extendedAgentCard":
            assert request.headers["authorization"] == "Bearer secret"
            return httpx.Response(200, json=_agent_card_payload())
        return httpx.Response(404)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = A2AClient(
        "http://remote.test",
        bearer_token="secret",
        http_client=http_client,
    )

    card = client.get_extended_agent_card()

    assert card.name == "remote-agent"
