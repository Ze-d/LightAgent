from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from app.a2a.schemas import (
    A2ARole,
    Artifact,
    ListTasksResponse,
    Message,
    Part,
    Task,
    TaskState,
    TaskStatus,
    TEXT_PLAIN,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskNotFoundError(KeyError):
    pass


class TaskConflictError(ValueError):
    pass


class InMemoryA2ATaskStore:
    """Thread-safe in-memory A2A task store.

    The store owns A2A task state only. Existing chat sessions remain in the
    app-level session manager, with A2A contextId mapped to session_id.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}
        self._lock = Lock()

    def _copy(self, task: Task, history_length: int | None = None) -> Task:
        copied = task.model_copy(deep=True)
        if history_length is not None:
            if history_length <= 0:
                copied.history = []
            else:
                copied.history = copied.history[-history_length:]
        return copied

    def _bind_message(
        self,
        message: Message,
        *,
        task_id: str,
        context_id: str,
    ) -> Message:
        message_id = message.message_id or str(uuid4())
        return message.model_copy(
            update={
                "message_id": message_id,
                "task_id": task_id,
                "context_id": context_id,
            },
            deep=True,
        )

    def prepare_task_for_message(
        self,
        message: Message,
        metadata: dict | None = None,
    ) -> tuple[Task, Message]:
        with self._lock:
            if message.task_id:
                task = self._tasks.get(message.task_id)
                if task is None:
                    raise TaskNotFoundError(message.task_id)
                context_id = message.context_id or task.context_id
                if context_id != task.context_id:
                    raise TaskConflictError(
                        "message contextId does not match existing task"
                    )
                task_id = task.id
                bound_message = self._bind_message(
                    message,
                    task_id=task_id,
                    context_id=context_id,
                )
                task.history.append(bound_message)
                task.status = TaskStatus(
                    state=TaskState.submitted,
                    message=bound_message,
                    timestamp=utc_now_iso(),
                )
                task.metadata.update(metadata or {})
                return self._copy(task), bound_message

            task_id = str(uuid4())
            context_id = message.context_id or str(uuid4())
            bound_message = self._bind_message(
                message,
                task_id=task_id,
                context_id=context_id,
            )
            task = Task(
                id=task_id,
                contextId=context_id,
                status=TaskStatus(
                    state=TaskState.submitted,
                    message=bound_message,
                    timestamp=utc_now_iso(),
                ),
                history=[bound_message],
                metadata=dict(metadata or {}),
            )
            self._tasks[task_id] = task
            return self._copy(task), bound_message

    def get(self, task_id: str, history_length: int | None = None) -> Task | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            return self._copy(task, history_length=history_length)

    def require(self, task_id: str, history_length: int | None = None) -> Task:
        task = self.get(task_id, history_length=history_length)
        if task is None:
            raise TaskNotFoundError(task_id)
        return task

    def list(
        self,
        *,
        context_id: str | None = None,
        state: TaskState | None = None,
        page_size: int = 50,
        page_token: str = "",
        history_length: int | None = None,
    ) -> ListTasksResponse:
        with self._lock:
            tasks = list(self._tasks.values())
            if context_id is not None:
                tasks = [task for task in tasks if task.context_id == context_id]
            if state is not None:
                tasks = [task for task in tasks if task.status.state == state]

            offset = int(page_token) if page_token.isdigit() else 0
            page_size = max(1, min(page_size, 100))
            page = tasks[offset:offset + page_size]
            next_offset = offset + len(page)
            next_token = str(next_offset) if next_offset < len(tasks) else ""

            return ListTasksResponse(
                tasks=[
                    self._copy(task, history_length=history_length)
                    for task in page
                ],
                totalSize=len(tasks),
                pageSize=page_size,
                nextPageToken=next_token,
            )

    def mark_working(self, task_id: str, message: Message | None = None) -> Task:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFoundError(task_id)
            task.status = TaskStatus(
                state=TaskState.working,
                message=message,
                timestamp=utc_now_iso(),
            )
            return self._copy(task)

    def complete(
        self,
        task_id: str,
        *,
        answer: str,
        artifacts: list[Artifact] | None = None,
        metadata: dict | None = None,
    ) -> Task:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFoundError(task_id)

            message = Message(
                role=A2ARole.agent,
                messageId=str(uuid4()),
                taskId=task.id,
                contextId=task.context_id,
                parts=[Part(text=answer, mediaType=TEXT_PLAIN)],
            )
            task.history.append(message)
            task.status = TaskStatus(
                state=TaskState.completed,
                message=message,
                timestamp=utc_now_iso(),
            )
            task.artifacts = list(artifacts or [])
            task.metadata.update(metadata or {})
            return self._copy(task)

    def fail(
        self,
        task_id: str,
        *,
        error_message: str,
        metadata: dict | None = None,
    ) -> Task:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFoundError(task_id)

            message = Message(
                role=A2ARole.agent,
                messageId=str(uuid4()),
                taskId=task.id,
                contextId=task.context_id,
                parts=[Part(text=error_message, mediaType=TEXT_PLAIN)],
            )
            task.history.append(message)
            task.status = TaskStatus(
                state=TaskState.failed,
                message=message,
                timestamp=utc_now_iso(),
            )
            task.metadata.update(metadata or {})
            return self._copy(task)
