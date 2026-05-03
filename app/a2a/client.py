from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any
from urllib.parse import urljoin
from uuid import uuid4

import httpx

from app.a2a.schemas import (
    A2ARole,
    AgentCard,
    ListTasksResponse,
    Message,
    Part,
    SendMessageConfiguration,
    SendMessageRequest,
    SendMessageResponse,
    StreamResponse,
    Task,
    TEXT_PLAIN,
)


class A2AClientError(RuntimeError):
    pass


class A2AHTTPError(A2AClientError):
    def __init__(self, status_code: int, message: str):
        super().__init__(f"A2A HTTP error {status_code}: {message}")
        self.status_code = status_code
        self.message = message


class A2AClient:
    """Synchronous A2A HTTP+JSON client."""

    def __init__(
        self,
        base_url: str,
        *,
        bearer_token: str | None = None,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.bearer_token = bearer_token
        self.timeout = timeout
        self._client = http_client or httpx.Client(timeout=timeout)
        self._owns_client = http_client is None
        self._agent_card: AgentCard | None = None

    def __enter__(self) -> "A2AClient":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _headers(self, *, accept: str = "application/json") -> dict[str, str]:
        headers = {"Accept": accept}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        return headers

    def _root_url(self, path: str) -> str:
        return urljoin(f"{self.base_url}/", path.lstrip("/"))

    def _raise_for_error(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        try:
            payload = response.json()
            detail = payload.get("detail", payload)
            message = (
                detail.get("message", str(detail))
                if isinstance(detail, dict)
                else str(detail)
            )
        except Exception:
            message = response.text
        raise A2AHTTPError(response.status_code, message)

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self._client.request(
            method,
            url,
            json=json_body,
            headers=self._headers(),
            timeout=self.timeout,
        )
        self._raise_for_error(response)
        return response.json()

    def get_agent_card(self, *, refresh: bool = False) -> AgentCard:
        if self._agent_card is not None and not refresh:
            return self._agent_card

        card_url = (
            self.base_url
            if self.base_url.endswith("/.well-known/agent-card.json")
            else self._root_url("/.well-known/agent-card.json")
        )
        payload = self._request_json("GET", card_url)
        self._agent_card = AgentCard.model_validate(payload)
        return self._agent_card

    def get_extended_agent_card(self) -> AgentCard:
        service_base = self._service_base()
        payload = self._request_json(
            "GET",
            f"{service_base}/extendedAgentCard",
        )
        return AgentCard.model_validate(payload)

    def _service_base(self, agent_card: AgentCard | None = None) -> str:
        card = agent_card or self.get_agent_card()
        interfaces = [
            *card.supported_interfaces,
            *card.additional_interfaces,
        ]
        for interface in interfaces:
            if interface.protocol_binding == "HTTP+JSON":
                return interface.url.rstrip("/")
        if card.url:
            return card.url.rstrip("/")
        raise A2AClientError("Agent Card does not advertise an A2A HTTP+JSON URL")

    def send_message(self, request: SendMessageRequest) -> SendMessageResponse:
        payload = self._request_json(
            "POST",
            f"{self._service_base()}/message:send",
            json_body=request.model_dump(by_alias=True, exclude_none=True),
        )
        return SendMessageResponse.model_validate(payload)

    def send_text(
        self,
        text: str,
        *,
        context_id: str | None = None,
        task_id: str | None = None,
        return_immediately: bool = False,
        accepted_output_modes: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SendMessageResponse:
        request = SendMessageRequest(
            message=Message(
                role=A2ARole.user,
                messageId=str(uuid4()),
                taskId=task_id,
                contextId=context_id,
                parts=[Part(text=text, mediaType=TEXT_PLAIN)],
            ),
            configuration=SendMessageConfiguration(
                acceptedOutputModes=accepted_output_modes or [TEXT_PLAIN],
                returnImmediately=return_immediately,
            ),
            metadata=metadata or {},
        )
        return self.send_message(request)

    def get_task(self, task_id: str, *, history_length: int | None = None) -> Task:
        params = (
            {"historyLength": str(history_length)}
            if history_length is not None
            else None
        )
        response = self._client.get(
            f"{self._service_base()}/tasks/{task_id}",
            params=params,
            headers=self._headers(),
            timeout=self.timeout,
        )
        self._raise_for_error(response)
        return Task.model_validate(response.json())

    def list_tasks(
        self,
        *,
        context_id: str | None = None,
        state: str | None = None,
        page_size: int | None = None,
        page_token: str | None = None,
        history_length: int | None = None,
    ) -> ListTasksResponse:
        params: dict[str, Any] = {}
        if context_id is not None:
            params["contextId"] = context_id
        if state is not None:
            params["state"] = state
        if page_size is not None:
            params["pageSize"] = page_size
        if page_token is not None:
            params["pageToken"] = page_token
        if history_length is not None:
            params["historyLength"] = history_length

        response = self._client.get(
            f"{self._service_base()}/tasks",
            params=params,
            headers=self._headers(),
            timeout=self.timeout,
        )
        self._raise_for_error(response)
        return ListTasksResponse.model_validate(response.json())

    def cancel_task(self, task_id: str) -> Task:
        payload = self._request_json(
            "POST",
            f"{self._service_base()}/tasks/{task_id}:cancel",
            json_body={},
        )
        return Task.model_validate(payload)

    def stream_message(self, request: SendMessageRequest) -> Iterator[StreamResponse]:
        yield from self._stream_responses(
            f"{self._service_base()}/message:stream",
            request.model_dump(by_alias=True, exclude_none=True),
        )

    def stream_text(
        self,
        text: str,
        *,
        context_id: str | None = None,
        task_id: str | None = None,
    ) -> Iterator[StreamResponse]:
        request = SendMessageRequest(
            message=Message(
                role=A2ARole.user,
                messageId=str(uuid4()),
                taskId=task_id,
                contextId=context_id,
                parts=[Part(text=text, mediaType=TEXT_PLAIN)],
            )
        )
        yield from self.stream_message(request)

    def subscribe_task(self, task_id: str) -> Iterator[StreamResponse]:
        yield from self._stream_responses(
            f"{self._service_base()}/tasks/{task_id}:subscribe",
            {},
        )

    def _stream_responses(
        self,
        url: str,
        json_body: dict[str, Any],
    ) -> Iterator[StreamResponse]:
        with self._client.stream(
            "POST",
            url,
            json=json_body,
            headers=self._headers(accept="text/event-stream"),
            timeout=self.timeout,
        ) as response:
            self._raise_for_error(response)
            for data in self._iter_sse_data(response.iter_lines()):
                yield StreamResponse.model_validate_json(data)

    def _iter_sse_data(self, lines: Iterator[str]) -> Iterator[str]:
        data_lines: list[str] = []
        for line in lines:
            line = line.strip("\r")
            if not line:
                if data_lines:
                    yield "\n".join(data_lines)
                    data_lines = []
                continue
            if line.startswith(":"):
                continue
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if data_lines:
            yield "\n".join(data_lines)


def extract_text_from_message(message: Message) -> str:
    return "\n".join(part.text for part in message.parts if part.text is not None)


def extract_text_from_task(task: Task) -> str:
    artifact_texts: list[str] = []
    for artifact in task.artifacts:
        for part in artifact.parts:
            if part.text is not None:
                artifact_texts.append(part.text)
    if artifact_texts:
        return "\n".join(artifact_texts)
    if task.status.message is not None:
        return extract_text_from_message(task.status.message)
    return ""


def extract_text_from_send_response(response: SendMessageResponse) -> str:
    if response.message is not None:
        return extract_text_from_message(response.message)
    if response.task is not None:
        return extract_text_from_task(response.task)
    return ""


def stream_response_to_json(response: StreamResponse) -> str:
    return response.model_dump_json(
        by_alias=True,
        exclude_none=True,
        exclude_defaults=True,
    )


def stream_responses_to_text(responses: Iterator[StreamResponse]) -> str:
    parts = [stream_response_to_json(response) for response in responses]
    return "\n".join(parts)


def response_to_debug_json(payload: Any) -> str:
    if hasattr(payload, "model_dump"):
        return json.dumps(payload.model_dump(by_alias=True), ensure_ascii=False)
    return json.dumps(payload, ensure_ascii=False, default=str)
