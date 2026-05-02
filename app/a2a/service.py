import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

from fastapi import BackgroundTasks

from app.a2a.adapter import A2AAdapterError, A2AProtocolAdapter
from app.a2a.schemas import (
    A2ARole,
    Artifact,
    CancelTaskRequest,
    ListTasksResponse,
    Message,
    SendMessageRequest,
    SendMessageResponse,
    StreamResponse,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatusUpdateEvent,
)
from app.a2a.task_store import (
    InMemoryA2ATaskStore,
    TaskConflictError,
    TaskNotFoundError,
    TaskNotCancelableError,
)
from app.obj.types import AgentRunResult


A2ARunTurn = Callable[[Message, str], AgentRunResult]


class A2AServiceError(Exception):
    status_code = 400
    error_code = "a2a_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class A2ABadRequestError(A2AServiceError):
    status_code = 400
    error_code = "invalid_request"


class A2ATaskNotFoundServiceError(A2AServiceError):
    status_code = 404
    error_code = "task_not_found"


class A2ATaskNotCancelableServiceError(A2AServiceError):
    status_code = 400
    error_code = "task_not_cancelable"


class A2AService:
    def __init__(
        self,
        *,
        task_store: InMemoryA2ATaskStore,
        run_turn: A2ARunTurn,
        adapter: A2AProtocolAdapter | None = None,
    ) -> None:
        self.task_store = task_store
        self.run_turn = run_turn
        self.adapter = adapter or A2AProtocolAdapter()

    def _prepare_task(
        self,
        request: SendMessageRequest,
    ) -> tuple[Task, Message]:
        try:
            if request.message.role != A2ARole.user:
                raise A2AAdapterError("Only ROLE_USER messages are accepted")
            self.adapter.extract_text(request.message)
            return self.task_store.prepare_task_for_message(
                request.message,
                metadata=request.metadata,
            )
        except A2AAdapterError as e:
            raise A2ABadRequestError(str(e)) from e
        except TaskNotFoundError as e:
            raise A2ATaskNotFoundServiceError(f"Task not found: {e}") from e
        except TaskConflictError as e:
            raise A2ABadRequestError(str(e)) from e

    def _history_length(self, request: SendMessageRequest) -> int | None:
        return request.configuration.history_length

    def _artifact_from_result(self, result: AgentRunResult) -> Artifact | None:
        if not result["answer"]:
            return None
        return self.adapter.answer_artifact(result["answer"])

    def _run_task(
        self,
        *,
        task_id: str,
        message: Message,
        context_id: str,
    ) -> Task:
        task = self.task_store.mark_working(task_id, message=message)
        if task.status.state == TaskState.canceled:
            return task

        try:
            result = self.run_turn(message, context_id)
        except Exception as e:
            return self.task_store.fail(
                task_id,
                error_message=f"Agent execution failed: {e}",
                metadata={"error": type(e).__name__},
            )

        artifact = self._artifact_from_result(result)
        metadata: dict[str, Any] = {
            "steps": result["steps"],
            "error": result["error"],
            "tool_events": result["tool_events"],
        }
        if result["success"]:
            return self.task_store.complete(
                task_id,
                answer=result["answer"],
                artifacts=[artifact] if artifact is not None else [],
                metadata=metadata,
            )
        return self.task_store.fail(
            task_id,
            error_message=result["answer"] or result["error"] or "Agent run failed.",
            metadata=metadata,
        )

    def send_message(
        self,
        request: SendMessageRequest,
        background_tasks: BackgroundTasks | None = None,
    ) -> SendMessageResponse:
        task, message = self._prepare_task(request)
        task = self.task_store.mark_working(task.id, message=message)

        if request.configuration.return_immediately:
            if background_tasks is not None:
                background_tasks.add_task(
                    self._run_task,
                    task_id=task.id,
                    message=message,
                    context_id=task.context_id,
                )
            return SendMessageResponse(
                task=self.task_store.require(
                    task.id,
                    history_length=self._history_length(request),
                )
            )

        final_task = self._run_task(
            task_id=task.id,
            message=message,
            context_id=task.context_id,
        )
        if request.configuration.history_length is not None:
            final_task = self.task_store.require(
                final_task.id,
                history_length=request.configuration.history_length,
            )
        return SendMessageResponse(task=final_task)

    def get_task(
        self,
        task_id: str,
        *,
        history_length: int | None = None,
    ) -> Task:
        try:
            return self.task_store.require(task_id, history_length=history_length)
        except TaskNotFoundError as e:
            raise A2ATaskNotFoundServiceError(f"Task not found: {task_id}") from e

    def cancel_task(
        self,
        task_id: str,
        request: CancelTaskRequest | None = None,
    ) -> Task:
        request_metadata = request.metadata if request is not None else {}
        try:
            return self.task_store.cancel(
                task_id,
                metadata=request_metadata,
            )
        except TaskNotFoundError as e:
            raise A2ATaskNotFoundServiceError(f"Task not found: {task_id}") from e
        except TaskNotCancelableError as e:
            raise A2ATaskNotCancelableServiceError(str(e)) from e

    def list_tasks(
        self,
        *,
        context_id: str | None = None,
        state: TaskState | None = None,
        page_size: int = 50,
        page_token: str = "",
        history_length: int | None = None,
    ) -> ListTasksResponse:
        return self.task_store.list(
            context_id=context_id,
            state=state,
            page_size=page_size,
            page_token=page_token,
            history_length=history_length,
        )

    async def stream_message(
        self,
        request: SendMessageRequest,
    ) -> AsyncIterator[dict[str, str]]:
        task, message = self._prepare_task(request)
        yield self._sse_response(StreamResponse(task=task))

        working_task = self.task_store.mark_working(task.id, message=message)
        yield self._sse_response(
            StreamResponse(
                statusUpdate=TaskStatusUpdateEvent(
                    taskId=working_task.id,
                    contextId=working_task.context_id,
                    status=working_task.status,
                )
            )
        )

        loop = asyncio.get_running_loop()
        final_task = await loop.run_in_executor(
            None,
            lambda: self._run_task(
                task_id=working_task.id,
                message=message,
                context_id=working_task.context_id,
            ),
        )

        for artifact in final_task.artifacts:
            yield self._sse_response(
                StreamResponse(
                    artifactUpdate=TaskArtifactUpdateEvent(
                        taskId=final_task.id,
                        contextId=final_task.context_id,
                        artifact=artifact,
                    )
                )
            )

        yield self._sse_response(
            StreamResponse(
                statusUpdate=TaskStatusUpdateEvent(
                    taskId=final_task.id,
                    contextId=final_task.context_id,
                    status=final_task.status,
                    final=True,
                )
            )
        )

    def _sse_response(self, response: StreamResponse) -> dict[str, str]:
        return {
            "event": "message",
            "data": response.model_dump_json(
                by_alias=True,
                exclude_none=True,
                exclude_defaults=True,
            ),
        }
