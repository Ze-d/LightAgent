from collections.abc import Callable

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Request

from app.core.sse import EventSourceResponse
from app.a2a.schemas import (
    A2A_PROTOCOL_VERSION,
    AgentCard,
    CancelTaskRequest,
    ListTasksResponse,
    SendMessageRequest,
    SendMessageResponse,
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

    @router.get("/.well-known/agent-card.json", response_model=AgentCard)
    def get_agent_card(request: Request) -> AgentCard:
        return agent_card_provider(str(request.base_url).rstrip("/"))

    @router.get("/a2a/v1/extendedAgentCard", response_model=AgentCard)
    def get_extended_agent_card(
        request: Request,
        authorization: str | None = Header(default=None),
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
        return extended_agent_card_provider(str(request.base_url).rstrip("/"))

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
