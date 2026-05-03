import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

from fastapi import BackgroundTasks

from app.a2a.adapter import A2AAdapterError, A2AProtocolAdapter
from app.a2a.event_broker import A2AEventBroker
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


class A2AUnsupportedOperationServiceError(A2AServiceError):
    status_code = 400
    error_code = "unsupported_operation"


class A2AService:
    def __init__(
        self,
        *,
        task_store: InMemoryA2ATaskStore,
        run_turn: A2ARunTurn,
        adapter: A2AProtocolAdapter | None = None,
        event_broker: A2AEventBroker | None = None,
    ) -> None:
        self.task_store = task_store
        self.run_turn = run_turn
        self.adapter = adapter or A2AProtocolAdapter()
        self.event_broker = event_broker or A2AEventBroker()

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

    def _publish_status(self, task: Task, *, final: bool = False) -> None:
        self.event_broker.publish(
            task.id,
            StreamResponse(
                statusUpdate=TaskStatusUpdateEvent(
                    taskId=task.id,
                    contextId=task.context_id,
                    status=task.status,
                    final=final,
                )
            ),
        )

    def _publish_artifact(self, task: Task, artifact: Artifact) -> None:
        self.event_broker.publish(
            task.id,
            StreamResponse(
                artifactUpdate=TaskArtifactUpdateEvent(
                    taskId=task.id,
                    contextId=task.context_id,
                    artifact=artifact,
                )
            ),
        )

    def _mark_working(self, task_id: str, message: Message) -> Task:
        task = self.task_store.mark_working(task_id, message=message)
        if task.status.state == TaskState.working:
            self._publish_status(task)
        return task

    def _run_task(
        self,
        *,
        task_id: str,
        message: Message,
        context_id: str,
        publish_start: bool = True,
    ) -> Task:
        if publish_start:
            task = self._mark_working(task_id, message)
            if task.status.state == TaskState.canceled:
                return task
        else:
            task = self.task_store.require(task_id)
            if task.status.state == TaskState.canceled:
                return task

        try:
            result = self.run_turn(message, context_id)
        except Exception as e:
            final_task = self.task_store.fail(
                task_id,
                error_message=f"Agent execution failed: {e}",
                metadata={"error": type(e).__name__},
            )
            if final_task.status.state == TaskState.failed:
                self._publish_status(final_task, final=True)
            return final_task

        artifact = self._artifact_from_result(result)
        metadata: dict[str, Any] = {
            "steps": result["steps"],
            "error": result["error"],
            "tool_events": result["tool_events"],
        }
        if result["success"]:
            final_task = self.task_store.complete(
                task_id,
                answer=result["answer"],
                artifacts=[artifact] if artifact is not None else [],
                metadata=metadata,
            )
            if final_task.status.state == TaskState.completed:
                for item in final_task.artifacts:
                    self._publish_artifact(final_task, item)
                self._publish_status(final_task, final=True)
            return final_task

        final_task = self.task_store.fail(
            task_id,
            error_message=result["answer"] or result["error"] or "Agent run failed.",
            metadata=metadata,
        )
        if final_task.status.state == TaskState.failed:
            self._publish_status(final_task, final=True)
        return final_task

    def send_message(
        self,
        request: SendMessageRequest,
        background_tasks: BackgroundTasks | None = None,
    ) -> SendMessageResponse:
        task, message = self._prepare_task(request)

        if request.configuration.return_immediately:
            task = self._mark_working(task.id, message)
            if background_tasks is not None:
                background_tasks.add_task(
                    self._run_task,
                    task_id=task.id,
                    message=message,
                    context_id=task.context_id,
                    publish_start=False,
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
            task = self.task_store.cancel(
                task_id,
                metadata=request_metadata,
            )
            self._publish_status(task, final=True)
            return task
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

    def stream_message(
        self,
        request: SendMessageRequest,
    ) -> AsyncIterator[dict[str, str]]:
        task, message = self._prepare_task(request)
        subscription = self.event_broker.subscribe(task.id)

        async def event_stream() -> AsyncIterator[dict[str, str]]:
            try:
                yield self._sse_response(StreamResponse(task=task))
                loop = asyncio.get_running_loop()
                loop.run_in_executor(
                    None,
                    lambda: self._run_task(
                        task_id=task.id,
                        message=message,
                        context_id=task.context_id,
                    ),
                )
                async for response in subscription:
                    yield self._sse_response(response)
            finally:
                subscription.close()

        return event_stream()

    def subscribe_task(self, task_id: str) -> AsyncIterator[dict[str, str]]:
        task = self.get_task(task_id)
        if task.status.state in {
            TaskState.completed,
            TaskState.failed,
            TaskState.canceled,
            TaskState.rejected,
        }:
            raise A2AUnsupportedOperationServiceError(
                f"Task is terminal and cannot be subscribed: {task_id}"
            )
        subscription = self.event_broker.subscribe(task_id)

        async def event_stream() -> AsyncIterator[dict[str, str]]:
            try:
                yield self._sse_response(StreamResponse(task=task))
                async for response in subscription:
                    yield self._sse_response(response)
            finally:
                subscription.close()

        return event_stream()

    def _sse_response(self, response: StreamResponse) -> dict[str, str]:
        return {
            "event": "message",
            "data": response.model_dump_json(
                by_alias=True,
                exclude_none=True,
                exclude_defaults=True,
            ),
        }
