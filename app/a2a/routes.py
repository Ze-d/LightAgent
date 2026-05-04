import json
from collections.abc import AsyncIterator, Callable
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.core.sse import EventSourceResponse
from app.a2a.schemas import (
    A2A_PROTOCOL_VERSION,
    AgentCard,
    CancelTaskJSONRPCRequest,
    CancelTaskRequest,
    GetExtendedAgentCardRequest,
    GetTaskRequest,
    JSONRPCError,
    JSONRPCRequest,
    JSONRPCResponse,
    ListTasksResponse,
    ListTasksRequest,
    SendMessageRequest,
    SendMessageResponse,
    SubscribeTaskRequest,
    Task,
    TaskState,
)
from app.a2a.service import A2AService, A2AServiceError


def build_a2a_router(
    agent_card_provider: Callable[[str], AgentCard],
    service: A2AService | None = None,
    extended_agent_card_provider: Callable[[str], AgentCard] | None = None,
    extended_agent_card_token: str | None = None,
) -> APIRouter:
    router = APIRouter(tags=["A2A"])

    @router.get(
        "/.well-known/agent-card.json",
        response_model=AgentCard,
        response_model_exclude_none=True,
        response_model_exclude_defaults=True,
    )
    def get_agent_card(request: Request) -> AgentCard:
        return agent_card_provider(str(request.base_url).rstrip("/"))

    def resolve_extended_agent_card(
        base_url: str,
        authorization: str | None,
    ) -> AgentCard:
        if extended_agent_card_provider is None or not extended_agent_card_token:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "extended_agent_card_not_available",
                    "message": "Extended Agent Card is not enabled.",
                },
            )
        expected_header = f"Bearer {extended_agent_card_token}"
        if authorization != expected_header:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "unauthorized",
                    "message": "Valid bearer token is required.",
                },
            )
        return extended_agent_card_provider(base_url)

    @router.get(
        "/a2a/v1/extendedAgentCard",
        response_model=AgentCard,
        response_model_exclude_none=True,
        response_model_exclude_defaults=True,
    )
    def get_extended_agent_card(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> AgentCard:
        return resolve_extended_agent_card(
            str(request.base_url).rstrip("/"),
            authorization,
        )

    @router.get("/a2a/v1", include_in_schema=False)
    def get_a2a_interface_root() -> dict[str, str]:
        return {
            "message": "A2A interface reserved for message and task endpoints.",
            "protocolVersion": A2A_PROTOCOL_VERSION,
        }

    def raise_service_error(error: A2AServiceError) -> None:
        raise HTTPException(
            status_code=error.status_code,
            detail={
                "code": error.error_code,
                "message": error.message,
            },
        )

    if service is None:
        return router

    def jsonrpc_success(rpc_id: str | int | None, result: Any) -> JSONResponse:
        if hasattr(result, "model_dump"):
            result = result.model_dump(by_alias=True, exclude_none=True)
        payload = JSONRPCResponse(id=rpc_id, result=result).model_dump(
            by_alias=True,
            exclude_none=True,
        )
        return JSONResponse(payload)

    def jsonrpc_error(
        rpc_id: str | int | None,
        *,
        code: int,
        message: str,
        data: Any | None = None,
    ) -> JSONResponse:
        payload = JSONRPCResponse(
            id=rpc_id,
            error=JSONRPCError(
                code=code,
                message=message,
                data=data,
            ),
        ).model_dump(by_alias=True, exclude_none=True)
        return JSONResponse(payload)

    def jsonrpc_service_error(
        rpc_id: str | int | None,
        error: A2AServiceError,
    ) -> JSONResponse:
        service_error_codes = {
            "task_not_found": -32001,
            "task_not_cancelable": -32002,
            "unsupported_operation": -32003,
            "invalid_request": -32602,
        }
        return jsonrpc_error(
            rpc_id,
            code=service_error_codes.get(error.error_code, -32000),
            message=error.message,
            data={
                "code": error.error_code,
                "httpStatus": error.status_code,
            },
        )

    def jsonrpc_http_error(
        rpc_id: str | int | None,
        error: HTTPException,
    ) -> JSONResponse:
        detail = error.detail if isinstance(error.detail, dict) else {}
        message = detail.get("message", str(error.detail))
        return jsonrpc_error(
            rpc_id,
            code=-32000,
            message=message,
            data={
                "code": detail.get("code", "http_error"),
                "httpStatus": error.status_code,
            },
        )

    async def jsonrpc_stream(
        rpc_id: str | int | None,
        responses: AsyncIterator[dict[str, str]],
    ) -> AsyncIterator[dict[str, str]]:
        try:
            async for event in responses:
                data = event.get("data", "")
                result = json.loads(data) if isinstance(data, str) else data
                payload = JSONRPCResponse(
                    id=rpc_id,
                    result=result,
                ).model_dump(by_alias=True, exclude_none=True)
                yield {
                    "event": event.get("event", "message"),
                    "data": json.dumps(payload, ensure_ascii=False, default=str),
                }
        except A2AServiceError as e:
            payload = jsonrpc_service_error(rpc_id, e).body.decode("utf-8")
            yield {"event": "message", "data": payload}

    @router.post("/a2a/v1/rpc")
    async def jsonrpc_endpoint(
        request: Request,
        background_tasks: BackgroundTasks,
        authorization: str | None = Header(default=None),
    ):
        rpc_id: str | int | None = None
        try:
            payload = await request.json()
        except Exception:
            return jsonrpc_error(None, code=-32700, message="Parse error")

        if isinstance(payload, dict):
            raw_id = payload.get("id")
            if isinstance(raw_id, (str, int)) or raw_id is None:
                rpc_id = raw_id
        try:
            rpc_request = JSONRPCRequest.model_validate(payload)
            rpc_id = rpc_request.id
        except ValidationError as e:
            return jsonrpc_error(
                rpc_id,
                code=-32600,
                message="Invalid Request",
                data=e.errors(include_context=False),
            )

        try:
            if rpc_request.method == "SendMessage":
                params = SendMessageRequest.model_validate(rpc_request.params)
                return jsonrpc_success(
                    rpc_id,
                    service.send_message(
                        params,
                        background_tasks=background_tasks,
                    ),
                )

            if rpc_request.method == "SendStreamingMessage":
                params = SendMessageRequest.model_validate(rpc_request.params)
                return EventSourceResponse(
                    jsonrpc_stream(
                        rpc_id,
                        service.stream_message(params),
                    )
                )

            if rpc_request.method == "GetTask":
                params = GetTaskRequest.model_validate(rpc_request.params)
                return jsonrpc_success(
                    rpc_id,
                    service.get_task(
                        params.id,
                        history_length=params.history_length,
                    ),
                )

            if rpc_request.method == "ListTasks":
                params = ListTasksRequest.model_validate(rpc_request.params)
                return jsonrpc_success(
                    rpc_id,
                    service.list_tasks(
                        context_id=params.context_id,
                        state=params.resolved_state(),
                        page_size=params.page_size,
                        page_token=params.page_token,
                        history_length=params.history_length,
                    ),
                )

            if rpc_request.method == "CancelTask":
                params = CancelTaskJSONRPCRequest.model_validate(rpc_request.params)
                return jsonrpc_success(
                    rpc_id,
                    service.cancel_task(
                        params.id,
                        request=CancelTaskRequest(metadata=params.metadata),
                    ),
                )

            if rpc_request.method == "SubscribeToTask":
                params = SubscribeTaskRequest.model_validate(rpc_request.params)
                return EventSourceResponse(
                    jsonrpc_stream(
                        rpc_id,
                        service.subscribe_task(params.id),
                    )
                )

            if rpc_request.method == "GetExtendedAgentCard":
                GetExtendedAgentCardRequest.model_validate(rpc_request.params)
                return jsonrpc_success(
                    rpc_id,
                    resolve_extended_agent_card(
                        str(request.base_url).rstrip("/"),
                        authorization,
                    ),
                )

            return jsonrpc_error(
                rpc_id,
                code=-32601,
                message=f"Method not found: {rpc_request.method}",
            )
        except ValidationError as e:
            return jsonrpc_error(
                rpc_id,
                code=-32602,
                message="Invalid params",
                data=e.errors(include_context=False),
            )
        except A2AServiceError as e:
            return jsonrpc_service_error(rpc_id, e)
        except HTTPException as e:
            return jsonrpc_http_error(rpc_id, e)

    @router.post(
        "/a2a/v1/message:send",
        response_model=SendMessageResponse,
    )
    def send_message(
        request: SendMessageRequest,
        background_tasks: BackgroundTasks,
    ) -> SendMessageResponse:
        try:
            return service.send_message(
                request,
                background_tasks=background_tasks,
            )
        except A2AServiceError as e:
            raise_service_error(e)

    @router.post("/a2a/v1/message:stream", response_class=EventSourceResponse)
    async def stream_message(request: SendMessageRequest):
        try:
            return EventSourceResponse(service.stream_message(request))
        except A2AServiceError as e:
            raise_service_error(e)

    @router.get("/a2a/v1/tasks/{task_id}", response_model=Task)
    def get_task(
        task_id: str,
        history_length: int | None = Query(default=None, alias="historyLength"),
    ) -> Task:
        try:
            return service.get_task(
                task_id,
                history_length=history_length,
            )
        except A2AServiceError as e:
            raise_service_error(e)

    @router.post("/a2a/v1/tasks/{task_id}:cancel", response_model=Task)
    def cancel_task(
        task_id: str,
        request: CancelTaskRequest | None = None,
    ) -> Task:
        try:
            return service.cancel_task(task_id, request=request)
        except A2AServiceError as e:
            raise_service_error(e)

    @router.post("/a2a/v1/tasks/{task_id}:subscribe", response_class=EventSourceResponse)
    async def subscribe_task(task_id: str):
        try:
            return EventSourceResponse(service.subscribe_task(task_id))
        except A2AServiceError as e:
            raise_service_error(e)

    @router.get("/a2a/v1/tasks", response_model=ListTasksResponse)
    def list_tasks(
        context_id: str | None = Query(default=None, alias="contextId"),
        state: TaskState | None = Query(default=None),
        page_size: int = Query(default=50, alias="pageSize", ge=1, le=100),
        page_token: str = Query(default="", alias="pageToken"),
        history_length: int | None = Query(default=None, alias="historyLength"),
    ) -> ListTasksResponse:
        return service.list_tasks(
            context_id=context_id,
            state=state,
            page_size=page_size,
            page_token=page_token,
            history_length=history_length,
        )

    return router
