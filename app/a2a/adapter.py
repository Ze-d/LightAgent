from uuid import uuid4

from app.a2a.schemas import (
    A2ARole,
    Artifact,
    Message,
    Part,
    Task,
    TaskState,
    TaskStatus,
    TEXT_PLAIN,
)
from app.obj.types import AgentRunResult, ChatMessage


class A2AAdapterError(ValueError):
    """Raised when an A2A payload cannot be mapped to the internal runtime."""


class A2AProtocolAdapter:
    """Translate between A2A protocol objects and MyAgent runtime objects."""

    def extract_text(self, message: Message) -> str:
        chunks: list[str] = []
        for part in message.parts:
            if part.text is None:
                raise A2AAdapterError("Only text parts are supported in P0")
            chunks.append(part.text)
        return "\n".join(chunks)

    def to_chat_message(self, message: Message) -> ChatMessage:
        role = "assistant" if message.role == A2ARole.agent else "user"
        return {
            "role": role,
            "content": self.extract_text(message),
        }

    def text_message(
        self,
        text: str,
        *,
        role: A2ARole,
        task_id: str | None = None,
        context_id: str | None = None,
    ) -> Message:
        return Message(
            role=role,
            messageId=str(uuid4()),
            taskId=task_id,
            contextId=context_id,
            parts=[Part(text=text, mediaType=TEXT_PLAIN)],
        )

    def answer_artifact(
        self,
        answer: str,
        *,
        artifact_id: str = "final-answer",
    ) -> Artifact:
        return Artifact(
            artifactId=artifact_id,
            name="Final answer",
            parts=[Part(text=answer, mediaType=TEXT_PLAIN)],
        )

    def result_to_task(
        self,
        result: AgentRunResult,
        *,
        task_id: str,
        context_id: str,
        history: list[Message] | None = None,
    ) -> Task:
        state = TaskState.completed if result["success"] else TaskState.failed
        status_message = self.text_message(
            result["answer"] or result["error"] or "",
            role=A2ARole.agent,
            task_id=task_id,
            context_id=context_id,
        )
        artifacts = (
            [self.answer_artifact(result["answer"])]
            if result["answer"]
            else []
        )
        return Task(
            id=task_id,
            contextId=context_id,
            status=TaskStatus(state=state, message=status_message),
            artifacts=artifacts,
            history=list(history or []),
            metadata={
                "steps": result["steps"],
                "error": result["error"],
            },
        )
